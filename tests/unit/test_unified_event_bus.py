"""Tests for the unified event bus."""

from unittest.mock import MagicMock, patch

import pytest

from infrafoundry.core.events import (
    Event,
    EventAbortedError,
    EventContext,
    EventResult,
    EventType,
    UnifiedEventBus,
)


class TestEventContext:
    """Tests for EventContext."""

    def test_basic_context(self) -> None:
        """Test creating a basic event context."""
        ctx = EventContext(
            event_type=EventType.BEFORE_PLAN,
            environment="dev",
        )
        assert ctx.event_type == EventType.BEFORE_PLAN
        assert ctx.environment == "dev"
        assert ctx.data == {}
        assert ctx.provider is None

    def test_context_with_all_fields(self) -> None:
        """Test context with all optional fields."""
        ctx = EventContext(
            event_type=EventType.RESOURCE_CREATED,
            environment="prod",
            data={"key": "value"},
            provider="proxmox",
            resource="vm-01",
            deployment_id=123,
        )
        assert ctx.provider == "proxmox"
        assert ctx.resource == "vm-01"
        assert ctx.deployment_id == 123
        assert ctx.data["key"] == "value"


class TestEventResult:
    """Tests for EventResult."""

    def test_successful_result(self) -> None:
        """Test a successful result."""
        result = EventResult(success=True)
        assert result.success
        assert not result.abort
        assert result.continue_workflow

    def test_failed_result(self) -> None:
        """Test a failed result."""
        result = EventResult(success=False, reason="Something went wrong")
        assert not result.success
        assert not result.abort
        assert not result.continue_workflow

    def test_abort_result(self) -> None:
        """Test an abort result."""
        result = EventResult(success=True, abort=True, reason="User requested abort")
        assert result.success
        assert result.abort
        assert not result.continue_workflow


class TestUnifiedEventBusBasic:
    """Basic tests for UnifiedEventBus."""

    def test_initialization(self) -> None:
        """Test bus initializes correctly."""
        bus = UnifiedEventBus()
        assert bus.handler_count() == 0

    def test_subscribe_legacy_callback(self) -> None:
        """Test subscribing legacy callbacks."""
        bus = UnifiedEventBus()
        callback = MagicMock()

        bus.subscribe(EventType.BEFORE_PLAN, callback)
        assert bus.handler_count(EventType.BEFORE_PLAN) == 1

    def test_emit_calls_legacy_callback(self) -> None:
        """Test emitting events calls legacy callbacks."""
        bus = UnifiedEventBus()
        callback = MagicMock()
        bus.subscribe(EventType.BEFORE_PLAN, callback)

        ctx = EventContext(EventType.BEFORE_PLAN, "dev")
        bus.emit(ctx)

        callback.assert_called_once()
        event = callback.call_args[0][0]
        assert isinstance(event, Event)
        assert event.event_type == EventType.BEFORE_PLAN

    def test_subscribe_all(self) -> None:
        """Test subscribing to all events."""
        bus = UnifiedEventBus()
        callback = MagicMock()
        bus.subscribe_all(callback)

        bus.emit_event(EventType.BEFORE_PLAN, "dev")
        bus.emit_event(EventType.AFTER_APPLY, "dev")

        assert callback.call_count == 2

    def test_unsubscribe(self) -> None:
        """Test unsubscribing callbacks."""
        bus = UnifiedEventBus()
        callback = MagicMock()
        bus.subscribe(EventType.BEFORE_PLAN, callback)
        bus.unsubscribe(EventType.BEFORE_PLAN, callback)

        bus.emit_event(EventType.BEFORE_PLAN, "dev")
        callback.assert_not_called()

    def test_clear(self) -> None:
        """Test clearing all handlers."""
        bus = UnifiedEventBus()
        bus.subscribe(EventType.BEFORE_PLAN, MagicMock())
        bus.subscribe(EventType.AFTER_APPLY, MagicMock())

        bus.clear()
        assert bus.handler_count() == 0


class TestUnifiedEventBusHandlers:
    """Tests for handler registration and execution."""

    def test_register_python_handler(self) -> None:
        """Test registering a Python handler."""
        bus = UnifiedEventBus()

        with patch("importlib.import_module") as mock_import:
            mock_module = MagicMock()
            mock_module.handle = MagicMock(return_value=EventResult(success=True))
            mock_import.return_value = mock_module

            bus.register_handler(
                EventType.AFTER_PLAN,
                {"type": "python", "module": "test.module"},
            )

            ctx = EventContext(EventType.AFTER_PLAN, "dev")
            results = bus.emit(ctx)

            assert len(results) == 1
            assert results[0].success

    def test_register_invalid_handler(self) -> None:
        """Test registering an invalid handler raises error."""
        bus = UnifiedEventBus()

        with pytest.raises(ValueError, match="Unknown handler type"):
            bus.register_handler(
                EventType.BEFORE_PLAN,
                {"type": "invalid_type"},
            )

    def test_script_handler_requires_script_field(self) -> None:
        """Test script handler validation."""
        bus = UnifiedEventBus()

        with pytest.raises(ValueError, match="'script' field"):
            bus.register_handler(
                EventType.BEFORE_PLAN,
                {"type": "script"},  # Missing script field
            )

    def test_webhook_handler_requires_url_field(self) -> None:
        """Test webhook handler validation."""
        bus = UnifiedEventBus()

        with pytest.raises(ValueError, match="'url' field"):
            bus.register_handler(
                EventType.BEFORE_PLAN,
                {"type": "webhook"},  # Missing url field
            )


class TestUnifiedEventBusAbort:
    """Tests for abort handling."""

    def test_abort_raises_exception(self) -> None:
        """Test that abort results raise EventAbortedError for abortable events."""
        bus = UnifiedEventBus()

        with patch("importlib.import_module") as mock_import:
            mock_module = MagicMock()
            mock_module.handle = MagicMock(
                return_value=EventResult(success=True, abort=True, reason="Test abort")
            )
            mock_import.return_value = mock_module

            bus.register_handler(
                EventType.BEFORE_PLAN,  # BEFORE_PLAN is abortable
                {"type": "python", "module": "test.module"},
            )

            ctx = EventContext(EventType.BEFORE_PLAN, "dev")

            with pytest.raises(EventAbortedError) as exc_info:
                bus.emit(ctx)

            assert exc_info.value.event_type == EventType.BEFORE_PLAN
            assert "Test abort" in str(exc_info.value)

    def test_abort_ignored_for_non_abortable_events(self) -> None:
        """Test that abort is ignored for non-abortable events."""
        bus = UnifiedEventBus()

        with patch("importlib.import_module") as mock_import:
            mock_module = MagicMock()
            mock_module.handle = MagicMock(return_value=EventResult(success=True, abort=True))
            mock_import.return_value = mock_module

            bus.register_handler(
                EventType.AFTER_PLAN,  # AFTER_PLAN is NOT abortable
                {"type": "python", "module": "test.module"},
            )

            ctx = EventContext(EventType.AFTER_PLAN, "dev")
            # Should not raise
            results = bus.emit(ctx)
            assert results[0].abort

    def test_abort_can_be_disabled(self) -> None:
        """Test that abort_on_failure=False prevents exception."""
        bus = UnifiedEventBus()

        with patch("importlib.import_module") as mock_import:
            mock_module = MagicMock()
            mock_module.handle = MagicMock(return_value=EventResult(success=True, abort=True))
            mock_import.return_value = mock_module

            bus.register_handler(
                EventType.BEFORE_PLAN,
                {"type": "python", "module": "test.module"},
            )

            ctx = EventContext(EventType.BEFORE_PLAN, "dev")
            # Should not raise with abort_on_failure=False
            results = bus.emit(ctx, abort_on_failure=False)
            assert results[0].abort


class TestUnifiedEventBusLoadConfig:
    """Tests for loading configuration."""

    def test_load_config(self) -> None:
        """Test loading handlers from config dict."""
        bus = UnifiedEventBus()

        with patch("importlib.import_module") as mock_import:
            mock_module = MagicMock()
            mock_module.handle = MagicMock(return_value=EventResult(success=True))
            mock_import.return_value = mock_module

            bus.load_config(
                {
                    "after_plan": [
                        {"type": "python", "module": "hooks.approval"},
                    ],
                }
            )

            assert bus.handler_count(EventType.AFTER_PLAN) == 1

    def test_load_config_unknown_event_type(self) -> None:
        """Test loading config with unknown event type logs warning."""
        bus = UnifiedEventBus()

        # Should not raise, just log warning
        bus.load_config(
            {
                "unknown_event": [
                    {"type": "python", "module": "test"},
                ],
            }
        )

        assert bus.handler_count() == 0


class TestBackwardCompatibility:
    """Tests for backward compatibility with legacy EventManager API."""

    def test_event_manager_alias(self) -> None:
        """Test EventManager is an alias for UnifiedEventBus."""
        from infrafoundry.core.events import EventManager

        bus = EventManager()
        assert isinstance(bus, UnifiedEventBus)

    def test_emit_event_convenience_method(self) -> None:
        """Test emit_event convenience method."""
        bus = UnifiedEventBus()
        callback = MagicMock()
        bus.subscribe(EventType.DRIFT_DETECTED, callback)

        bus.emit_event(
            EventType.DRIFT_DETECTED,
            "prod",
            data={"drift": True},
            provider="proxmox",
        )

        callback.assert_called_once()
        event = callback.call_args[0][0]
        assert event.context.provider == "proxmox"
        assert event.context.data["drift"] is True
