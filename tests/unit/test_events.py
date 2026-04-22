"""Unit tests for EventManager and event handlers."""

import json
import shutil
import stat
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from infrafoundry.core.events import Event, EventHandlerError, EventManager, EventType
from infrafoundry.core.events.bus import UnifiedEventBus
from infrafoundry.core.events.context import EventContext, EventResult
from infrafoundry.core.events.handlers.script import ScriptHandler, _build_remote_bash


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


def _make_dump_env_script(tmp_path: Path, name: str) -> tuple[Path, Path]:
    """Create an executable script that dumps its environment to a file.

    Returns:
        (script_rel_path, output_file_path) where ``script_rel_path`` is the
        filename relative to ``envs/dev/`` and ``output_file_path`` is the
        absolute path the script writes to.
    """
    env_dir = tmp_path / "envs" / "dev"
    env_dir.mkdir(parents=True, exist_ok=True)
    out_file = tmp_path / "env-dump.txt"
    script = env_dir / name
    script.write_text(f"#!/bin/bash\nenv > {out_file}\n")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return Path(name), out_file


def _parse_env_dump(path: Path) -> dict[str, str]:
    """Parse a file produced by ``env`` into a dict."""
    result: dict[str, str] = {}
    for line in path.read_text().splitlines():
        if "=" in line:
            k, _, v = line.partition("=")
            result[k] = v
    return result


@pytest.mark.unit
class TestScriptHandlerInventoryInjection:
    """Tests for INFRAFOUNDRY_INVENTORY / INFRAFOUNDRY_PACKAGE_DIR injection from _package_dir."""

    def test_injects_inventory_env_when_package_dir_has_generated_inventory(self, tmp_path: Path):
        """INFRAFOUNDRY_INVENTORY is set when _package_dir contains .generated-inventory.yml."""
        script_rel, out_file = _make_dump_env_script(tmp_path, "dump.sh")

        # Create a fake package dir with a generated inventory file
        pkg_dir = tmp_path / "envs" / "dev" / "proxmox" / "my-pkg"
        pkg_dir.mkdir(parents=True, exist_ok=True)
        inventory_path = pkg_dir / ".generated-inventory.yml"
        inventory_path.write_text("groups: {}\n")

        handler = ScriptHandler(
            {"script": str(script_rel), "_package_dir": str(pkg_dir)},
            config_base_dir=tmp_path,
        )
        context = EventContext(
            event_type=EventType.AFTER_APPLY,
            environment="dev",
        )
        result = handler.execute(context)
        assert result.success, result.reason

        env = _parse_env_dump(out_file)
        assert env.get("INFRAFOUNDRY_INVENTORY") == str(inventory_path)

    def test_does_not_inject_inventory_when_file_missing(self, tmp_path: Path):
        """INFRAFOUNDRY_INVENTORY is not set when _package_dir has no inventory file."""
        script_rel, out_file = _make_dump_env_script(tmp_path, "dump-no-inv.sh")

        pkg_dir = tmp_path / "envs" / "dev" / "proxmox" / "no-inv-pkg"
        pkg_dir.mkdir(parents=True, exist_ok=True)
        # No .generated-inventory.yml created

        handler = ScriptHandler(
            {"script": str(script_rel), "_package_dir": str(pkg_dir)},
            config_base_dir=tmp_path,
        )
        context = EventContext(
            event_type=EventType.AFTER_APPLY,
            environment="dev",
        )
        result = handler.execute(context)
        assert result.success, result.reason

        env = _parse_env_dump(out_file)
        assert "INFRAFOUNDRY_INVENTORY" not in env

    def test_does_not_inject_inventory_when_package_dir_absent(self, tmp_path: Path):
        """INFRAFOUNDRY_INVENTORY is unset when config has no _package_dir (env-level handler)."""
        script_rel, out_file = _make_dump_env_script(tmp_path, "dump-no-pkg.sh")

        handler = ScriptHandler(
            {"script": str(script_rel)},
            config_base_dir=tmp_path,
        )
        context = EventContext(
            event_type=EventType.AFTER_APPLY,
            environment="dev",
        )
        result = handler.execute(context)
        assert result.success, result.reason

        env = _parse_env_dump(out_file)
        assert "INFRAFOUNDRY_INVENTORY" not in env

    def test_injects_package_dir_env_when_package_dir_configured(self, tmp_path: Path):
        """INFRAFOUNDRY_PACKAGE_DIR is set to the configured _package_dir."""
        script_rel, out_file = _make_dump_env_script(tmp_path, "dump-pkg-dir.sh")

        pkg_dir = tmp_path / "envs" / "dev" / "proxmox" / "some-pkg"
        pkg_dir.mkdir(parents=True, exist_ok=True)

        handler = ScriptHandler(
            {"script": str(script_rel), "_package_dir": str(pkg_dir)},
            config_base_dir=tmp_path,
        )
        context = EventContext(
            event_type=EventType.AFTER_APPLY,
            environment="dev",
        )
        result = handler.execute(context)
        assert result.success, result.reason

        env = _parse_env_dump(out_file)
        assert env.get("INFRAFOUNDRY_PACKAGE_DIR") == str(pkg_dir)

    def test_does_not_inject_package_dir_when_not_configured(self, tmp_path: Path):
        """INFRAFOUNDRY_PACKAGE_DIR is unset when config has no _package_dir."""
        script_rel, out_file = _make_dump_env_script(tmp_path, "dump-no-pkg-dir.sh")

        handler = ScriptHandler(
            {"script": str(script_rel)},
            config_base_dir=tmp_path,
        )
        context = EventContext(
            event_type=EventType.AFTER_APPLY,
            environment="dev",
        )
        result = handler.execute(context)
        assert result.success, result.reason

        env = _parse_env_dump(out_file)
        assert "INFRAFOUNDRY_PACKAGE_DIR" not in env


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


def _make_fake_process(
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
    wait_raises: Exception | None = None,
) -> MagicMock:
    """Build a mock subprocess.Popen result used by jumphost reexec tests.

    The ``_read_stream`` helper iterates line-by-line with ``for line in
    stream``, so ``stdout``/``stderr`` are exposed as iterators over the
    configured content. ``stdin`` supports ``write`` and ``close``.
    """
    import io

    proc = MagicMock()
    proc.stdout = io.StringIO(stdout)
    proc.stderr = io.StringIO(stderr)
    proc.stdin = MagicMock()
    proc.stdin.write = MagicMock()
    proc.stdin.close = MagicMock()
    proc.returncode = returncode
    if wait_raises is not None:
        proc.wait = MagicMock(side_effect=wait_raises)
    else:
        proc.wait = MagicMock(return_value=returncode)
    proc.kill = MagicMock()
    return proc


@pytest.mark.unit
class TestScriptHandlerJumphostReexec:
    """Tests for ScriptHandler jumphost reexec dispatch (#544)."""

    def _handler(self, tmp_path: Path, script_name: str = "run.sh") -> tuple[ScriptHandler, Path]:
        """Create a ScriptHandler with a minimal executable script on disk."""
        env_dir = tmp_path / "envs" / "dev"
        env_dir.mkdir(parents=True, exist_ok=True)
        script = env_dir / script_name
        script.write_text("#!/bin/bash\necho hi\n")
        script.chmod(script.stat().st_mode | stat.S_IEXEC)
        handler = ScriptHandler(
            {"script": script_name},
            config_base_dir=tmp_path,
        )
        return handler, script

    def _context(self, **vars: object) -> EventContext:
        """Build an EventContext carrying the given package variables."""
        return EventContext(
            event_type=EventType.AFTER_APPLY,
            environment="dev",
            package_variables=dict(vars),
        )

    def test_no_jumphost_runs_locally(self, tmp_path: Path):
        """Empty/missing jumphost takes the local subprocess path."""
        handler, script = self._handler(tmp_path)
        context = self._context()  # no jumphost

        with patch("infrafoundry.core.events.handlers.script.subprocess.Popen") as mock_popen:
            mock_popen.return_value = _make_fake_process(returncode=0)
            result = handler.execute(context)

        assert mock_popen.call_count == 1
        args, _ = mock_popen.call_args
        # Local path: first positional is [str(script_path)]
        assert args[0] == [str(script)]
        assert result.success

    def test_jumphost_set_triggers_reexec(self, tmp_path: Path):
        """jumphost variable causes ssh-based remote execution."""
        handler, _ = self._handler(tmp_path)
        context = self._context(jumphost="ansible@jump", other="val")

        run_result = MagicMock(returncode=0, stdout="", stderr="")
        with (
            patch(
                "infrafoundry.core.events.handlers.script.subprocess.run",
                return_value=run_result,
            ),
            patch("infrafoundry.core.events.handlers.script.subprocess.Popen") as mock_popen,
        ):
            mock_popen.return_value = _make_fake_process(returncode=0)
            result = handler.execute(context)

        assert result.success
        assert mock_popen.call_count == 1
        cmd = mock_popen.call_args[0][0]
        assert cmd[0] == "ssh"
        assert "StrictHostKeyChecking=no" in cmd
        assert "ansible@jump" in cmd
        # The last arg is the remote bash command string
        assert "INFRAFOUNDRY_ON_JUMPHOST=1" in cmd[-1]
        assert "bash /tmp/infrafoundry-" in cmd[-1]

    def test_jumphost_stripped_from_forwarded_json(self, tmp_path: Path):
        """Package vars JSON piped to stdin excludes 'jumphost'."""
        handler, _ = self._handler(tmp_path)
        context = self._context(jumphost="jh", foo="bar", num=7)

        run_result = MagicMock(returncode=0, stdout="", stderr="")
        fake_proc = _make_fake_process(returncode=0)
        with (
            patch(
                "infrafoundry.core.events.handlers.script.subprocess.run",
                return_value=run_result,
            ),
            patch(
                "infrafoundry.core.events.handlers.script.subprocess.Popen",
                return_value=fake_proc,
            ),
        ):
            handler.execute(context)

        fake_proc.stdin.write.assert_called_once()
        written = fake_proc.stdin.write.call_args[0][0]
        parsed = json.loads(written)
        assert "jumphost" not in parsed
        assert parsed["foo"] == "bar"
        assert parsed["num"] == 7
        fake_proc.stdin.close.assert_called_once()

    def test_infrafoundry_on_jumphost_env_set_in_remote_command(self, tmp_path: Path):
        """Remote bash command sets INFRAFOUNDRY_ON_JUMPHOST=1 for recursion guard."""
        handler, _ = self._handler(tmp_path)
        context = self._context(jumphost="jh")

        run_result = MagicMock(returncode=0, stdout="", stderr="")
        with (
            patch(
                "infrafoundry.core.events.handlers.script.subprocess.run",
                return_value=run_result,
            ),
            patch(
                "infrafoundry.core.events.handlers.script.subprocess.Popen",
                return_value=_make_fake_process(returncode=0),
            ) as mock_popen,
        ):
            handler.execute(context)

        remote_bash = mock_popen.call_args[0][0][-1]
        assert "INFRAFOUNDRY_ON_JUMPHOST=1" in remote_bash
        assert 'INFRAFOUNDRY_PACKAGE_VARS="$(cat)"' in remote_bash

    def test_remote_exit_code_propagated(self, tmp_path: Path):
        """Non-zero remote returncode surfaces as failure with abort."""
        handler, _ = self._handler(tmp_path)
        context = self._context(jumphost="jh")

        run_result = MagicMock(returncode=0, stdout="", stderr="")
        with (
            patch(
                "infrafoundry.core.events.handlers.script.subprocess.run",
                return_value=run_result,
            ),
            patch(
                "infrafoundry.core.events.handlers.script.subprocess.Popen",
                return_value=_make_fake_process(returncode=17),
            ),
        ):
            result = handler.execute(context)

        assert result.success is False
        assert result.abort is True
        assert result.data.get("returncode") == 17
        assert "17" in (result.reason or "")

    def test_rsync_failure(self, tmp_path: Path):
        """Rsync failure returns a clear reason and never launches the remote script."""
        handler, _ = self._handler(tmp_path)
        context = self._context(jumphost="jh")

        mkdir_ok = MagicMock(returncode=0, stdout="", stderr="")
        rsync_fail = MagicMock(returncode=23, stdout="", stderr="permission denied")
        cleanup_ok = MagicMock(returncode=0, stdout=b"", stderr=b"")

        def run_side_effect(cmd, *_args, **_kwargs):
            if cmd[0] == "rsync":
                return rsync_fail
            if cmd[0] == "ssh" and cmd[-1].startswith("mkdir"):
                return mkdir_ok
            return cleanup_ok

        with (
            patch(
                "infrafoundry.core.events.handlers.script.subprocess.run",
                side_effect=run_side_effect,
            ),
            patch("infrafoundry.core.events.handlers.script.subprocess.Popen") as mock_popen,
        ):
            result = handler.execute(context)

        assert result.success is False
        assert "rsync" in (result.reason or "")
        assert mock_popen.call_count == 0

    def test_ssh_mkdir_failure(self, tmp_path: Path):
        """mkdir failure returns a clear reason and never runs rsync or remote."""
        handler, _ = self._handler(tmp_path)
        context = self._context(jumphost="jh")

        mkdir_fail = MagicMock(returncode=255, stdout="", stderr="host unreachable")

        def run_side_effect(cmd, *_args, **_kwargs):
            if cmd[0] == "ssh" and cmd[-1].startswith("mkdir"):
                return mkdir_fail
            # rsync/cleanup should not be reached
            raise AssertionError(f"unexpected call: {cmd}")

        with (
            patch(
                "infrafoundry.core.events.handlers.script.subprocess.run",
                side_effect=run_side_effect,
            ),
            patch("infrafoundry.core.events.handlers.script.subprocess.Popen") as mock_popen,
        ):
            result = handler.execute(context)

        assert result.success is False
        assert "mkdir" in (result.reason or "")
        assert mock_popen.call_count == 0

    def test_cleanup_runs_on_success(self, tmp_path: Path):
        """Cleanup ssh rm -rf fires after a successful remote run."""
        handler, _ = self._handler(tmp_path)
        context = self._context(jumphost="jh")

        calls: list[list[str]] = []

        def run_side_effect(cmd, *_args, **_kwargs):
            calls.append(list(cmd))
            return MagicMock(returncode=0, stdout=b"", stderr=b"")

        with (
            patch(
                "infrafoundry.core.events.handlers.script.subprocess.run",
                side_effect=run_side_effect,
            ),
            patch(
                "infrafoundry.core.events.handlers.script.subprocess.Popen",
                return_value=_make_fake_process(returncode=0),
            ),
        ):
            result = handler.execute(context)

        assert result.success is True
        cleanup_calls = [c for c in calls if c[0] == "ssh" and "rm -rf" in c[-1]]
        assert len(cleanup_calls) == 1

    def test_cleanup_runs_on_failure(self, tmp_path: Path):
        """Cleanup ssh rm -rf fires even when remote script returns non-zero."""
        handler, _ = self._handler(tmp_path)
        context = self._context(jumphost="jh")

        calls: list[list[str]] = []

        def run_side_effect(cmd, *_args, **_kwargs):
            calls.append(list(cmd))
            return MagicMock(returncode=0, stdout=b"", stderr=b"")

        with (
            patch(
                "infrafoundry.core.events.handlers.script.subprocess.run",
                side_effect=run_side_effect,
            ),
            patch(
                "infrafoundry.core.events.handlers.script.subprocess.Popen",
                return_value=_make_fake_process(returncode=5),
            ),
        ):
            result = handler.execute(context)

        assert result.success is False
        cleanup_calls = [c for c in calls if c[0] == "ssh" and "rm -rf" in c[-1]]
        assert len(cleanup_calls) == 1

    def test_cleanup_error_ignored(self, tmp_path: Path):
        """Non-zero cleanup return code does not affect the main EventResult."""
        handler, _ = self._handler(tmp_path)
        context = self._context(jumphost="jh")

        def run_side_effect(cmd, *_args, **_kwargs):
            if cmd[0] == "ssh" and "rm -rf" in cmd[-1]:
                return MagicMock(returncode=1, stdout=b"", stderr=b"cleanup failed")
            return MagicMock(returncode=0, stdout=b"", stderr=b"")

        with (
            patch(
                "infrafoundry.core.events.handlers.script.subprocess.run",
                side_effect=run_side_effect,
            ),
            patch(
                "infrafoundry.core.events.handlers.script.subprocess.Popen",
                return_value=_make_fake_process(returncode=3),
            ),
        ):
            result = handler.execute(context)

        # Reflects real remote exit code, not cleanup's rc
        assert result.data.get("returncode") == 3
        assert result.success is False

    def test_stream_output_from_remote(self, tmp_path: Path):
        """stdout/stderr from the remote Popen are captured in EventResult."""
        handler, _ = self._handler(tmp_path)
        context = self._context(jumphost="jh")

        run_result = MagicMock(returncode=0, stdout="", stderr="")
        with (
            patch(
                "infrafoundry.core.events.handlers.script.subprocess.run",
                return_value=run_result,
            ),
            patch(
                "infrafoundry.core.events.handlers.script.subprocess.Popen",
                return_value=_make_fake_process(
                    returncode=0,
                    stdout="out-line-1\nout-line-2\n",
                    stderr="err-line-1\n",
                ),
            ),
        ):
            result = handler.execute(context)

        assert "out-line-1" in result.stdout
        assert "out-line-2" in result.stdout
        assert "err-line-1" in result.stderr

    def test_timeout_kills_ssh_subprocess(self, tmp_path: Path):
        """Timeout on remote wait kills ssh process and still runs cleanup."""
        handler, _ = self._handler(tmp_path)
        handler.config["timeout"] = 1
        context = self._context(jumphost="jh")

        cleanup_seen: list[list[str]] = []

        def run_side_effect(cmd, *_args, **_kwargs):
            if cmd[0] == "ssh" and "rm -rf" in cmd[-1]:
                cleanup_seen.append(list(cmd))
            return MagicMock(returncode=0, stdout=b"", stderr=b"")

        fake_proc = _make_fake_process(
            returncode=0,
            wait_raises=subprocess.TimeoutExpired(cmd="ssh", timeout=1),
        )
        with (
            patch(
                "infrafoundry.core.events.handlers.script.subprocess.run",
                side_effect=run_side_effect,
            ),
            patch(
                "infrafoundry.core.events.handlers.script.subprocess.Popen",
                return_value=fake_proc,
            ),
        ):
            result = handler.execute(context)

        fake_proc.kill.assert_called_once()
        assert result.success is False
        assert "Timeout" in (result.reason or "")
        assert len(cleanup_seen) == 1

    def test_infrafoundry_on_jumphost_already_set_skips_reexec(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """If INFRAFOUNDRY_ON_JUMPHOST is already set, local path is taken."""
        handler, script = self._handler(tmp_path)
        context = self._context(jumphost="jh")

        monkeypatch.setenv("INFRAFOUNDRY_ON_JUMPHOST", "1")
        with patch("infrafoundry.core.events.handlers.script.subprocess.Popen") as mock_popen:
            mock_popen.return_value = _make_fake_process(returncode=0)
            result = handler.execute(context)

        assert mock_popen.call_count == 1
        # Local path signature: first arg list is [str(script)]
        assert mock_popen.call_args[0][0] == [str(script)]
        assert result.success

    def test_remote_bash_contains_var_reexport(self, tmp_path: Path):
        """Remote wrapper re-exports each package var as INFRAFOUNDRY_VAR_<key>.

        Regression for #639: the jumphost path previously only forwarded
        INFRAFOUNDRY_PACKAGE_VARS (JSON), breaking scripts that consume the
        documented INFRAFOUNDRY_VAR_<key> contract under ``set -u``.
        """
        handler, _ = self._handler(tmp_path)
        context = self._context(jumphost="jh", server_ip="10.0.0.1", cluster_name="k3s")

        run_result = MagicMock(returncode=0, stdout="", stderr="")
        with (
            patch(
                "infrafoundry.core.events.handlers.script.subprocess.run",
                return_value=run_result,
            ),
            patch(
                "infrafoundry.core.events.handlers.script.subprocess.Popen",
                return_value=_make_fake_process(returncode=0),
            ) as mock_popen,
        ):
            handler.execute(context)

        remote_bash = mock_popen.call_args[0][0][-1]
        assert "INFRAFOUNDRY_VAR_$k" in remote_bash
        assert "python3 -c '" in remote_bash
        assert "command -v python3" in remote_bash
        assert "\\0" in remote_bash
        # Regression for #641: must not silently depend on jq.
        assert "jq " not in remote_bash

    def test_remote_wrapper_sets_var_env_via_real_shell(self, tmp_path: Path):
        """End-to-end: the wrapper under bash+python3 populates INFRAFOUNDRY_VAR_<key>.

        Executes the generated remote bash string against a local bash+python3
        so the shell-level re-export loop is exercised for real, not merely
        asserted against the string.
        """
        if shutil.which("python3") is None or shutil.which("bash") is None:
            pytest.skip("requires python3 and bash")

        remote_dir = tmp_path
        script = remote_dir / "dump.sh"
        script.write_text(
            '#!/bin/bash\nset -u\necho "ip=${INFRAFOUNDRY_VAR_server_ip}"\n'
            'echo "name=${INFRAFOUNDRY_VAR_cluster_name}"\n'
            'echo "num=${INFRAFOUNDRY_VAR_count}"\n'
            'echo "pkg=${INFRAFOUNDRY_PACKAGE_VARS}"\n'
        )
        script.chmod(script.stat().st_mode | stat.S_IEXEC)

        remote_bash = _build_remote_bash(str(remote_dir), "dump.sh")
        pkg_vars = {
            "server_ip": "10.0.0.1",
            "cluster_name": "k3s-test",
            "count": 3,
            "agents": [{"name": "a1"}],  # object/array — only in JSON blob
        }
        proc = subprocess.run(  # nosec B603
            ["bash", "-c", remote_bash],
            input=json.dumps(pkg_vars),
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert proc.returncode == 0, f"stderr: {proc.stderr}"
        assert "ip=10.0.0.1" in proc.stdout
        assert "name=k3s-test" in proc.stdout
        assert "num=3" in proc.stdout
        # Full JSON remains available (incl. the array value that scalars skip).
        assert '"agents"' in proc.stdout

    def test_remote_wrapper_fails_fast_without_python3(self, tmp_path: Path):
        """Regression for #641: wrapper fails fast with a clear error when python3 is absent.

        Previously (PR #640) the wrapper silently depended on ``jq`` — when
        missing, the subshell emitted ``jq: command not found`` but the outer
        bash kept going and the inner script surfaced an unbound-variable
        error that didn't point at the real cause.
        """
        bash_path = shutil.which("bash")
        if bash_path is None:
            pytest.skip("requires bash")

        script = tmp_path / "dump.sh"
        script.write_text("#!/bin/bash\necho unreachable\n")
        script.chmod(script.stat().st_mode | stat.S_IEXEC)

        remote_bash = _build_remote_bash(str(tmp_path), "dump.sh")
        # Use absolute path to bash and clear PATH so the wrapper's
        # `command -v python3` check cannot find python3.
        proc = subprocess.run(  # nosec B603
            [bash_path, "-c", remote_bash],
            input="{}",
            capture_output=True,
            text=True,
            env={"PATH": ""},
            timeout=10,
        )

        assert proc.returncode == 127
        assert "python3 is required" in proc.stderr
        assert "unreachable" not in proc.stdout

    def test_remote_bash_exports_warnings_file(self, tmp_path: Path):
        """When a warnings_file is provided, the wrapper seeds and exports it.

        Regression for #661: the jumphost path must propagate
        INFRAFOUNDRY_WARNINGS_FILE to remote scripts so they can emit
        warnings the orchestrator can later scp back and summarize.
        """
        warnings_path = "/tmp/infrafoundry-abcd/warnings.jsonl"  # nosec B108
        remote_bash = _build_remote_bash(str(tmp_path), "dump.sh", warnings_file=warnings_path)

        # Seed: `: > "<path>"` creates/truncates so scp-back always finds it.
        assert f': > "{warnings_path}"' in remote_bash
        # Export: downstream processes inherit the env var.
        assert f'export INFRAFOUNDRY_WARNINGS_FILE="{warnings_path}"' in remote_bash
        # Without the arg, the wrapper must not emit the warnings plumbing.
        plain = _build_remote_bash(str(tmp_path), "dump.sh")
        assert "INFRAFOUNDRY_WARNINGS_FILE" not in plain

    def test_remote_wrapper_appends_to_warnings_file_on_disk(self, tmp_path: Path):
        """End-to-end: inner script appends to $INFRAFOUNDRY_WARNINGS_FILE on disk.

        Runs the real bash+python3 wrapper and asserts that a warning
        appended inside the inner script lands on disk at the expected
        path, exercising the seed+export plumbing.
        """
        if shutil.which("python3") is None or shutil.which("bash") is None:
            pytest.skip("requires python3 and bash")

        remote_dir = tmp_path
        warnings_path = tmp_path / "warnings.jsonl"
        script = remote_dir / "emit.sh"
        script.write_text(
            "#!/bin/bash\nset -u\n"
            'echo \'{"source":"remote","message":"hello"}\' '
            '>> "$INFRAFOUNDRY_WARNINGS_FILE"\n'
        )
        script.chmod(script.stat().st_mode | stat.S_IEXEC)

        remote_bash = _build_remote_bash(
            str(remote_dir), "emit.sh", warnings_file=str(warnings_path)
        )
        proc = subprocess.run(  # nosec B603
            ["bash", "-c", remote_bash],
            input=json.dumps({}),  # no package vars
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert proc.returncode == 0, f"stderr: {proc.stderr}"
        assert warnings_path.exists()
        content = warnings_path.read_text(encoding="utf-8")
        assert '"source":"remote"' in content
        assert '"message":"hello"' in content


@pytest.mark.unit
class TestScriptHandlerOutputs:
    """Tests for the ``outputs:`` pull-back affordance on ScriptHandler (#660).

    Declared ``outputs`` let blueprint authors tell the framework which
    artifact files a script produces and where the operator wants them
    to land. Local execution uses ``shutil.copy2``; jumphost execution
    uses ``scp``. All pull-back failures are non-fatal warnings.
    """

    def _handler(
        self,
        tmp_path: Path,
        outputs: list[dict[str, str]] | None = None,
        script_content: str = "#!/bin/bash\necho hi\n",
    ) -> tuple[ScriptHandler, Path]:
        """Build a ScriptHandler with optional ``outputs`` config."""
        env_dir = tmp_path / "envs" / "dev"
        env_dir.mkdir(parents=True, exist_ok=True)
        script = env_dir / "run.sh"
        script.write_text(script_content)
        script.chmod(script.stat().st_mode | stat.S_IEXEC)
        config: dict = {"script": "run.sh"}
        if outputs is not None:
            config["outputs"] = outputs
        handler = ScriptHandler(config, config_base_dir=tmp_path)
        return handler, script

    def _context(self, **vars: object) -> EventContext:
        return EventContext(
            event_type=EventType.AFTER_APPLY,
            environment="dev",
            package_variables=dict(vars),
        )

    # -- Validation -----------------------------------------------------

    def test_validate_config_accepts_absent_outputs(self, tmp_path: Path):
        """Missing ``outputs`` field is valid (back-compat default)."""
        handler, _ = self._handler(tmp_path)
        assert handler.validate_config() == []

    def test_validate_config_accepts_empty_outputs_list(self, tmp_path: Path):
        """Empty ``outputs: []`` is valid."""
        handler, _ = self._handler(tmp_path, outputs=[])
        assert handler.validate_config() == []

    def test_validate_config_rejects_non_list_outputs(self, tmp_path: Path):
        """``outputs`` as a non-list produces a validation error."""
        env_dir = tmp_path / "envs" / "dev"
        env_dir.mkdir(parents=True, exist_ok=True)
        script = env_dir / "run.sh"
        script.write_text("#!/bin/bash\n")
        script.chmod(script.stat().st_mode | stat.S_IEXEC)
        handler = ScriptHandler(
            {"script": "run.sh", "outputs": "not-a-list"},
            config_base_dir=tmp_path,
        )
        errors = handler.validate_config()
        assert any("outputs must be a list" in e for e in errors)

    def test_validate_config_rejects_entry_missing_source(self, tmp_path: Path):
        """An entry without ``source`` is invalid."""
        handler, _ = self._handler(tmp_path, outputs=[{"dest": "/tmp/x"}])
        errors = handler.validate_config()
        assert any("source" in e for e in errors)

    def test_validate_config_rejects_entry_missing_dest(self, tmp_path: Path):
        """An entry without ``dest`` is invalid."""
        handler, _ = self._handler(tmp_path, outputs=[{"source": "/tmp/x"}])
        errors = handler.validate_config()
        assert any("dest" in e for e in errors)

    def test_validate_config_rejects_non_mapping_entry(self, tmp_path: Path):
        """A list entry that isn't a mapping is invalid."""
        handler, _ = self._handler(
            tmp_path,
            outputs=["just-a-string"],  # type: ignore[list-item]
        )
        errors = handler.validate_config()
        assert any("outputs[0]" in e and "mapping" in e for e in errors)

    # -- Absent / empty are no-ops --------------------------------------

    def test_outputs_absent_is_noop(self, tmp_path: Path):
        """With no ``outputs`` config, no copy/scp happens."""
        handler, _ = self._handler(tmp_path)
        context = self._context()
        with patch("infrafoundry.core.events.handlers.script.shutil.copy2") as mock_copy:
            result = handler.execute(context)
        assert result.success
        assert mock_copy.call_count == 0

    def test_outputs_empty_list_is_noop(self, tmp_path: Path):
        """``outputs: []`` behaves identically to absent."""
        handler, _ = self._handler(tmp_path, outputs=[])
        context = self._context()
        with patch("infrafoundry.core.events.handlers.script.shutil.copy2") as mock_copy:
            result = handler.execute(context)
        assert result.success
        assert mock_copy.call_count == 0

    # -- Local execution paths ------------------------------------------

    def test_local_copies_source_to_dest(self, tmp_path: Path):
        """On success, source is copied to dest with different paths."""
        src = tmp_path / "src.txt"
        src.write_text("hello world")
        dst = tmp_path / "out" / "dst.txt"
        handler, _ = self._handler(
            tmp_path,
            outputs=[{"source": str(src), "dest": str(dst)}],
            script_content="#!/bin/bash\necho ok\n",
        )
        result = handler.execute(self._context())
        assert result.success
        assert dst.exists()
        assert dst.read_text() == "hello world"

    def test_local_same_path_is_noop(self, tmp_path: Path):
        """When source == dest, no copy is attempted."""
        both = tmp_path / "file.txt"
        both.write_text("unchanged")
        handler, _ = self._handler(
            tmp_path,
            outputs=[{"source": str(both), "dest": str(both)}],
        )
        with patch("infrafoundry.core.events.handlers.script.shutil.copy2") as mock_copy:
            result = handler.execute(self._context())
        assert result.success
        assert mock_copy.call_count == 0
        # File is unmodified.
        assert both.read_text() == "unchanged"

    def test_local_missing_source_warns(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Missing source after success: warning emitted, handler still succeeds."""
        warnings_file = tmp_path / "warnings.jsonl"
        monkeypatch.setenv("INFRAFOUNDRY_WARNINGS_FILE", str(warnings_file))
        missing = tmp_path / "does-not-exist.txt"
        dst = tmp_path / "dst.txt"
        handler, _ = self._handler(
            tmp_path,
            outputs=[{"source": str(missing), "dest": str(dst)}],
        )
        result = handler.execute(self._context())
        assert result.success
        assert not dst.exists()
        assert warnings_file.exists()
        content = warnings_file.read_text()
        assert "output source not found" in content
        assert "script_handler_outputs" in content

    def test_local_relative_path_warns_and_skips(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """Non-absolute rendered paths warn and skip the entry."""
        warnings_file = tmp_path / "warnings.jsonl"
        monkeypatch.setenv("INFRAFOUNDRY_WARNINGS_FILE", str(warnings_file))
        # dest is a bare relative name; source is absolute.
        src = tmp_path / "src.txt"
        src.write_text("x")
        handler, _ = self._handler(
            tmp_path,
            outputs=[{"source": str(src), "dest": "foo-relative"}],
        )
        with patch("infrafoundry.core.events.handlers.script.shutil.copy2") as mock_copy:
            result = handler.execute(self._context())
        assert result.success
        assert mock_copy.call_count == 0
        assert warnings_file.exists()
        assert "dest must be an absolute path" in warnings_file.read_text()

    def test_local_template_vars_rendered(self, tmp_path: Path):
        """Jinja2 templates in source/dest resolve against package vars."""
        src = tmp_path / "k3s-prod.yaml"
        src.write_text("# kubeconfig")
        dst = tmp_path / "prod.yaml"
        handler, _ = self._handler(
            tmp_path,
            outputs=[
                {
                    "source": str(tmp_path) + "/k3s-{{ cluster_name }}.yaml",
                    "dest": str(tmp_path) + "/{{ cluster_name }}.yaml",
                }
            ],
        )
        result = handler.execute(self._context(cluster_name="prod"))
        assert result.success
        assert dst.exists()
        assert dst.read_text() == "# kubeconfig"

    def test_local_creates_dest_parent_dir(self, tmp_path: Path):
        """Nonexistent dest parent dir is created automatically."""
        src = tmp_path / "src.txt"
        src.write_text("payload")
        dst = tmp_path / "nested" / "deeper" / "dst.txt"
        assert not dst.parent.exists()
        handler, _ = self._handler(
            tmp_path,
            outputs=[{"source": str(src), "dest": str(dst)}],
        )
        result = handler.execute(self._context())
        assert result.success
        assert dst.exists()
        assert dst.read_text() == "payload"

    def test_local_outputs_skipped_on_script_failure(self, tmp_path: Path):
        """Non-zero script exit skips outputs processing entirely."""
        src = tmp_path / "src.txt"
        src.write_text("payload")
        dst = tmp_path / "dst.txt"
        handler, _ = self._handler(
            tmp_path,
            outputs=[{"source": str(src), "dest": str(dst)}],
            script_content="#!/bin/bash\nexit 1\n",
        )
        result = handler.execute(self._context())
        assert result.success is False
        assert not dst.exists()

    # -- Jumphost (scp) paths -------------------------------------------

    def _jumphost_run_ok(self, scp_calls: list[list[str]] | None = None):
        """Build a subprocess.run side effect that records scp invocations."""

        def side_effect(cmd, *_args, **_kwargs):
            if cmd[0] == "scp" and scp_calls is not None:
                scp_calls.append(list(cmd))
            return MagicMock(returncode=0, stdout=b"", stderr=b"")

        return side_effect

    def test_remote_scp_invoked_on_success(self, tmp_path: Path):
        """A successful remote run triggers one scp per output."""
        handler, _ = self._handler(
            tmp_path,
            outputs=[{"source": "/tmp/remote/out.txt", "dest": str(tmp_path / "out.txt")}],
        )
        context = self._context(jumphost="jump@host")
        scp_calls: list[list[str]] = []
        with (
            patch(
                "infrafoundry.core.events.handlers.script.subprocess.run",
                side_effect=self._jumphost_run_ok(scp_calls),
            ),
            patch(
                "infrafoundry.core.events.handlers.script.subprocess.Popen",
                return_value=_make_fake_process(returncode=0),
            ),
        ):
            result = handler.execute(context)
        assert result.success
        assert len(scp_calls) == 1
        scp_cmd = scp_calls[0]
        assert scp_cmd[0] == "scp"
        assert "jump@host:/tmp/remote/out.txt" in scp_cmd
        assert str(tmp_path / "out.txt") in scp_cmd

    def test_remote_scp_skipped_on_script_failure(self, tmp_path: Path):
        """A failed remote run skips scp entirely."""
        handler, _ = self._handler(
            tmp_path,
            outputs=[{"source": "/tmp/remote/out.txt", "dest": str(tmp_path / "out.txt")}],
        )
        context = self._context(jumphost="jump@host")
        scp_calls: list[list[str]] = []
        with (
            patch(
                "infrafoundry.core.events.handlers.script.subprocess.run",
                side_effect=self._jumphost_run_ok(scp_calls),
            ),
            patch(
                "infrafoundry.core.events.handlers.script.subprocess.Popen",
                return_value=_make_fake_process(returncode=7),
            ),
        ):
            result = handler.execute(context)
        assert result.success is False
        assert scp_calls == []

    def test_remote_scp_failure_warns_but_handler_succeeds(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """A non-zero scp returncode surfaces as a warning, not a handler failure."""
        warnings_file = tmp_path / "warnings.jsonl"
        monkeypatch.setenv("INFRAFOUNDRY_WARNINGS_FILE", str(warnings_file))
        handler, _ = self._handler(
            tmp_path,
            outputs=[{"source": "/tmp/remote/out.txt", "dest": str(tmp_path / "out.txt")}],
        )
        context = self._context(jumphost="jump@host")

        def run_side_effect(cmd, *_args, **_kwargs):
            if cmd[0] == "scp":
                return MagicMock(returncode=1, stdout=b"", stderr=b"no such file")
            return MagicMock(returncode=0, stdout=b"", stderr=b"")

        with (
            patch(
                "infrafoundry.core.events.handlers.script.subprocess.run",
                side_effect=run_side_effect,
            ),
            patch(
                "infrafoundry.core.events.handlers.script.subprocess.Popen",
                return_value=_make_fake_process(returncode=0),
            ),
        ):
            result = handler.execute(context)

        assert result.success
        assert warnings_file.exists()
        content = warnings_file.read_text()
        assert "scp of output" in content
        assert "no such file" in content

    def test_remote_multiple_outputs_all_attempted(self, tmp_path: Path):
        """Multiple outputs: one failure does not skip subsequent entries."""
        handler, _ = self._handler(
            tmp_path,
            outputs=[
                {"source": "/tmp/remote/first.txt", "dest": str(tmp_path / "first.txt")},
                {"source": "/tmp/remote/second.txt", "dest": str(tmp_path / "second.txt")},
            ],
        )
        context = self._context(jumphost="jump@host")
        scp_calls: list[list[str]] = []

        def run_side_effect(cmd, *_args, **_kwargs):
            if cmd[0] == "scp":
                scp_calls.append(list(cmd))
                # First scp fails, second succeeds.
                if "first.txt" in cmd[-2]:
                    return MagicMock(returncode=1, stdout=b"", stderr=b"err")
                return MagicMock(returncode=0, stdout=b"", stderr=b"")
            return MagicMock(returncode=0, stdout=b"", stderr=b"")

        with (
            patch(
                "infrafoundry.core.events.handlers.script.subprocess.run",
                side_effect=run_side_effect,
            ),
            patch(
                "infrafoundry.core.events.handlers.script.subprocess.Popen",
                return_value=_make_fake_process(returncode=0),
            ),
        ):
            result = handler.execute(context)

        assert result.success
        # Filter out any scp from the unrelated warnings-collector plumbing
        # (only present when INFRAFOUNDRY_WARNINGS_FILE is set); the outputs
        # pull-back uses /tmp/remote/* sources.
        output_scps = [c for c in scp_calls if "/tmp/remote/" in c[-2]]
        assert len(output_scps) == 2
        assert any("first.txt" in c[-2] for c in output_scps)
        assert any("second.txt" in c[-2] for c in output_scps)

    def test_remote_cleanup_runs_after_outputs_processing(self, tmp_path: Path):
        """Remote cleanup (rm -rf) always fires after scp attempts."""
        handler, _ = self._handler(
            tmp_path,
            outputs=[{"source": "/tmp/remote/out.txt", "dest": str(tmp_path / "out.txt")}],
        )
        context = self._context(jumphost="jump@host")
        order: list[str] = []

        def run_side_effect(cmd, *_args, **_kwargs):
            if cmd[0] == "scp":
                order.append("scp")
                # Make scp fail so we also verify cleanup still runs after a
                # non-fatal pull-back error.
                return MagicMock(returncode=1, stdout=b"", stderr=b"boom")
            if cmd[0] == "ssh" and "rm -rf" in cmd[-1]:
                order.append("cleanup")
            return MagicMock(returncode=0, stdout=b"", stderr=b"")

        with (
            patch(
                "infrafoundry.core.events.handlers.script.subprocess.run",
                side_effect=run_side_effect,
            ),
            patch(
                "infrafoundry.core.events.handlers.script.subprocess.Popen",
                return_value=_make_fake_process(returncode=0),
            ),
        ):
            result = handler.execute(context)

        assert result.success
        # scp must run before the remote cleanup so the remote tmp dir
        # still contains the artifact when scp executes.
        assert order == ["scp", "cleanup"]

    def test_remote_ssh_opts_forwarded_to_scp(self, tmp_path: Path):
        """scp inherits the same StrictHostKeyChecking=no used by the handler."""
        handler, _ = self._handler(
            tmp_path,
            outputs=[{"source": "/tmp/remote/out.txt", "dest": str(tmp_path / "out.txt")}],
        )
        context = self._context(jumphost="jump@host")
        scp_calls: list[list[str]] = []
        with (
            patch(
                "infrafoundry.core.events.handlers.script.subprocess.run",
                side_effect=self._jumphost_run_ok(scp_calls),
            ),
            patch(
                "infrafoundry.core.events.handlers.script.subprocess.Popen",
                return_value=_make_fake_process(returncode=0),
            ),
        ):
            handler.execute(context)
        assert len(scp_calls) == 1
        assert "-o" in scp_calls[0]
        assert "StrictHostKeyChecking=no" in scp_calls[0]

    # -- Extra error-handling paths -------------------------------------

    def test_local_template_error_warns_and_skips(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """A malformed Jinja2 template surfaces a warning and skips the entry."""
        warnings_file = tmp_path / "warnings.jsonl"
        monkeypatch.setenv("INFRAFOUNDRY_WARNINGS_FILE", str(warnings_file))
        # Unclosed expression -> jinja2.TemplateSyntaxError.
        handler, _ = self._handler(
            tmp_path,
            outputs=[{"source": "/tmp/{{ broken", "dest": str(tmp_path / "x.txt")}],
        )
        with patch("infrafoundry.core.events.handlers.script.shutil.copy2") as mock_copy:
            result = handler.execute(self._context())
        assert result.success
        assert mock_copy.call_count == 0
        assert warnings_file.exists()
        assert "failed to render output template" in warnings_file.read_text()

    def test_local_source_relative_warns_and_skips(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """A non-absolute rendered source also triggers a warning."""
        warnings_file = tmp_path / "warnings.jsonl"
        monkeypatch.setenv("INFRAFOUNDRY_WARNINGS_FILE", str(warnings_file))
        handler, _ = self._handler(
            tmp_path,
            outputs=[{"source": "relative.txt", "dest": str(tmp_path / "x.txt")}],
        )
        with patch("infrafoundry.core.events.handlers.script.shutil.copy2") as mock_copy:
            result = handler.execute(self._context())
        assert result.success
        assert mock_copy.call_count == 0
        assert "source must be an absolute path" in warnings_file.read_text()

    def test_local_copy_oserror_warns(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """A raising ``shutil.copy2`` surfaces as a warning (not a failure)."""
        warnings_file = tmp_path / "warnings.jsonl"
        monkeypatch.setenv("INFRAFOUNDRY_WARNINGS_FILE", str(warnings_file))
        src = tmp_path / "src.txt"
        src.write_text("hi")
        dst = tmp_path / "dst.txt"
        handler, _ = self._handler(
            tmp_path,
            outputs=[{"source": str(src), "dest": str(dst)}],
        )
        with patch(
            "infrafoundry.core.events.handlers.script.shutil.copy2",
            side_effect=PermissionError("denied"),
        ):
            result = handler.execute(self._context())
        assert result.success
        content = warnings_file.read_text()
        assert "failed to copy" in content

    def test_remote_scp_oserror_warns(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """An ``OSError`` from ``subprocess.run`` during scp is also a warning."""
        warnings_file = tmp_path / "warnings.jsonl"
        monkeypatch.setenv("INFRAFOUNDRY_WARNINGS_FILE", str(warnings_file))
        handler, _ = self._handler(
            tmp_path,
            outputs=[{"source": "/tmp/remote/out.txt", "dest": str(tmp_path / "out.txt")}],
        )
        context = self._context(jumphost="jump@host")

        def run_side_effect(cmd, *_args, **_kwargs):
            if cmd[0] == "scp":
                raise OSError("scp binary missing")
            return MagicMock(returncode=0, stdout=b"", stderr=b"")

        with (
            patch(
                "infrafoundry.core.events.handlers.script.subprocess.run",
                side_effect=run_side_effect,
            ),
            patch(
                "infrafoundry.core.events.handlers.script.subprocess.Popen",
                return_value=_make_fake_process(returncode=0),
            ),
        ):
            result = handler.execute(context)

        assert result.success
        content = warnings_file.read_text()
        assert "scp of output" in content
        assert "scp binary missing" in content
