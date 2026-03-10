"""Mixin for hook execution in orchestrator workflows.

This module provides a reusable mixin that encapsulates the common hook
execution logic used by PlanOrchestrator, ApplyOrchestrator, and
DestroyOrchestrator.
"""

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from rich.console import Console

from infrafoundry.core.hooks.manager import HookExecutionError, HookManager

if TYPE_CHECKING:
    from infrafoundry.core.config.models import EnvironmentConfig
    from infrafoundry.core.events.bus import UnifiedEventBus
    from infrafoundry.core.provider import ResourceConfig


@runtime_checkable
class HasHookExecutionDependencies(Protocol):
    """Protocol defining required attributes for HookExecutionMixin."""

    _hook_manager: HookManager | None
    console: Console


class HookExecutionMixin:
    """Mixin providing hook execution methods for orchestrator classes.

    This mixin requires the following attributes on the class:
    - _hook_manager: HookManager | None
    - console: Console

    Example:
        class MyOrchestrator(HookExecutionMixin):
            def __init__(self, console: Console, hook_manager: HookManager | None):
                self.console = console
                self._hook_manager = hook_manager

            def do_work(self, env_name: str, env_config: EnvironmentConfig):
                self._execute_env_hooks(env_name, "before_plan", env_config)
                # ... do actual work ...
                self._execute_env_hooks(env_name, "after_plan", env_config)
    """

    # Type hints for mixin - these are provided by the class using this mixin
    _hook_manager: HookManager | None
    console: Console
    event_manager: "UnifiedEventBus"

    def _execute_env_hooks(
        self,
        env_name: str,
        stage: str,
        env_config: "EnvironmentConfig | None",
    ) -> None:
        """Execute environment-level hooks for a lifecycle stage.

        Args:
            env_name: Environment name
            stage: Lifecycle stage (e.g., "before_plan", "after_apply")
            env_config: Environment configuration containing hooks
        """
        if not self._hook_manager or not env_config or not env_config.hooks:
            return

        try:
            self._hook_manager.execute_environment_hooks(
                env_name=env_name,
                stage=stage,
                hooks_config=env_config.hooks,
            )
        except HookExecutionError as e:
            self.console.print(f"[red]Hook failed: {e}[/red]")
            raise

    def _load_event_config(self, env_config: "EnvironmentConfig | None") -> None:
        """Register event handlers from environment configuration.

        Clears existing config-based handlers before loading to prevent
        duplicate registrations across repeated workflow calls.

        Args:
            env_config: Environment configuration containing event handler definitions
        """
        if not env_config or not env_config.events:
            return

        self.event_manager.clear_handlers()
        self.event_manager.load_config(env_config.events)

    def _execute_resource_hooks(
        self,
        env_name: str,
        stage: str,
        resource: "ResourceConfig",
        provider_name: str,
    ) -> None:
        """Execute resource-level hooks for a lifecycle stage.

        Args:
            env_name: Environment name
            stage: Lifecycle stage (e.g., "before_plan", "after_apply")
            resource: Resource configuration containing hooks
            provider_name: Name of the provider for this resource
        """
        if not self._hook_manager or not resource.hooks:
            return

        try:
            self._hook_manager.execute_resource_hooks(
                env_name=env_name,
                stage=stage,
                resource_name=resource.name,
                provider_name=provider_name,
                hooks_config=resource.hooks,
            )
        except HookExecutionError as e:
            self.console.print(f"[red]Hook failed for {resource.name}: {e}[/red]")
            raise
