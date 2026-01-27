"""Unit tests for lifecycle hooks."""

import stat
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from infrafoundry.core.hooks import (
    HookConfig,
    HookExecutionError,
    HookManager,
    HookResult,
    HooksConfig,
)
from infrafoundry.core.secrets.secret_manager import SecretManager


@pytest.fixture
def temp_config_dir():
    """Create a temporary config directory with env structure."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_dir = Path(tmpdir)
        env_dir = config_dir / "envs" / "test-env"
        scripts_dir = env_dir / "scripts"
        scripts_dir.mkdir(parents=True)
        yield config_dir


@pytest.fixture
def executable_script(temp_config_dir):
    """Create an executable script that prints environment variables."""
    env_dir = temp_config_dir / "envs" / "test-env"
    scripts_dir = env_dir / "scripts"
    script_path = scripts_dir / "test-hook.sh"
    script_path.write_text("""#!/bin/bash
echo "ENV: $INFRAFOUNDRY_ENV"
echo "CONFIG_DIR: $INFRAFOUNDRY_CONFIG_DIR"
echo "EVENT: $INFRAFOUNDRY_EVENT"
echo "CUSTOM_VAR: $CUSTOM_VAR"
exit 0
""")
    script_path.chmod(script_path.stat().st_mode | stat.S_IXUSR)
    return script_path


@pytest.fixture
def failing_script(temp_config_dir):
    """Create a script that exits with non-zero."""
    env_dir = temp_config_dir / "envs" / "test-env"
    scripts_dir = env_dir / "scripts"
    script_path = scripts_dir / "failing-hook.sh"
    script_path.write_text("""#!/bin/bash
echo "About to fail"
exit 1
""")
    script_path.chmod(script_path.stat().st_mode | stat.S_IXUSR)
    return script_path


@pytest.fixture
def timeout_script(temp_config_dir):
    """Create a script that takes too long."""
    env_dir = temp_config_dir / "envs" / "test-env"
    scripts_dir = env_dir / "scripts"
    script_path = scripts_dir / "timeout-hook.sh"
    script_path.write_text("""#!/bin/bash
sleep 10
exit 0
""")
    script_path.chmod(script_path.stat().st_mode | stat.S_IXUSR)
    return script_path


@pytest.fixture
def mock_secret_manager_factory():
    """Create a mock secret manager factory."""

    def factory(env_name: str) -> SecretManager:
        mock_manager = MagicMock(spec=SecretManager)
        mock_manager.get_secret.return_value = "secret-value-from-manager"
        return mock_manager

    return factory


class TestHookConfig:
    """Tests for HookConfig model."""

    def test_minimal_config(self):
        """Test creating HookConfig with minimal fields."""
        config = HookConfig(script="scripts/test.sh")
        assert config.script == "scripts/test.sh"
        assert config.description is None
        assert config.env == {}
        assert config.continue_on_error is False
        assert config.timeout == 300

    def test_full_config(self):
        """Test creating HookConfig with all fields."""
        config = HookConfig(
            script="scripts/test.sh",
            description="Test hook",
            env={"KEY": "value"},
            continue_on_error=True,
            timeout=60,
        )
        assert config.script == "scripts/test.sh"
        assert config.description == "Test hook"
        assert config.env == {"KEY": "value"}
        assert config.continue_on_error is True
        assert config.timeout == 60

    def test_timeout_validation_min(self):
        """Test timeout minimum validation."""
        with pytest.raises(ValueError):
            HookConfig(script="test.sh", timeout=0)

    def test_timeout_validation_max(self):
        """Test timeout maximum validation."""
        with pytest.raises(ValueError):
            HookConfig(script="test.sh", timeout=3601)


class TestHooksConfig:
    """Tests for HooksConfig model."""

    def test_empty_config(self):
        """Test creating empty HooksConfig."""
        config = HooksConfig()
        assert config.before_plan == []
        assert config.after_plan == []
        assert config.before_apply == []
        assert config.after_apply == []
        assert config.before_destroy == []
        assert config.after_destroy == []

    def test_config_with_hooks(self):
        """Test creating HooksConfig with hooks defined."""
        hook = HookConfig(script="scripts/test.sh")
        config = HooksConfig(
            before_destroy=[hook],
            after_apply=[hook],
        )
        assert len(config.before_destroy) == 1
        assert len(config.after_apply) == 1
        assert len(config.before_plan) == 0


class TestHookResult:
    """Tests for HookResult model."""

    def test_successful_result(self):
        """Test creating successful HookResult."""
        result = HookResult(
            script="test.sh",
            success=True,
            exit_code=0,
            stdout="output",
            stderr="",
            duration_seconds=1.5,
        )
        assert result.success is True
        assert result.exit_code == 0
        assert result.timed_out is False
        assert result.error_message is None

    def test_failed_result(self):
        """Test creating failed HookResult."""
        result = HookResult(
            script="test.sh",
            success=False,
            exit_code=1,
            stdout="",
            stderr="error",
            duration_seconds=0.5,
            error_message="Exit code: 1",
        )
        assert result.success is False
        assert result.exit_code == 1

    def test_timeout_result(self):
        """Test creating timeout HookResult."""
        result = HookResult(
            script="test.sh",
            success=False,
            exit_code=-1,
            stdout="",
            stderr="",
            duration_seconds=5.0,
            timed_out=True,
            error_message="Timeout after 5 seconds",
        )
        assert result.timed_out is True


class TestHookManager:
    """Tests for HookManager."""

    def test_init(self, temp_config_dir, mock_secret_manager_factory):
        """Test HookManager initialization."""
        manager = HookManager(
            config_base_dir=temp_config_dir,
            secret_manager_factory=mock_secret_manager_factory,
        )
        assert manager.config_base_dir == temp_config_dir

    def test_execute_environment_hooks_empty(self, temp_config_dir, mock_secret_manager_factory):
        """Test executing with no hooks defined."""
        manager = HookManager(
            config_base_dir=temp_config_dir,
            secret_manager_factory=mock_secret_manager_factory,
        )
        results = manager.execute_environment_hooks(
            env_name="test-env",
            stage="before_plan",
            hooks_config=None,
        )
        assert results == []

    def test_execute_environment_hooks_no_hooks_for_stage(
        self, temp_config_dir, mock_secret_manager_factory
    ):
        """Test executing when no hooks defined for the stage."""
        manager = HookManager(
            config_base_dir=temp_config_dir,
            secret_manager_factory=mock_secret_manager_factory,
        )
        hooks_config = HooksConfig(before_destroy=[HookConfig(script="scripts/test.sh")])
        results = manager.execute_environment_hooks(
            env_name="test-env",
            stage="before_plan",  # No hooks for this stage
            hooks_config=hooks_config,
        )
        assert results == []

    def test_execute_single_hook_success(
        self, temp_config_dir, mock_secret_manager_factory, executable_script
    ):
        """Test successful hook execution."""
        manager = HookManager(
            config_base_dir=temp_config_dir,
            secret_manager_factory=mock_secret_manager_factory,
        )
        hook = HookConfig(
            script="scripts/test-hook.sh",
            env={"CUSTOM_VAR": "custom-value"},
        )
        hooks_config = HooksConfig(before_plan=[hook])

        results = manager.execute_environment_hooks(
            env_name="test-env",
            stage="before_plan",
            hooks_config=hooks_config,
        )

        assert len(results) == 1
        assert results[0].success is True
        assert results[0].exit_code == 0
        assert "ENV: test-env" in results[0].stdout
        assert "CUSTOM_VAR: custom-value" in results[0].stdout

    def test_execute_hook_script_not_found(self, temp_config_dir, mock_secret_manager_factory):
        """Test hook execution when script doesn't exist."""
        manager = HookManager(
            config_base_dir=temp_config_dir,
            secret_manager_factory=mock_secret_manager_factory,
        )
        hook = HookConfig(script="scripts/nonexistent.sh")
        hooks_config = HooksConfig(before_plan=[hook])

        with pytest.raises(HookExecutionError) as exc_info:
            manager.execute_environment_hooks(
                env_name="test-env",
                stage="before_plan",
                hooks_config=hooks_config,
            )

        assert "Script not found" in str(exc_info.value)
        assert exc_info.value.result.success is False

    def test_execute_hook_failure_raises_error(
        self, temp_config_dir, mock_secret_manager_factory, failing_script
    ):
        """Test that hook failure raises HookExecutionError."""
        manager = HookManager(
            config_base_dir=temp_config_dir,
            secret_manager_factory=mock_secret_manager_factory,
        )
        hook = HookConfig(script="scripts/failing-hook.sh")
        hooks_config = HooksConfig(before_plan=[hook])

        with pytest.raises(HookExecutionError) as exc_info:
            manager.execute_environment_hooks(
                env_name="test-env",
                stage="before_plan",
                hooks_config=hooks_config,
            )

        assert exc_info.value.result.success is False
        assert exc_info.value.result.exit_code == 1

    def test_execute_hook_failure_continue_on_error(
        self, temp_config_dir, mock_secret_manager_factory, failing_script
    ):
        """Test that continue_on_error allows execution to proceed."""
        manager = HookManager(
            config_base_dir=temp_config_dir,
            secret_manager_factory=mock_secret_manager_factory,
        )
        hook = HookConfig(
            script="scripts/failing-hook.sh",
            continue_on_error=True,
        )
        hooks_config = HooksConfig(before_plan=[hook])

        # Should not raise
        results = manager.execute_environment_hooks(
            env_name="test-env",
            stage="before_plan",
            hooks_config=hooks_config,
        )

        assert len(results) == 1
        assert results[0].success is False
        assert results[0].exit_code == 1

    def test_execute_hook_timeout(
        self, temp_config_dir, mock_secret_manager_factory, timeout_script
    ):
        """Test hook timeout handling."""
        manager = HookManager(
            config_base_dir=temp_config_dir,
            secret_manager_factory=mock_secret_manager_factory,
        )
        hook = HookConfig(
            script="scripts/timeout-hook.sh",
            timeout=1,  # 1 second timeout
        )
        hooks_config = HooksConfig(before_plan=[hook])

        with pytest.raises(HookExecutionError) as exc_info:
            manager.execute_environment_hooks(
                env_name="test-env",
                stage="before_plan",
                hooks_config=hooks_config,
            )

        assert exc_info.value.result.timed_out is True
        assert "Timeout" in exc_info.value.result.error_message

    def test_execute_resource_hooks(
        self, temp_config_dir, mock_secret_manager_factory, executable_script
    ):
        """Test resource-level hook execution."""
        manager = HookManager(
            config_base_dir=temp_config_dir,
            secret_manager_factory=mock_secret_manager_factory,
        )
        hook = HookConfig(script="scripts/test-hook.sh")
        hooks_config = HooksConfig(before_destroy=[hook])

        results = manager.execute_resource_hooks(
            env_name="test-env",
            stage="before_destroy",
            resource_name="my-resource",
            provider_name="oci",
            hooks_config=hooks_config,
        )

        assert len(results) == 1
        assert results[0].success is True

    def test_environment_variables_injection(self, temp_config_dir, mock_secret_manager_factory):
        """Test that environment variables are properly injected."""
        env_dir = temp_config_dir / "envs" / "test-env" / "scripts"
        script_path = env_dir / "check-env.sh"
        script_path.write_text("""#!/bin/bash
echo "INFRAFOUNDRY_ENV=$INFRAFOUNDRY_ENV"
echo "INFRAFOUNDRY_CONFIG_DIR=$INFRAFOUNDRY_CONFIG_DIR"
echo "INFRAFOUNDRY_EVENT=$INFRAFOUNDRY_EVENT"
echo "INFRAFOUNDRY_RESOURCE=$INFRAFOUNDRY_RESOURCE"
echo "INFRAFOUNDRY_PROVIDER=$INFRAFOUNDRY_PROVIDER"
exit 0
""")
        script_path.chmod(script_path.stat().st_mode | stat.S_IXUSR)

        manager = HookManager(
            config_base_dir=temp_config_dir,
            secret_manager_factory=mock_secret_manager_factory,
        )
        hook = HookConfig(script="scripts/check-env.sh")
        hooks_config = HooksConfig(before_destroy=[hook])

        results = manager.execute_resource_hooks(
            env_name="test-env",
            stage="before_destroy",
            resource_name="my-vm",
            provider_name="oci",
            hooks_config=hooks_config,
        )

        stdout = results[0].stdout
        assert "INFRAFOUNDRY_ENV=test-env" in stdout
        assert "INFRAFOUNDRY_EVENT=before_destroy" in stdout
        assert "INFRAFOUNDRY_RESOURCE=my-vm" in stdout
        assert "INFRAFOUNDRY_PROVIDER=oci" in stdout

    def test_secret_template_resolution(self, temp_config_dir, mock_secret_manager_factory):
        """Test that {{ secrets.xxx }} templates are resolved."""
        env_dir = temp_config_dir / "envs" / "test-env" / "scripts"
        script_path = env_dir / "check-secret.sh"
        script_path.write_text("""#!/bin/bash
echo "SECRET=$MY_SECRET"
exit 0
""")
        script_path.chmod(script_path.stat().st_mode | stat.S_IXUSR)

        manager = HookManager(
            config_base_dir=temp_config_dir,
            secret_manager_factory=mock_secret_manager_factory,
        )
        hook = HookConfig(
            script="scripts/check-secret.sh",
            env={"MY_SECRET": "{{ secrets.myfile.api_key }}"},
        )
        hooks_config = HooksConfig(before_plan=[hook])

        results = manager.execute_environment_hooks(
            env_name="test-env",
            stage="before_plan",
            hooks_config=hooks_config,
        )

        assert results[0].success is True
        assert "SECRET=secret-value-from-manager" in results[0].stdout

    def test_secret_template_not_found(self, temp_config_dir):
        """Test that missing secrets result in empty string with warning."""
        env_dir = temp_config_dir / "envs" / "test-env" / "scripts"
        script_path = env_dir / "check-secret.sh"
        script_path.write_text("""#!/bin/bash
echo "SECRET=$MY_SECRET"
exit 0
""")
        script_path.chmod(script_path.stat().st_mode | stat.S_IXUSR)

        def failing_factory(env_name: str) -> SecretManager:
            mock_manager = MagicMock(spec=SecretManager)
            mock_manager.get_secret.side_effect = FileNotFoundError("Secret file not found")
            return mock_manager

        manager = HookManager(
            config_base_dir=temp_config_dir,
            secret_manager_factory=failing_factory,
        )
        hook = HookConfig(
            script="scripts/check-secret.sh",
            env={"MY_SECRET": "{{ secrets.missing.key }}"},
        )
        hooks_config = HooksConfig(before_plan=[hook])

        # Should not raise - missing secrets become empty strings
        results = manager.execute_environment_hooks(
            env_name="test-env",
            stage="before_plan",
            hooks_config=hooks_config,
        )

        assert results[0].success is True
        assert "SECRET=" in results[0].stdout

    def test_multiple_hooks_execution_order(self, temp_config_dir, mock_secret_manager_factory):
        """Test that multiple hooks are executed in order."""
        env_dir = temp_config_dir / "envs" / "test-env" / "scripts"

        # Create scripts that append to a file
        script1 = env_dir / "hook1.sh"
        script1.write_text("""#!/bin/bash
echo "hook1"
exit 0
""")
        script1.chmod(script1.stat().st_mode | stat.S_IXUSR)

        script2 = env_dir / "hook2.sh"
        script2.write_text("""#!/bin/bash
echo "hook2"
exit 0
""")
        script2.chmod(script2.stat().st_mode | stat.S_IXUSR)

        manager = HookManager(
            config_base_dir=temp_config_dir,
            secret_manager_factory=mock_secret_manager_factory,
        )
        hooks_config = HooksConfig(
            before_plan=[
                HookConfig(script="scripts/hook1.sh"),
                HookConfig(script="scripts/hook2.sh"),
            ]
        )

        results = manager.execute_environment_hooks(
            env_name="test-env",
            stage="before_plan",
            hooks_config=hooks_config,
        )

        assert len(results) == 2
        assert results[0].success is True
        assert "hook1" in results[0].stdout
        assert results[1].success is True
        assert "hook2" in results[1].stdout

    def test_non_executable_script(self, temp_config_dir, mock_secret_manager_factory):
        """Test that non-executable script fails properly."""
        env_dir = temp_config_dir / "envs" / "test-env" / "scripts"
        script_path = env_dir / "non-exec.sh"
        script_path.write_text("""#!/bin/bash
echo "test"
exit 0
""")
        # Don't make it executable

        manager = HookManager(
            config_base_dir=temp_config_dir,
            secret_manager_factory=mock_secret_manager_factory,
        )
        hook = HookConfig(script="scripts/non-exec.sh")
        hooks_config = HooksConfig(before_plan=[hook])

        with pytest.raises(HookExecutionError) as exc_info:
            manager.execute_environment_hooks(
                env_name="test-env",
                stage="before_plan",
                hooks_config=hooks_config,
            )

        assert "not executable" in str(exc_info.value)


class TestHookExecutionError:
    """Tests for HookExecutionError."""

    def test_error_with_result(self):
        """Test HookExecutionError contains result."""
        result = HookResult(
            script="test.sh",
            success=False,
            exit_code=1,
            stdout="",
            stderr="error",
            duration_seconds=0.5,
        )
        error = HookExecutionError("Hook failed", result)
        assert error.result == result
        assert "Hook failed" in str(error)


@pytest.mark.unit
class TestHookEventsIntegration:
    """Tests for hook events integration."""

    def test_hook_emits_events_on_success(
        self, temp_config_dir, executable_script, mock_secret_manager_factory
    ):
        """Test that successful hook emits HOOK_STARTED and HOOK_COMPLETED events."""
        from unittest.mock import MagicMock

        from infrafoundry.core.events import EventManager, EventType

        mock_event_manager = MagicMock(spec=EventManager)

        manager = HookManager(
            config_base_dir=temp_config_dir,
            secret_manager_factory=mock_secret_manager_factory,
            event_manager=mock_event_manager,
        )
        hook = HookConfig(script="scripts/test-hook.sh", description="Test hook")
        hooks_config = HooksConfig(before_plan=[hook])

        manager.execute_environment_hooks(
            env_name="test-env",
            stage="before_plan",
            hooks_config=hooks_config,
        )

        # Should have emitted HOOK_STARTED and HOOK_COMPLETED
        calls = mock_event_manager.emit_event.call_args_list
        assert len(calls) == 2

        # First call: HOOK_STARTED
        assert calls[0][0][0] == EventType.HOOK_STARTED
        assert calls[0][0][1] == "test-env"
        assert calls[0][0][2]["script"] == "scripts/test-hook.sh"
        assert calls[0][0][2]["stage"] == "before_plan"

        # Second call: HOOK_COMPLETED
        assert calls[1][0][0] == EventType.HOOK_COMPLETED
        assert calls[1][0][1] == "test-env"
        assert calls[1][0][2]["success"] is True

    def test_hook_emits_events_on_failure(
        self, temp_config_dir, failing_script, mock_secret_manager_factory
    ):
        """Test that failing hook emits HOOK_STARTED and HOOK_FAILED events."""
        from unittest.mock import MagicMock

        from infrafoundry.core.events import EventManager, EventType

        mock_event_manager = MagicMock(spec=EventManager)

        manager = HookManager(
            config_base_dir=temp_config_dir,
            secret_manager_factory=mock_secret_manager_factory,
            event_manager=mock_event_manager,
        )
        hook = HookConfig(script="scripts/failing-hook.sh", continue_on_error=True)
        hooks_config = HooksConfig(before_plan=[hook])

        manager.execute_environment_hooks(
            env_name="test-env",
            stage="before_plan",
            hooks_config=hooks_config,
        )

        # Should have emitted HOOK_STARTED and HOOK_FAILED
        calls = mock_event_manager.emit_event.call_args_list
        assert len(calls) == 2

        # First call: HOOK_STARTED
        assert calls[0][0][0] == EventType.HOOK_STARTED

        # Second call: HOOK_FAILED
        assert calls[1][0][0] == EventType.HOOK_FAILED
        assert calls[1][0][2]["success"] is False
        assert "error_message" in calls[1][0][2]

    def test_hook_no_events_without_event_manager(
        self, temp_config_dir, executable_script, mock_secret_manager_factory
    ):
        """Test that hooks work without event manager (no events emitted)."""
        manager = HookManager(
            config_base_dir=temp_config_dir,
            secret_manager_factory=mock_secret_manager_factory,
            event_manager=None,  # No event manager
        )
        hook = HookConfig(script="scripts/test-hook.sh")
        hooks_config = HooksConfig(before_plan=[hook])

        # Should not raise any errors
        results = manager.execute_environment_hooks(
            env_name="test-env",
            stage="before_plan",
            hooks_config=hooks_config,
        )

        assert len(results) == 1
        assert results[0].success is True

    def test_hook_events_include_resource_info(
        self, temp_config_dir, executable_script, mock_secret_manager_factory
    ):
        """Test that resource hooks include resource info in events."""
        from unittest.mock import MagicMock

        from infrafoundry.core.events import EventManager

        mock_event_manager = MagicMock(spec=EventManager)

        manager = HookManager(
            config_base_dir=temp_config_dir,
            secret_manager_factory=mock_secret_manager_factory,
            event_manager=mock_event_manager,
        )
        hook = HookConfig(script="scripts/test-hook.sh")
        hooks_config = HooksConfig(before_plan=[hook])

        manager.execute_resource_hooks(
            env_name="test-env",
            stage="before_plan",
            resource_name="my-vm",
            provider_name="proxmox",
            hooks_config=hooks_config,
        )

        # Check that resource info is in event data
        calls = mock_event_manager.emit_event.call_args_list
        assert len(calls) == 2

        # Both events should include resource info
        for call in calls:
            data = call[0][2]
            assert data["resource_name"] == "my-vm"
            assert data["provider_name"] == "proxmox"
