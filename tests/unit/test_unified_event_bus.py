"""Tests for the unified event bus."""

from typing import Any
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


class TestBaseHandlerMatchesResources:
    """Tests for BaseHandler.matches_resources()."""

    def _make_handler(self, config: dict[str, Any]) -> Any:
        """Create a concrete handler subclass for testing."""
        from infrafoundry.core.events.handlers.base import BaseHandler

        class StubHandler(BaseHandler):
            def execute(self, context: EventContext) -> EventResult:
                return EventResult(success=True, handler_name=self.name)

            def validate_config(self) -> list[str]:
                return []

        return StubHandler(config)

    def test_no_config_filter_returns_true(self) -> None:
        """Handler without resources config fires for any target."""
        handler = self._make_handler({"name": "no-filter"})
        assert handler.matches_resources(["res-a", "res-b"]) is True

    def test_no_target_resources_returns_true(self) -> None:
        """Handler with resources config fires when target is None (no -r)."""
        handler = self._make_handler({"name": "filtered", "resources": ["res-a"]})
        assert handler.matches_resources(None) is True

    def test_intersection_returns_true(self) -> None:
        """Handler fires when target_resources overlaps handler resources."""
        handler = self._make_handler({"name": "filtered", "resources": ["res-a", "res-b"]})
        assert handler.matches_resources(["res-b", "res-c"]) is True

    def test_no_intersection_returns_false(self) -> None:
        """Handler skipped when no overlap between handler and target resources."""
        handler = self._make_handler({"name": "filtered", "resources": ["res-a"]})
        assert handler.matches_resources(["res-x", "res-y"]) is False

    def test_empty_config_resources_returns_true(self) -> None:
        """Empty resources list treated as no filter (fires for all)."""
        handler = self._make_handler({"name": "empty-filter", "resources": []})
        assert handler.matches_resources(["res-a"]) is True

    def test_empty_target_resources_returns_true(self) -> None:
        """Empty target list has no overlap, but empty handler list fires."""
        handler = self._make_handler({"name": "no-filter"})
        assert handler.matches_resources([]) is True


class TestResourceFilteredEmit:
    """Tests for resource-scoped filtering in emit()."""

    def test_filtered_handler_skipped_unfiltered_fires(self) -> None:
        """Only matching handlers execute when target_resources is set."""
        bus = UnifiedEventBus()

        with patch("importlib.import_module") as mock_import:
            call_count: dict[str, int] = {"ontap": 0, "aiqum": 0}

            def make_result(name: str) -> EventResult:
                call_count[name] += 1
                return EventResult(success=True, handler_name=name)

            # Two separate modules for two handlers
            ontap_module = MagicMock()
            ontap_module.handle = MagicMock(side_effect=lambda ctx: make_result("ontap"))

            aiqum_module = MagicMock()
            aiqum_module.handle = MagicMock(side_effect=lambda ctx: make_result("aiqum"))

            def import_side_effect(module_name: str) -> MagicMock:
                if module_name == "hooks.ontap":
                    return ontap_module
                return aiqum_module

            mock_import.side_effect = import_side_effect

            # Handler scoped to ontap resources
            bus.register_handler(
                EventType.AFTER_APPLY,
                {
                    "type": "python",
                    "module": "hooks.ontap",
                    "name": "ontap-handler",
                    "resources": ["ontapcl-01", "ontapcl-02"],
                },
            )

            # Handler scoped to aiqum resources
            bus.register_handler(
                EventType.AFTER_APPLY,
                {
                    "type": "python",
                    "module": "hooks.aiqum",
                    "name": "aiqum-handler",
                    "resources": ["aiqum-console"],
                },
            )

            # Emit targeting only ontap resources
            ctx = EventContext(
                EventType.AFTER_APPLY,
                "prod",
                target_resources=["ontapcl-01", "ontapcl-02"],
            )
            results = bus.emit(ctx)

            # Only ontap handler should have fired
            assert len(results) == 1
            assert results[0].handler_name == "ontap-handler"
            assert call_count["ontap"] == 1
            assert call_count["aiqum"] == 0

    def test_handler_without_filter_fires_regardless(self) -> None:
        """Handler with no resources config fires for any target_resources."""
        bus = UnifiedEventBus()

        with patch("importlib.import_module") as mock_import:
            mock_module = MagicMock()
            mock_module.handle = MagicMock(
                return_value=EventResult(success=True, handler_name="global")
            )
            mock_import.return_value = mock_module

            bus.register_handler(
                EventType.AFTER_APPLY,
                {"type": "python", "module": "hooks.global", "name": "global-handler"},
            )

            ctx = EventContext(
                EventType.AFTER_APPLY,
                "prod",
                target_resources=["res-a"],
            )
            results = bus.emit(ctx)

            assert len(results) == 1
            assert results[0].handler_name == "global-handler"

    def test_config_loading_preserves_resources_field(self) -> None:
        """Resources field in handler config is preserved through load_config."""
        bus = UnifiedEventBus()

        with patch("importlib.import_module") as mock_import:
            mock_module = MagicMock()
            mock_module.handle = MagicMock(return_value=EventResult(success=True))
            mock_import.return_value = mock_module

            bus.load_config(
                {
                    "after_apply": [
                        {
                            "type": "python",
                            "module": "hooks.scoped",
                            "resources": ["res-a", "res-b"],
                        },
                    ],
                }
            )

            handlers = bus._handlers[EventType.AFTER_APPLY]
            assert len(handlers) == 1
            assert handlers[0].config["resources"] == ["res-a", "res-b"]


class TestEventContextTargetResources:
    """Tests for target_resources field on EventContext."""

    def test_default_is_none(self) -> None:
        """target_resources defaults to None."""
        ctx = EventContext(EventType.BEFORE_PLAN, "dev")
        assert ctx.target_resources is None

    def test_set_via_constructor(self) -> None:
        """target_resources can be set via constructor."""
        ctx = EventContext(
            EventType.BEFORE_PLAN,
            "dev",
            target_resources=["res-a", "res-b"],
        )
        assert ctx.target_resources == ["res-a", "res-b"]

    def test_emit_event_passes_target_resources(self) -> None:
        """emit_event convenience method passes target_resources to context."""
        bus = UnifiedEventBus()
        callback = MagicMock()
        bus.subscribe(EventType.BEFORE_APPLY, callback)

        bus.emit_event(
            EventType.BEFORE_APPLY,
            "prod",
            target_resources=["res-a"],
        )

        callback.assert_called_once()
        event = callback.call_args[0][0]
        assert event.context.target_resources == ["res-a"]
