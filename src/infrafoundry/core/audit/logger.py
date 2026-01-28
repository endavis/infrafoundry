"""Audit logger service for tracking infrastructure operations."""

from __future__ import annotations

import hashlib
import json
import os
import socket
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, ClassVar

from sqlalchemy.orm import Session, sessionmaker

from infrafoundry.core.audit.models import AuditEntry, AuditStatus
from infrafoundry.core.base_manager import BaseManager
from infrafoundry.core.events import Event, EventType

if TYPE_CHECKING:
    from infrafoundry.core.events import UnifiedEventBus


class AuditLogger(BaseManager):
    """Logs all operations to immutable audit trail.

    Automatically subscribes to the event bus to capture infrastructure
    operations. Each audit entry includes a SHA-256 checksum for tamper
    detection.

    Attributes:
        AUDITED_EVENTS: Mapping of event types to audit action names
    """

    AUDITED_EVENTS: ClassVar[dict[EventType, str]] = {
        EventType.BEFORE_PLAN: "plan_started",
        EventType.AFTER_PLAN: "plan_completed",
        EventType.PLAN_FAILED: "plan_failed",
        EventType.BEFORE_APPLY: "apply_started",
        EventType.AFTER_APPLY: "apply_completed",
        EventType.APPLY_FAILED: "apply_failed",
        EventType.BEFORE_DESTROY: "destroy_started",
        EventType.AFTER_DESTROY: "destroy_completed",
        EventType.DESTROY_FAILED: "destroy_failed",
        EventType.DRIFT_DETECTED: "drift_detected",
        EventType.POLICY_VIOLATION: "policy_violation",
    }

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        event_bus: UnifiedEventBus | None = None,
        get_current_user: Callable[[], str] | None = None,
    ) -> None:
        """Initialize audit logger.

        Args:
            session_factory: SQLAlchemy session factory for database access
            event_bus: Event bus to subscribe to for automatic logging
            get_current_user: Callable that returns current user identifier
        """
        super().__init__()
        self._session_factory = session_factory
        self._get_current_user = get_current_user or self._default_get_user
        self._event_bus = event_bus

        # Subscribe to audited events if event bus provided
        if event_bus:
            self._subscribe_to_events(event_bus)

        self._log_debug("AuditLogger initialized")

    def _default_get_user(self) -> str:
        """Get current user from environment."""
        return os.environ.get("USER") or os.environ.get("USERNAME") or "unknown"

    def _subscribe_to_events(self, event_bus: UnifiedEventBus) -> None:
        """Subscribe to all audited events.

        Args:
            event_bus: Event bus to subscribe to
        """
        for event_type in self.AUDITED_EVENTS:
            event_bus.subscribe(event_type, self._handle_event)
        self._log_debug(f"Subscribed to {len(self.AUDITED_EVENTS)} event types")

    def _handle_event(self, event: Event) -> None:
        """Handle an event by creating an audit entry.

        Args:
            event: Event to log
        """
        action = self.AUDITED_EVENTS.get(event.event_type)
        if not action:
            return

        # Determine status based on event type
        if "failed" in event.event_type.value:
            status = AuditStatus.FAILED
        elif event.event_type.value.startswith("before_"):
            status = AuditStatus.IN_PROGRESS
        else:
            status = AuditStatus.SUCCESS

        # Extract provider and resource from event data
        provider = event.context.provider
        resource = event.context.resource

        # Extract message from event data
        message = event.data.get("message") or event.data.get("error")

        # Build changes summary from event data
        changes_summary = None
        if "changes" in event.data or "plan" in event.data:
            changes_summary = {
                k: v
                for k, v in event.data.items()
                if k in ("changes", "plan", "resources_affected")
            }

        self.log(
            event_type=event.event_type,
            action=action,
            status=status,
            environment=event.environment,
            provider=provider,
            resource_name=resource,
            message=str(message) if message else None,
            changes_summary=changes_summary,
            request_metadata={"event_data": event.data} if event.data else None,
        )

    def log(
        self,
        event_type: EventType,
        action: str,
        status: AuditStatus,
        environment: str | None = None,
        command: str | None = None,
        provider: str | None = None,
        resource_name: str | None = None,
        resource_type: str | None = None,
        message: str | None = None,
        changes_summary: dict[str, Any] | None = None,
        request_metadata: dict[str, Any] | None = None,
    ) -> AuditEntry:
        """Create an immutable audit entry.

        Args:
            event_type: Type of event being logged
            action: Audit action name (e.g., plan_started, apply_completed)
            status: Operation status (success, failed, in_progress)
            environment: Target environment
            command: CLI command (plan, apply, destroy)
            provider: Provider name
            resource_name: Specific resource affected
            resource_type: Type of resource
            message: Additional context or error message
            changes_summary: Summary of changes made
            request_metadata: CLI args, git commit, etc.

        Returns:
            Created AuditEntry
        """
        user = self._get_current_user()
        ip_address = self._get_ip_address()
        timestamp = datetime.now(UTC)

        # Derive command from action if not provided
        if not command and action:
            for cmd in ("plan", "apply", "destroy", "drift"):
                if cmd in action:
                    command = cmd
                    break

        # Create entry without checksum first
        entry = AuditEntry(
            timestamp=timestamp,
            event_type=event_type.value,
            user_identifier=user,
            environment=environment,
            command=command,
            provider=provider,
            resource_name=resource_name,
            resource_type=resource_type,
            action=action,
            status=status.value,
            message=message,
            ip_address=ip_address,
            changes_summary=changes_summary,
            request_metadata=request_metadata,
        )

        # Calculate checksum over entry data
        entry.checksum = self._calculate_checksum(entry)

        # Save to database
        with self._session_factory() as session:
            session.add(entry)
            session.commit()
            session.refresh(entry)
            self._log_debug(f"Created audit entry {entry.id}: {action}")

        return entry

    def query(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        user: str | None = None,
        env: str | None = None,
        action: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AuditEntry]:
        """Query audit entries with filters.

        Args:
            start_date: Filter entries after this date
            end_date: Filter entries before this date
            user: Filter by user identifier
            env: Filter by environment
            action: Filter by action (e.g., apply_completed)
            limit: Maximum number of entries to return
            offset: Number of entries to skip

        Returns:
            List of matching AuditEntry objects
        """
        with self._session_factory() as session:
            query = session.query(AuditEntry)

            if start_date:
                query = query.filter(AuditEntry.timestamp >= start_date)
            if end_date:
                query = query.filter(AuditEntry.timestamp <= end_date)
            if user:
                query = query.filter(AuditEntry.user_identifier == user)
            if env:
                query = query.filter(AuditEntry.environment == env)
            if action:
                query = query.filter(AuditEntry.action == action)

            query = query.order_by(AuditEntry.timestamp.desc())
            query = query.offset(offset).limit(limit)

            return list(query.all())

    def get_by_id(self, entry_id: int) -> AuditEntry | None:
        """Get an audit entry by ID.

        Args:
            entry_id: Audit entry ID

        Returns:
            AuditEntry or None if not found
        """
        with self._session_factory() as session:
            return session.query(AuditEntry).filter(AuditEntry.id == entry_id).first()

    def verify_integrity(self, entry_id: int) -> bool:
        """Verify the integrity of an audit entry.

        Recalculates the checksum and compares to stored value.

        Args:
            entry_id: Audit entry ID to verify

        Returns:
            True if checksum matches, False if tampered
        """
        entry = self.get_by_id(entry_id)
        if not entry:
            self._log_warning(f"Audit entry {entry_id} not found")
            return False

        if not entry.checksum:
            self._log_warning(f"Audit entry {entry_id} has no checksum")
            return False

        calculated = self._calculate_checksum(entry)
        is_valid = calculated == entry.checksum

        if not is_valid:
            self._log_warning(
                f"Audit entry {entry_id} integrity check failed: "
                f"expected {entry.checksum}, got {calculated}"
            )

        return is_valid

    def _calculate_checksum(self, entry: AuditEntry) -> str:
        """Calculate SHA-256 checksum for an audit entry.

        Args:
            entry: Audit entry to checksum

        Returns:
            Hex-encoded SHA-256 checksum
        """
        # Normalize timestamp for consistent hashing
        # SQLite stores timestamps without timezone, so strip timezone before isoformat
        timestamp_str = None
        if entry.timestamp:
            # Convert to naive UTC for consistent representation
            ts = entry.timestamp
            if ts.tzinfo is not None:
                ts = ts.replace(tzinfo=None)
            timestamp_str = ts.isoformat()

        # Build deterministic data string for hashing
        # Exclude id and checksum fields
        data = {
            "timestamp": timestamp_str,
            "event_type": entry.event_type,
            "user_identifier": entry.user_identifier,
            "environment": entry.environment,
            "command": entry.command,
            "provider": entry.provider,
            "resource_name": entry.resource_name,
            "resource_type": entry.resource_type,
            "action": entry.action,
            "status": entry.status,
            "message": entry.message,
            "ip_address": entry.ip_address,
            "changes_summary": entry.changes_summary,
            "request_metadata": entry.request_metadata,
        }

        # Sort keys for deterministic JSON
        json_str = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(json_str.encode()).hexdigest()

    def _get_ip_address(self) -> str | None:
        """Get local IP address for audit logging.

        Returns:
            IP address string or None
        """
        try:
            # Get hostname and resolve to IP
            hostname = socket.gethostname()
            return socket.gethostbyname(hostname)
        except (OSError, socket.gaierror):
            return None

    def cleanup(self) -> None:
        """Cleanup resources (required by BaseManager)."""
        self._log_debug("AuditLogger cleanup complete")
