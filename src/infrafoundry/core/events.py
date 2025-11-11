"""Event system for InfraFoundry.

Provides hooks for providers and plugins to respond to lifecycle events.
"""

from collections import defaultdict
from collections.abc import Callable
from enum import Enum
from typing import Any

from infrafoundry.core.base_manager import BaseManager


class EventType(str, Enum):
    """Types of events that can be emitted."""

    # Planning phase
    BEFORE_PLAN = "before_plan"
    AFTER_PLAN = "after_plan"
    PLAN_FAILED = "plan_failed"

    # Apply phase
    BEFORE_APPLY = "before_apply"
    AFTER_APPLY = "after_apply"
    APPLY_FAILED = "apply_failed"

    # Destroy phase
    BEFORE_DESTROY = "before_destroy"
    AFTER_DESTROY = "after_destroy"
    DESTROY_FAILED = "destroy_failed"

    # Resource lifecycle
    RESOURCE_PLANNED = "resource_planned"
    RESOURCE_CREATING = "resource_creating"
    RESOURCE_CREATED = "resource_created"
    RESOURCE_UPDATING = "resource_updating"
    RESOURCE_UPDATED = "resource_updated"
    RESOURCE_DELETING = "resource_deleting"
    RESOURCE_DELETED = "resource_deleted"
    RESOURCE_FAILED = "resource_failed"

    # Validation
    VALIDATION_STARTED = "validation_started"
    VALIDATION_PASSED = "validation_passed"
    VALIDATION_FAILED = "validation_failed"

    # Drift detection
    DRIFT_DETECTED = "drift_detected"
    DRIFT_CHECK_STARTED = "drift_check_started"
    DRIFT_CHECK_COMPLETED = "drift_check_completed"

    # Policy enforcement
    POLICY_CHECK_STARTED = "policy_check_started"
    POLICY_VIOLATION = "policy_violation"
    POLICY_CHECK_PASSED = "policy_check_passed"
    POLICY_CHECK_FAILED = "policy_check_failed"


class Event:
    """Event object passed to handlers."""

    def __init__(
        self,
        event_type: EventType,
        environment: str,
        data: dict[str, Any] | None = None,
    ):
        """Initialize event.

        Args:
            event_type: Type of event
            environment: Environment name
            data: Event-specific data
        """
        self.event_type = event_type
        self.environment = environment
        self.data = data or {}

    def __repr__(self) -> str:
        return f"Event({self.event_type}, env={self.environment}, data={self.data})"


EventHandler = Callable[[Event], None]


class EventManager(BaseManager):
    """Manages event subscriptions and emission."""

    def __init__(self):
        """Initialize event manager."""
        # Initialize base manager with logging
        super().__init__()

        self._handlers: dict[EventType, list[EventHandler]] = defaultdict(list)
        self._global_handlers: list[EventHandler] = []
        self._log_debug("EventManager initialized")

    def subscribe(self, event_type: EventType, handler: EventHandler) -> None:
        """Subscribe to a specific event type.

        Args:
            event_type: Event type to subscribe to
            handler: Callback function to invoke when event occurs
        """
        self._handlers[event_type].append(handler)
        self._log_debug(f"Handler subscribed to {event_type}")

    def subscribe_all(self, handler: EventHandler) -> None:
        """Subscribe to all events.

        Args:
            handler: Callback function to invoke for any event
        """
        self._global_handlers.append(handler)

    def unsubscribe(self, event_type: EventType, handler: EventHandler) -> None:
        """Unsubscribe from a specific event type.

        Args:
            event_type: Event type to unsubscribe from
            handler: Handler to remove
        """
        if handler in self._handlers[event_type]:
            self._handlers[event_type].remove(handler)

    def emit(self, event: Event) -> None:
        """Emit an event to all registered handlers.

        Args:
            event: Event to emit
        """
        self._log_debug(f"Emitting event: {event.event_type}")

        # Call specific handlers
        for handler in self._handlers[event.event_type]:
            try:
                handler(event)
            except Exception as e:
                # Log error but don't stop other handlers
                error_msg = f"Error in event handler for {event.event_type}"
                self._log_error(error_msg, e)

        # Call global handlers
        for handler in self._global_handlers:
            try:
                handler(event)
            except Exception as e:
                error_msg = "Error in global event handler"
                self._log_error(error_msg, e)

    def emit_event(
        self,
        event_type: EventType,
        environment: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        """Convenience method to create and emit an event.

        Args:
            event_type: Type of event
            environment: Environment name
            data: Event-specific data
        """
        event = Event(event_type, environment, data)
        self.emit(event)

    def clear(self) -> None:
        """Clear all event handlers."""
        handler_count = self.handler_count()
        self._handlers.clear()
        self._global_handlers.clear()
        self._log_debug(f"Cleared {handler_count} event handlers")

    def handler_count(self, event_type: EventType | None = None) -> int:
        """Get count of registered handlers.

        Args:
            event_type: Specific event type, or None for total count

        Returns:
            Number of handlers registered
        """
        if event_type:
            return len(self._handlers[event_type])
        return sum(len(handlers) for handlers in self._handlers.values()) + len(
            self._global_handlers
        )

    def cleanup(self) -> None:
        """Cleanup resources (required by BaseManager).

        Clears all event handlers.
        """
        self.clear()
        self._log_debug("EventManager cleanup complete")
