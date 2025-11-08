"""Unit tests for EventManager."""

import pytest

from infrafoundry.core.events import Event, EventManager, EventType


@pytest.mark.unit
class TestEventManager:
    """Tests for EventManager."""

    def test_init(self):
        """Test EventManager initialization."""
        manager = EventManager()
        assert manager.handler_count() == 0

    def test_subscribe(self):
        """Test subscribing to events."""
        manager = EventManager()
        called = []

        def handler(event: Event):
            called.append(event.event_type)

        manager.subscribe(EventType.BEFORE_PLAN, handler)
        assert manager.handler_count(EventType.BEFORE_PLAN) == 1

    def test_emit_event(self):
        """Test emitting events."""
        manager = EventManager()
        events_received = []

        def handler(event: Event):
            events_received.append((event.event_type, event.environment, event.data))

        manager.subscribe(EventType.BEFORE_PLAN, handler)
        manager.emit_event(EventType.BEFORE_PLAN, "dev", {"resource": "test-vm"})

        assert len(events_received) == 1
        assert events_received[0][0] == EventType.BEFORE_PLAN
        assert events_received[0][1] == "dev"
        assert events_received[0][2]["resource"] == "test-vm"

    def test_global_handler(self):
        """Test global event handlers."""
        manager = EventManager()
        events = []

        def global_handler(event: Event):
            events.append(event.event_type)

        manager.subscribe_all(global_handler)

        manager.emit_event(EventType.BEFORE_PLAN, "dev", {})
        manager.emit_event(EventType.AFTER_APPLY, "prod", {})

        assert len(events) == 2
        assert EventType.BEFORE_PLAN in events
        assert EventType.AFTER_APPLY in events

    def test_multiple_handlers(self):
        """Test multiple handlers for same event."""
        manager = EventManager()
        calls = []

        def handler1(event: Event):
            calls.append("handler1")

        def handler2(event: Event):
            calls.append("handler2")

        manager.subscribe(EventType.BEFORE_PLAN, handler1)
        manager.subscribe(EventType.BEFORE_PLAN, handler2)

        manager.emit_event(EventType.BEFORE_PLAN, "dev", {})

        assert len(calls) == 2
        assert "handler1" in calls
        assert "handler2" in calls

    def test_handler_error_handling(self):
        """Test that handler errors don't stop other handlers."""
        manager = EventManager()
        calls = []

        def failing_handler(event: Event):
            raise ValueError("Handler error")

        def working_handler(event: Event):
            calls.append("success")

        manager.subscribe(EventType.BEFORE_PLAN, failing_handler)
        manager.subscribe(EventType.BEFORE_PLAN, working_handler)

        # Should not raise exception
        manager.emit_event(EventType.BEFORE_PLAN, "dev", {})

        # Working handler should still be called
        assert "success" in calls

    def test_clear_handlers(self):
        """Test clearing all handlers."""
        manager = EventManager()

        def handler(event: Event):
            pass

        manager.subscribe(EventType.BEFORE_PLAN, handler)
        assert manager.handler_count(EventType.BEFORE_PLAN) == 1

        manager.clear()
        assert manager.handler_count(EventType.BEFORE_PLAN) == 0

    def test_event_object(self):
        """Test Event object creation."""
        event = Event(EventType.BEFORE_PLAN, "dev", {"key": "value"})
        assert event.event_type == EventType.BEFORE_PLAN
        assert event.environment == "dev"
        assert event.data["key"] == "value"

    def test_event_repr(self):
        """Test Event string representation."""
        event = Event(EventType.BEFORE_PLAN, "dev", {"resource": "vm-01"})
        repr_str = repr(event)
        assert "BEFORE_PLAN" in repr_str
        assert "dev" in repr_str

    def test_global_handler_error_handling(self):
        """Test that global handler errors don't stop other handlers."""
        manager = EventManager()
        calls = []

        def failing_global_handler(event: Event):
            raise RuntimeError("Global handler error")

        def working_global_handler(event: Event):
            calls.append("global_success")

        manager.subscribe_all(failing_global_handler)
        manager.subscribe_all(working_global_handler)

        # Should not raise exception
        manager.emit_event(EventType.BEFORE_PLAN, "dev", {})

        # Working global handler should still be called
        assert "global_success" in calls

    def test_unsubscribe(self):
        """Test unsubscribing a handler from an event."""
        manager = EventManager()
        calls = []

        def handler1(event: Event):
            calls.append("handler1")

        def handler2(event: Event):
            calls.append("handler2")

        # Subscribe both handlers
        manager.subscribe(EventType.BEFORE_PLAN, handler1)
        manager.subscribe(EventType.BEFORE_PLAN, handler2)

        # Emit - both should be called
        manager.emit_event(EventType.BEFORE_PLAN, "dev", {})
        assert len(calls) == 2

        # Unsubscribe handler1
        calls.clear()
        manager.unsubscribe(EventType.BEFORE_PLAN, handler1)

        # Emit again - only handler2 should be called
        manager.emit_event(EventType.BEFORE_PLAN, "dev", {})
        assert len(calls) == 1
        assert "handler2" in calls
        assert "handler1" not in calls

    def test_unsubscribe_nonexistent_handler(self):
        """Test unsubscribing a handler that was never subscribed."""
        manager = EventManager()

        def handler(event: Event):
            pass

        # Should not raise exception when unsubscribing non-existent handler
        manager.unsubscribe(EventType.BEFORE_PLAN, handler)
