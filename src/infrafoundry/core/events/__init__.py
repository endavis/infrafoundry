"""Unified event system for InfraFoundry.

This module provides a unified event bus that replaces both the legacy
EventManager (Python callbacks) and HookManager (shell scripts) with
a single, flexible event system.

Features:
- Multiple handler types: Python, script, webhook
- Handlers can abort workflows for certain events
- Rich event context with provider, resource, deployment info
- Backward compatible with legacy EventManager API

Example usage:
    from infrafoundry.core.events import UnifiedEventBus, EventType, EventContext

    # Create event bus
    bus = UnifiedEventBus()

    # Register handlers from config
    bus.load_config({
        "AFTER_PLAN": [
            {"type": "python", "module": "hooks.approval"},
        ],
    })

    # Emit an event
    context = EventContext(
        event_type=EventType.AFTER_PLAN,
        environment="dev",
        data={"resources": 5},
    )
    results = bus.emit(context)

    # Legacy API (backward compatible)
    bus.subscribe(EventType.DRIFT_DETECTED, my_callback)
    bus.emit_event(EventType.DRIFT_DETECTED, "prod", {"drift": True})
"""

from infrafoundry.core.events.bus import (
    EventAbortedError,
    EventHandlerError,
    EventManager,
    UnifiedEventBus,
)
from infrafoundry.core.events.context import (
    Event,
    EventContext,
    EventHandler,
    EventPayload,
    EventResult,
)
from infrafoundry.core.events.types import (
    ABORTABLE_EVENTS,
    LIFECYCLE_STAGES,
    EventType,
    HandlerType,
)

__all__ = [
    "ABORTABLE_EVENTS",
    "LIFECYCLE_STAGES",
    "Event",
    "EventAbortedError",
    "EventContext",
    "EventHandler",
    "EventHandlerError",
    "EventManager",
    "EventPayload",
    "EventResult",
    "EventType",
    "HandlerType",
    "UnifiedEventBus",
]
