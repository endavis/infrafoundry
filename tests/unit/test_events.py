"""Unit tests for EventManager and event handlers."""

import stat
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from infrafoundry.core.events import Event, EventHandlerError, EventManager, EventType
from infrafoundry.core.events.bus import UnifiedEventBus
from infrafoundry.core.events.context import EventContext, EventResult
from infrafoundry.core.events.handlers.script import ScriptHandler


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
        assert "before_plan" in repr_str
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

    def test_handler_error_metadata(self):
        """Ensure EventHandlerError exposes handler name and message."""

        def failing_handler(event: Event) -> None:
            raise ValueError("boom")

        event = Event(EventType.BEFORE_PLAN, "dev")
        error = EventHandlerError(failing_handler, event, ValueError("boom"))
        assert "failing_handler" in str(error)
        assert error.handler_name.endswith("failing_handler")

    def test_unsubscribe_nonexistent_handler(self):
        """Test unsubscribing a handler that was never subscribed."""
        manager = EventManager()

        def handler(event: Event):
            pass

        # Should not raise exception when unsubscribing non-existent handler
        manager.unsubscribe(EventType.BEFORE_PLAN, handler)


@pytest.mark.unit
class TestScriptHandlerEnvironment:
    """Tests for ScriptHandler._prepare_environment."""

    def test_runner_env_var_injected_when_present(self, tmp_path: Path):
        """INFRAFOUNDRY_RUNNER is set when context.runner is provided."""
        handler = ScriptHandler({"script": "test.sh"}, config_base_dir=tmp_path)
        context = EventContext(
            event_type=EventType.RUNNER_COMPLETED,
            environment="dev",
            runner="terraform",
            provider="proxmox",
        )
        env = handler._prepare_environment(context, tmp_path)
        assert env["INFRAFOUNDRY_RUNNER"] == "terraform"

    def test_runner_env_var_omitted_when_none(self, tmp_path: Path):
        """INFRAFOUNDRY_RUNNER is not set when context.runner is None."""
        handler = ScriptHandler({"script": "test.sh"}, config_base_dir=tmp_path)
        context = EventContext(
            event_type=EventType.BEFORE_PLAN,
            environment="dev",
        )
        env = handler._prepare_environment(context, tmp_path)
        assert "INFRAFOUNDRY_RUNNER" not in env


def _make_script(tmp_path: Path, name: str, content: str) -> Path:
    """Create an executable script in the expected directory structure.

    Args:
        tmp_path: Pytest temporary directory
        name: Script filename
        content: Script content

    Returns:
        Path to the script relative to envs/dev/
    """
    env_dir = tmp_path / "envs" / "dev"
    env_dir.mkdir(parents=True, exist_ok=True)
    script = env_dir / name
    script.write_text(content)
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return Path(name)


@pytest.mark.unit
class TestScriptHandlerStreaming:
    """Tests for ScriptHandler real-time output streaming."""

    def test_streaming_prints_stdout_to_console(self, tmp_path: Path):
        """Stdout lines are printed to console in real-time."""
        script_rel = _make_script(
            tmp_path,
            "echo.sh",
            "#!/bin/bash\necho line1\necho line2\n",
        )
        console = MagicMock()
        handler = ScriptHandler(
            {"script": str(script_rel)},
            config_base_dir=tmp_path,
            console=console,
        )
        context = EventContext(
            event_type=EventType.AFTER_APPLY,
            environment="dev",
        )
        result = handler.execute(context)

        assert result.success
        assert "line1" in result.stdout
        assert "line2" in result.stdout
        # Console should have been called with each line
        print_calls = [str(c) for c in console.print.call_args_list]
        assert any("line1" in c for c in print_calls)
        assert any("line2" in c for c in print_calls)

    def test_streaming_prints_stderr_with_red_style(self, tmp_path: Path):
        """Stderr lines are printed to console with red styling."""
        script_rel = _make_script(
            tmp_path,
            "stderr.sh",
            "#!/bin/bash\necho err_msg >&2\n",
        )
        console = MagicMock()
        handler = ScriptHandler(
            {"script": str(script_rel)},
            config_base_dir=tmp_path,
            console=console,
        )
        context = EventContext(
            event_type=EventType.AFTER_APPLY,
            environment="dev",
        )
        result = handler.execute(context)

        assert "err_msg" in result.stderr
        print_calls = [str(c) for c in console.print.call_args_list]
        assert any("[red]" in c and "err_msg" in c for c in print_calls)

    def test_stdout_and_stderr_captured_in_result(self, tmp_path: Path):
        """EventResult still contains full stdout and stderr."""
        script_rel = _make_script(
            tmp_path,
            "both.sh",
            "#!/bin/bash\necho out_line\necho err_line >&2\n",
        )
        console = MagicMock()
        handler = ScriptHandler(
            {"script": str(script_rel)},
            config_base_dir=tmp_path,
            console=console,
        )
        context = EventContext(
            event_type=EventType.AFTER_APPLY,
            environment="dev",
        )
        result = handler.execute(context)

        assert result.success
        assert "out_line" in result.stdout
        assert "err_line" in result.stderr

    def test_no_console_backward_compat(self, tmp_path: Path):
        """ScriptHandler works without console (backward compatibility)."""
        script_rel = _make_script(
            tmp_path,
            "compat.sh",
            "#!/bin/bash\necho hello\n",
        )
        handler = ScriptHandler(
            {"script": str(script_rel)},
            config_base_dir=tmp_path,
        )
        assert handler.console is None

        context = EventContext(
            event_type=EventType.AFTER_APPLY,
            environment="dev",
        )
        result = handler.execute(context)

        assert result.success
        assert "hello" in result.stdout

    def test_timeout_kills_process_returns_partial(self, tmp_path: Path):
        """Timeout kills the process and returns partial output."""
        script_rel = _make_script(
            tmp_path,
            "slow.sh",
            "#!/bin/bash\necho partial_out\nsleep 60\n",
        )
        console = MagicMock()
        handler = ScriptHandler(
            {"script": str(script_rel), "timeout": 1},
            config_base_dir=tmp_path,
            console=console,
        )
        context = EventContext(
            event_type=EventType.AFTER_APPLY,
            environment="dev",
        )
        result = handler.execute(context)

        assert not result.success
        assert "Timeout" in (result.reason or "")
        assert "partial_out" in result.stdout

    def test_empty_output(self, tmp_path: Path):
        """Empty output produces empty strings in result."""
        script_rel = _make_script(
            tmp_path,
            "empty.sh",
            "#!/bin/bash\n",
        )
        handler = ScriptHandler(
            {"script": str(script_rel)},
            config_base_dir=tmp_path,
        )
        context = EventContext(
            event_type=EventType.AFTER_APPLY,
            environment="dev",
        )
        result = handler.execute(context)

        assert result.success
        assert result.stdout == ""
        assert result.stderr == ""


@pytest.mark.unit
class TestPrintHandlerResultStreaming:
    """Tests for _print_handler_result with streaming behavior."""

    def test_skips_reprinting_for_streamed_script_handler(self):
        """Output is not re-printed for ScriptHandler with console."""
        console = MagicMock()
        bus = UnifiedEventBus(console=console)

        handler = ScriptHandler(
            {"type": "script", "script": "test.sh"},
            console=console,
        )
        result = EventResult(
            success=True,
            stdout="already streamed line",
            handler_name="test",
        )

        console.reset_mock()
        bus._print_handler_result(handler, result)

        # Should print summary but NOT re-print stdout
        calls = [str(c) for c in console.print.call_args_list]
        assert any("completed" in c for c in calls)
        assert not any("already streamed line" in c for c in calls)

    def test_skips_reprinting_stderr_for_streamed_script_handler(self):
        """Stderr is not re-printed for failed ScriptHandler with console."""
        console = MagicMock()
        bus = UnifiedEventBus(console=console)

        handler = ScriptHandler(
            {"type": "script", "script": "test.sh"},
            console=console,
        )
        result = EventResult(
            success=False,
            reason="Exit code: 1",
            stdout="some output",
            stderr="some error",
            handler_name="test",
        )

        console.reset_mock()
        bus._print_handler_result(handler, result)

        calls = [str(c) for c in console.print.call_args_list]
        assert any("failed" in c for c in calls)
        assert not any("some output" in c for c in calls)
        assert not any("some error" in c for c in calls)

    def test_prints_output_for_non_script_handler(self):
        """Output is still printed for non-script handlers."""
        from infrafoundry.core.events.handlers.python import PythonHandler

        console = MagicMock()
        bus = UnifiedEventBus(console=console)

        handler = PythonHandler({"type": "python", "module": "test"})
        result = EventResult(
            success=True,
            stdout="python handler output",
            handler_name="test",
        )

        console.reset_mock()
        bus._print_handler_result(handler, result)

        calls = [str(c) for c in console.print.call_args_list]
        assert any("python handler output" in c for c in calls)

    def test_prints_output_for_script_handler_without_console(self):
        """Output is printed for ScriptHandler without console (no streaming)."""
        console = MagicMock()
        bus = UnifiedEventBus(console=console)

        handler = ScriptHandler(
            {"type": "script", "script": "test.sh"},
            console=None,
        )
        result = EventResult(
            success=True,
            stdout="buffered output",
            handler_name="test",
        )

        console.reset_mock()
        bus._print_handler_result(handler, result)

        calls = [str(c) for c in console.print.call_args_list]
        assert any("buffered output" in c for c in calls)


@pytest.mark.unit
class TestPackageEventsIntegration:
    """Tests for package events wiring through orchestrator."""

    def test_package_events_registered_after_resource_load(self, tmp_path: Path):
        """Verify orchestrator registers package events after resource loading."""
        from unittest.mock import Mock, patch

        from infrafoundry.core.config import ConfigManager
        from infrafoundry.core.events import EventManager

        # Create env structure with a package that has events
        envs_dir = tmp_path / "envs"
        dev_dir = envs_dir / "dev"
        dev_dir.mkdir(parents=True)
        (dev_dir / "settings.yaml").write_text("name: dev\ndescription: Test\n")

        proxmox_dir = dev_dir / "proxmox"
        proxmox_dir.mkdir()

        pkg_dir = proxmox_dir / "my-pkg"
        pkg_dir.mkdir()
        import yaml

        manifest = {
            "name": "my-pkg",
            "events": {"AFTER_APPLY": [{"type": "webhook", "url": "https://example.com/hook"}]},
        }
        with open(pkg_dir / "infrafoundry.yml", "w") as f:
            yaml.dump(manifest, f)

        config_manager = ConfigManager(envs_dir)
        event_manager = EventManager()

        # Spy on load_config
        original_load_config = event_manager.load_config
        load_config_calls: list[dict] = []

        def spy_load_config(config: dict) -> None:
            load_config_calls.append(config)
            original_load_config(config)

        event_manager.load_config = spy_load_config  # type: ignore[assignment]

        # Patch Orchestrator to avoid full initialization
        with (
            patch("infrafoundry.core.orchestrator.StateManager"),
            patch("infrafoundry.core.orchestrator.PolicyEngine"),
            patch("infrafoundry.core.orchestrator.NotificationManager"),
            patch("infrafoundry.core.orchestrator.AuditLogger"),
            patch("infrafoundry.core.orchestrator.ProviderRegistryService") as mock_prs,
        ):
            mock_prs.return_value.providers = {}
            mock_runner_registry = Mock()
            mock_runner_registry.list_runners.return_value = []
            mock_prs.return_value.runner_registry = mock_runner_registry

            from infrafoundry.core.orchestrator import Orchestrator

            orch = Orchestrator(
                config_manager=config_manager,
                output_dir=tmp_path / "generated",
                event_manager=event_manager,
            )

            # Call _load_resources which should trigger package event registration
            orch._load_resources("dev")

            # Verify load_config was called with package events
            assert len(load_config_calls) > 0
            # Find the call that has AFTER_APPLY
            pkg_event_calls = [c for c in load_config_calls if "AFTER_APPLY" in c]
            assert len(pkg_event_calls) == 1
            assert pkg_event_calls[0]["AFTER_APPLY"][0]["type"] == "webhook"
