"""Unit tests for HookExecutionMixin."""

from unittest.mock import MagicMock

import pytest
from rich.console import Console

from infrafoundry.core.config.models import EnvironmentConfig
from infrafoundry.core.hooks import HookExecutionMixin, HookManager
from infrafoundry.core.hooks.manager import HookExecutionError
from infrafoundry.core.hooks.models import HookResult, HooksConfig
from infrafoundry.core.provider import ResourceConfig


class MockOrchestrator(HookExecutionMixin):
    """Mock orchestrator class for testing the mixin."""

    def __init__(
        self,
        console: Console | None = None,
        hook_manager: HookManager | None = None,
        event_manager: MagicMock | None = None,
    ) -> None:
        self.console = console or MagicMock(spec=Console)
        self._hook_manager = hook_manager
        self.event_manager = event_manager or MagicMock()


@pytest.fixture
def mock_console():
    """Create a mock console."""
    return MagicMock(spec=Console)


@pytest.fixture
def mock_hook_manager():
    """Create a mock hook manager."""
    return MagicMock(spec=HookManager)


@pytest.fixture
def orchestrator(mock_console, mock_hook_manager):
    """Create a MockOrchestrator instance for testing."""
    return MockOrchestrator(console=mock_console, hook_manager=mock_hook_manager)


@pytest.mark.unit
class TestHookExecutionMixin:
    """Tests for HookExecutionMixin."""

    def test_execute_env_hooks_no_hook_manager(self, mock_console):
        """Test _execute_env_hooks when no hook manager is set."""
        orchestrator = MockOrchestrator(console=mock_console, hook_manager=None)
        env_config = MagicMock(spec=EnvironmentConfig)
        env_config.hooks = MagicMock(spec=HooksConfig)

        # Should not raise, just return early
        orchestrator._execute_env_hooks("test-env", "before_plan", env_config)

    def test_execute_env_hooks_no_env_config(self, orchestrator):
        """Test _execute_env_hooks when env_config is None."""
        # Should not raise, just return early
        orchestrator._execute_env_hooks("test-env", "before_plan", None)
        orchestrator._hook_manager.execute_environment_hooks.assert_not_called()

    def test_execute_env_hooks_no_hooks_in_config(self, orchestrator):
        """Test _execute_env_hooks when env_config has no hooks."""
        env_config = MagicMock(spec=EnvironmentConfig)
        env_config.hooks = None

        # Should not raise, just return early
        orchestrator._execute_env_hooks("test-env", "before_plan", env_config)
        orchestrator._hook_manager.execute_environment_hooks.assert_not_called()

    def test_execute_env_hooks_success(self, orchestrator):
        """Test _execute_env_hooks calls hook manager correctly."""
        env_config = MagicMock(spec=EnvironmentConfig)
        env_config.hooks = MagicMock(spec=HooksConfig)

        orchestrator._execute_env_hooks("test-env", "before_plan", env_config)

        orchestrator._hook_manager.execute_environment_hooks.assert_called_once_with(
            env_name="test-env",
            stage="before_plan",
            hooks_config=env_config.hooks,
        )

    def test_execute_env_hooks_error(self, orchestrator, mock_console):
        """Test _execute_env_hooks handles errors correctly."""
        env_config = MagicMock(spec=EnvironmentConfig)
        env_config.hooks = MagicMock(spec=HooksConfig)
        mock_result = HookResult(
            script="test_hook.sh",
            success=False,
            exit_code=1,
            stdout="",
            stderr="Test error",
            duration_seconds=0.1,
        )
        orchestrator._hook_manager.execute_environment_hooks.side_effect = HookExecutionError(
            "Test error", mock_result
        )

        with pytest.raises(HookExecutionError):
            orchestrator._execute_env_hooks("test-env", "before_plan", env_config)

        mock_console.print.assert_called_once()
        assert "Hook failed" in mock_console.print.call_args[0][0]

    def test_execute_resource_hooks_no_hook_manager(self, mock_console):
        """Test _execute_resource_hooks when no hook manager is set."""
        orchestrator = MockOrchestrator(console=mock_console, hook_manager=None)
        resource = MagicMock(spec=ResourceConfig)
        resource.hooks = MagicMock(spec=HooksConfig)

        # Should not raise, just return early
        orchestrator._execute_resource_hooks("test-env", "before_plan", resource, "proxmox")

    def test_execute_resource_hooks_no_hooks_in_resource(self, orchestrator):
        """Test _execute_resource_hooks when resource has no hooks."""
        resource = MagicMock(spec=ResourceConfig)
        resource.hooks = None

        # Should not raise, just return early
        orchestrator._execute_resource_hooks("test-env", "before_plan", resource, "proxmox")
        orchestrator._hook_manager.execute_resource_hooks.assert_not_called()

    def test_execute_resource_hooks_success(self, orchestrator):
        """Test _execute_resource_hooks calls hook manager correctly."""
        resource = MagicMock(spec=ResourceConfig)
        resource.name = "test-resource"
        resource.hooks = MagicMock(spec=HooksConfig)

        orchestrator._execute_resource_hooks("test-env", "before_plan", resource, "proxmox")

        orchestrator._hook_manager.execute_resource_hooks.assert_called_once_with(
            env_name="test-env",
            stage="before_plan",
            resource_name="test-resource",
            provider_name="proxmox",
            hooks_config=resource.hooks,
        )

    def test_execute_resource_hooks_error(self, orchestrator, mock_console):
        """Test _execute_resource_hooks handles errors correctly."""
        resource = MagicMock(spec=ResourceConfig)
        resource.name = "test-resource"
        resource.hooks = MagicMock(spec=HooksConfig)
        mock_result = HookResult(
            script="test_hook.sh",
            success=False,
            exit_code=1,
            stdout="",
            stderr="Test error",
            duration_seconds=0.1,
        )
        orchestrator._hook_manager.execute_resource_hooks.side_effect = HookExecutionError(
            "Test error", mock_result
        )

        with pytest.raises(HookExecutionError):
            orchestrator._execute_resource_hooks("test-env", "before_plan", resource, "proxmox")

        mock_console.print.assert_called_once()
        assert "Hook failed for test-resource" in mock_console.print.call_args[0][0]


@pytest.mark.unit
class TestOrchestratorIntegration:
    """Tests verifying the mixin works with orchestrator classes."""

    def test_plan_orchestrator_has_mixin_methods(self):
        """Test that PlanOrchestrator has the mixin methods."""
        from infrafoundry.core.orchestrator_workflows import PlanOrchestrator

        assert hasattr(PlanOrchestrator, "_execute_env_hooks")
        assert hasattr(PlanOrchestrator, "_execute_resource_hooks")
        assert issubclass(PlanOrchestrator, HookExecutionMixin)

    def test_apply_orchestrator_has_mixin_methods(self):
        """Test that ApplyOrchestrator has the mixin methods."""
        from infrafoundry.core.orchestrator_workflows import ApplyOrchestrator

        assert hasattr(ApplyOrchestrator, "_execute_env_hooks")
        assert hasattr(ApplyOrchestrator, "_execute_resource_hooks")
        assert issubclass(ApplyOrchestrator, HookExecutionMixin)

    def test_destroy_orchestrator_has_mixin_methods(self):
        """Test that DestroyOrchestrator has the mixin methods."""
        from infrafoundry.core.orchestrator_workflows import DestroyOrchestrator

        assert hasattr(DestroyOrchestrator, "_execute_env_hooks")
        assert hasattr(DestroyOrchestrator, "_execute_resource_hooks")
        assert issubclass(DestroyOrchestrator, HookExecutionMixin)


@pytest.mark.unit
class TestLoadEventConfig:
    """Tests for _load_event_config in HookExecutionMixin."""

    def test_load_event_config_with_events(self, mock_console):
        """Test _load_event_config calls clear_handlers and load_config."""
        event_manager = MagicMock()
        orchestrator = MockOrchestrator(console=mock_console, event_manager=event_manager)
        events = {
            "RUNNER_COMPLETED": [{"type": "script", "name": "post-tf", "script": "scripts/post.sh"}]
        }
        env_config = MagicMock(spec=EnvironmentConfig)
        env_config.events = events

        orchestrator._load_event_config(env_config)

        event_manager.clear_handlers.assert_called_once()
        event_manager.load_config.assert_called_once_with(events)

    def test_load_event_config_empty_events(self, mock_console):
        """Test _load_event_config skips when events dict is empty."""
        event_manager = MagicMock()
        orchestrator = MockOrchestrator(console=mock_console, event_manager=event_manager)
        env_config = MagicMock(spec=EnvironmentConfig)
        env_config.events = {}

        orchestrator._load_event_config(env_config)

        event_manager.clear_handlers.assert_not_called()
        event_manager.load_config.assert_not_called()

    def test_load_event_config_none_env_config(self, mock_console):
        """Test _load_event_config skips when env_config is None."""
        event_manager = MagicMock()
        orchestrator = MockOrchestrator(console=mock_console, event_manager=event_manager)

        orchestrator._load_event_config(None)

        event_manager.clear_handlers.assert_not_called()
        event_manager.load_config.assert_not_called()
