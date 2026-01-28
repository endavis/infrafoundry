"""Database models for audit trail."""

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from sqlalchemy import JSON, DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from infrafoundry.core.state.models import Base


class AuditStatus(str, Enum):
    """Status of an audited operation."""

    SUCCESS = "success"
    FAILED = "failed"
    IN_PROGRESS = "in_progress"


class AuditEntry(Base):
    """Immutable audit log entry for compliance tracking.

    Records all infrastructure operations with tamper-detection checksums.
    Entries should never be modified after creation - use verify_integrity()
    to detect any tampering.

    Attributes:
        id: Primary key
        timestamp: When the operation occurred (UTC)
        event_type: Type of event (e.g., BEFORE_APPLY, AFTER_PLAN)
        user_identifier: Who performed the operation
        environment: Target environment (e.g., dev, prod)
        command: CLI command (plan, apply, destroy)
        provider: Provider name (e.g., proxmox, oci)
        resource_name: Specific resource affected
        resource_type: Type of resource (e.g., vms, firewall_rules)
        action: Audit action (e.g., plan_started, apply_completed)
        status: Operation status (success, failed, in_progress)
        message: Additional context or error message
        ip_address: Source IP address if available
        changes_summary: JSON summary of changes made
        request_metadata: JSON with CLI args, git commit, etc.
        checksum: SHA-256 checksum for tamper detection
    """

    __tablename__ = "audit_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(UTC), index=True
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    user_identifier: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    environment: Mapped[str | None] = mapped_column(String(100), index=True)
    command: Mapped[str | None] = mapped_column(String(50))
    provider: Mapped[str | None] = mapped_column(String(50))
    resource_name: Mapped[str | None] = mapped_column(String(200))
    resource_type: Mapped[str | None] = mapped_column(String(50))
    action: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    message: Mapped[str | None] = mapped_column(Text)
    ip_address: Mapped[str | None] = mapped_column(String(45))
    changes_summary: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    request_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    checksum: Mapped[str | None] = mapped_column(String(64))

    # Composite indexes for common query patterns
    __table_args__ = (
        Index("ix_audit_env_timestamp", "environment", "timestamp"),
        Index("ix_audit_user_timestamp", "user_identifier", "timestamp"),
        Index("ix_audit_action_timestamp", "action", "timestamp"),
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert entry to dictionary for export/display.

        Returns:
            Dictionary with all entry fields
        """
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "event_type": self.event_type,
            "user_identifier": self.user_identifier,
            "environment": self.environment,
            "command": self.command,
            "provider": self.provider,
            "resource_name": self.resource_name,
            "resource_type": self.resource_type,
            "action": self.action,
            "status": self.status,
            "message": self.message,
            "ip_address": self.ip_address,
            "changes_summary": self.changes_summary,
            "request_metadata": self.request_metadata,
            "checksum": self.checksum,
        }

    def __repr__(self) -> str:
        return (
            f"<AuditEntry(id={self.id}, action={self.action}, "
            f"user={self.user_identifier}, env={self.environment})>"
        )
