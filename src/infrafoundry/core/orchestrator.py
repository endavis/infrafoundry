"""Core orchestration for infrastructure deployment."""

import getpass
import os
import socket
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rich.console import Console

from infrafoundry.core.audit import AuditLogger
from infrafoundry.core.config import ConfigManager
from infrafoundry.core.dependencies import DependencyGraph
from infrafoundry.core.deployment_executor import DeploymentExecutor
from infrafoundry.core.drift_detector import DriftDetector
from infrafoundry.core.events import Event, EventManager, EventType
from infrafoundry.core.exceptions import ResourceFilterError
from infrafoundry.core.execution_planner import ExecutionPlanner
from infrafoundry.core.hooks import HookManager
from infrafoundry.core.notifications import NotificationManager
from infrafoundry.core.orchestrator_workflows import (
    ApplyOrchestrator,
    DestroyOrchestrator,
    DriftOrchestrator,
    PlanOrchestrator,
    ProviderResourceBatch,
    RollbackOrchestrator,
    StatusOrchestrator,
    ValidationOrchestrator,
)
from infrafoundry.core.policy import PolicyEngine, PolicyViolation
from infrafoundry.core.policy_checker import PolicyChecker
from infrafoundry.core.provider import ProviderBase, ResourceConfig
from infrafoundry.core.provider_registry_service import ProviderRegistryService
from infrafoundry.core.runners import RunnerRegistry
from infrafoundry.core.secrets.secret_manager import SecretManager
from infrafoundry.core.state import StateManager
from infrafoundry.core.state.lock_context import environment_lock


@dataclass(slots=True)
class OrchestratorStrictConfig:
    """Configuration for strict-mode safeguards."""

    strict_mode: bool = False
    fail_on_missing_secrets: bool = False
    fail_on_missing_snippets: bool = False

    def __post_init__(self) -> None:
        if self.strict_mode:
            self.fail_on_missing_secrets = True
            self.fail_on_missing_snippets = True


class Orchestrator:
    """Orchestrates infrastructure deployment across providers."""

    def __init__(
        self,
        config_manager: ConfigManager,
        output_dir: Path | None = None,
        state_manager: StateManager | None = None,
        event_manager: EventManager | None = None,
        policy_dir: Path | None = None,
        notifications_config: Path | None = None,
        strict_config: OrchestratorStrictConfig | None = None,
    ) -> None:
        """Initialize orchestrator.

        Args:
            config_manager: Configuration manager instance
            output_dir: Directory for generated files (defaults to ./generated)
            state_manager: State manager instance (creates default if None)
            event_manager: Event manager instance (creates default if None)
            policy_dir: Directory containing policy files (defaults to ./policies)
            notifications_config: Path to notifications config file
            strict_config: Configuration for strict-mode safeguards
        """
        self.config_manager = config_manager
        self.output_dir = output_dir or Path.cwd() / "generated"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.console = Console()
        self.strict_config = strict_config or OrchestratorStrictConfig()

        # Initialize state, event, policy, and notification managers
        self.state_manager = state_manager or StateManager()
        self.state_manager.initialize()  # Initialize database schema
        self.event_manager = event_manager or EventManager()
        self.policy_engine = PolicyEngine(policy_dir)
        self.notification_manager = NotificationManager(notifications_config)

        # Initialize audit logger with event bus subscription
        self.audit_logger = AuditLogger(
            session_factory=self.state_manager.SessionLocal,
            event_bus=self.event_manager,
            get_current_user=self._get_current_user,
        )

        # Provider and runner management
        self.provider_registry = ProviderRegistryService(
            base_output_dir=self.output_dir,
            config_manager=self.config_manager,
            runner_registry_factory=RunnerRegistry,
        )
        self._providers = self.provider_registry.providers
        self.runner_registry = self.provider_registry.runner_registry

        # Hook manager for lifecycle hooks
        self.hook_manager = HookManager(
            config_base_dir=self.config_manager.base_dir,
            secret_manager_factory=self._create_secret_manager,
        )

        # Initialize helper classes for orchestration tasks
        self.policy_checker = PolicyChecker(self.policy_engine, self.event_manager, self.console)
        self.drift_detector = DriftDetector(
            self.config_manager,
            self.runner_registry,
            self.event_manager,
            self.providers,
        )
        self.deployment_executor = DeploymentExecutor(
            self.runner_registry,
            self.state_manager,
            self.event_manager,
            self.providers,
            self.console,
        )
        self.validation_orchestrator = ValidationOrchestrator(
            config_manager=self.config_manager,
            console=self.console,
            get_providers=self._get_providers,
            load_resources=self._load_resources,
            iter_provider_batches=self._iter_provider_batches,
        )
        self.plan_orchestrator = PlanOrchestrator(
            console=self.console,
            state_manager=self.state_manager,
            event_manager=self.event_manager,
            runner_registry=self.runner_registry,
            get_providers=self._get_providers,
            load_resources=self._load_resources,
            iter_provider_batches=self._iter_provider_batches,
            validate_resources=self.validate_resources,
            has_policies=self._has_policies,
            check_policies=self._check_policies_wrapper,
            secret_manager_factory=self._create_secret_manager,
            get_current_user=self._get_current_user,
            fail_on_missing_secrets=self.strict_config.fail_on_missing_secrets,
            get_runner_priorities=self.provider_registry.get_runner_priorities,
            hook_manager=self.hook_manager,
            load_environment=self.config_manager.load_environment,
        )
        self.apply_orchestrator = ApplyOrchestrator(
            console=self.console,
            state_manager=self.state_manager,
            event_manager=self.event_manager,
            load_resources=self._load_resources,
            apply_serial=self._apply_providers_serial,
            apply_parallel=self._apply_providers_parallel,
            get_current_user=self._get_current_user,
            hook_manager=self.hook_manager,
            load_environment=self.config_manager.load_environment,
        )
        self.destroy_orchestrator = DestroyOrchestrator(
            console=self.console,
            state_manager=self.state_manager,
            event_manager=self.event_manager,
            runner_registry=self.runner_registry,
            get_providers=self._get_providers,
            load_resources=self._load_resources,
            iter_provider_batches=self._iter_provider_batches,
            get_current_user=self._get_current_user,
            hook_manager=self.hook_manager,
            load_environment=self.config_manager.load_environment,
        )
        self.rollback_orchestrator = RollbackOrchestrator(
            console=self.console,
            state_manager=self.state_manager,
            apply_orchestrator=self.apply_orchestrator,
            get_current_user=self._get_current_user,
        )
        self.drift_orchestrator = DriftOrchestrator(
            drift_detector=self.drift_detector,
            get_providers=self._get_providers,
        )
        self.status_orchestrator = StatusOrchestrator(
            console=self.console,
            config_manager=self.config_manager,
            get_providers=self._get_providers,
        )

        # Subscribe notification manager to events
        self._setup_notifications()

    def _get_current_user(self) -> str:
        """Get current system user."""
        return os.environ.get("USER") or os.environ.get("USERNAME") or "unknown"

    def _get_providers(self) -> dict[str, ProviderBase]:
        """Get registered providers."""
        return self.providers

    def _has_policies(self) -> bool:
        """Check if policies are loaded."""
        return bool(self.policy_engine.policies)

    def _create_secret_manager(self, env_name: str) -> SecretManager:
        """Create a secret manager for an environment."""
        return SecretManager(env_name=env_name)

    def _check_policies_wrapper(
        self, env_name: str, resources: list[ResourceConfig], enforce: bool
    ) -> None:
        """Wrapper for check_policies to match PlanOrchestrator interface."""
        self.check_policies(env_name, resources, enforce=enforce)

    def _setup_notifications(self) -> None:
        """Set up notification handlers for events."""
        if not self.notification_manager or not self.notification_manager.channels:
            return

        # Subscribe to all events
        def event_handler(event: Event) -> None:
            """Forward events to notification manager."""
            self.notification_manager.notify(event.event_type.value, event.environment, event.data)

        # Subscribe to all event types
        for event_type in EventType:
            self.event_manager.subscribe(event_type, event_handler)

    def register_provider(self, provider: ProviderBase) -> None:
        """Register a provider plugin.

        Args:
            provider: Provider instance to register
        """
        self._providers[provider.name] = provider
        if hasattr(provider, "fail_on_missing_snippets"):
            provider.fail_on_missing_snippets = self.strict_config.fail_on_missing_snippets
        # Sync providers to helper classes that need them
        self.deployment_executor.providers = self._providers
        self.drift_detector.providers = self._providers

    @property
    def providers(self) -> dict[str, ProviderBase]:
        """Registered providers."""
        return self._providers

    @providers.setter
    def providers(self, value: dict[str, ProviderBase]) -> None:
        """Set providers and propagate to dependent components."""
        self._providers = value
        self.deployment_executor.providers = self._providers
        self.drift_detector.providers = self._providers

    def _load_resources(
        self, env_name: str
    ) -> tuple[list[ResourceConfig], dict[str, list[ResourceConfig]]]:
        """Load all resources for an environment and group them by provider."""
        all_resources = self.config_manager.get_all_resources_all_providers(env_name)
        resources_by_provider: dict[str, list[ResourceConfig]] = {}
        for resource in all_resources:
            resources_by_provider.setdefault(resource.provider, []).append(resource)

        # Register package events discovered during resource loading
        package_events = self.config_manager.get_package_events()
        if isinstance(package_events, dict) and package_events and self.event_manager:
            self.event_manager.load_config(package_events)

        return all_resources, resources_by_provider

    def _create_execution_planner(self, env_name: str) -> ExecutionPlanner:
        """Create an execution planner for an environment.

        Args:
            env_name: Environment name

        Returns:
            ExecutionPlanner configured with environment's provider order
        """
        env_config = self.config_manager.load_environment(env_name)
        provider_order = None
        if env_config and env_config.provider_order:
            provider_order = env_config.provider_order

        # Optionally include dependency graph for cross-provider deps
        dependency_graph = self.build_dependency_graph(env_name)

        return ExecutionPlanner(
            provider_order=provider_order,
            dependency_graph=dependency_graph,
        )

    def _iter_provider_batches(
        self,
        resources_by_provider: dict[str, list[ResourceConfig]],
        resource_filter: list[str] | None,
        reverse: bool = False,
        env_name: str | None = None,
    ) -> list[ProviderResourceBatch]:
        """Yield provider batches applying an optional resource name filter.

        Args:
            resources_by_provider: Dict mapping provider names to resources
            resource_filter: Optional list of resource names to filter by
            reverse: If True, return batches in reverse order (for destroy)
            env_name: Optional environment name for loading provider order config

        Returns:
            List of ProviderResourceBatch in execution order
        """
        # Create execution planner with environment config
        planner = self._create_execution_planner(env_name) if env_name else ExecutionPlanner()

        # Convert to set for O(1) lookups
        filter_set = set(resource_filter) if resource_filter else None

        # Get sorted provider order
        sorted_providers = planner.sort_providers(
            list(resources_by_provider.keys()), reverse=reverse
        )

        batches: list[ProviderResourceBatch] = []
        for provider_name in sorted_providers:
            resources = resources_by_provider.get(provider_name, [])
            original_count = len(resources)
            filtered_resources = resources
            if filter_set:
                filtered_resources = [r for r in resources if r.name in filter_set]
                if not filtered_resources:
                    continue
            batches.append(
                ProviderResourceBatch(
                    name=provider_name,
                    resources=filtered_resources,
                    original_count=original_count,
                )
            )

        # Validate resource filter results
        if filter_set:
            matched_names = {r.name for batch in batches for r in batch.resources}
            unmatched = filter_set - matched_names
            if not matched_names:
                all_names = sorted(
                    {r.name for resources in resources_by_provider.values() for r in resources}
                )
                raise ResourceFilterError(
                    f"No resources matched filter: {', '.join(sorted(filter_set))}. "
                    f"Available resources: {', '.join(all_names)}"
                )
            elif unmatched:
                self.console.print(
                    f"[yellow]Warning: Some resources not found: "
                    f"{', '.join(sorted(unmatched))}[/yellow]"
                )

        return batches

    def validate_resources(self, resources: list[ResourceConfig]) -> None:
        """Validate that all resources have providers that support their types.

        Args:
            resources: List of ResourceConfig objects to validate

        Raises:
            ValueError: If a resource's provider doesn't support its type
        """
        for resource in resources:
            provider_name = resource.provider
            resource_type = resource.type

            # Check if provider is registered
            if provider_name not in self.providers:
                raise ValueError(
                    f"Provider '{provider_name}' not registered for resource "
                    f"'{resource.name}' (type: {resource_type})"
                )

            # Check if provider supports the resource type
            provider = self.providers[provider_name]
            supported_types = provider.get_resource_types()
            if resource_type not in supported_types:
                raise ValueError(
                    f"Provider '{provider_name}' does not support resource type "
                    f"'{resource_type}' for resource '{resource.name}'. "
                    f"Supported types: {', '.join(supported_types)}"
                )

    def build_dependency_graph(self, env_name: str) -> DependencyGraph:
        """Build dependency graph for an environment.

        Args:
            env_name: Environment name

        Returns:
            DependencyGraph with all resources and dependencies
        """
        graph = DependencyGraph()

        # Get all resources for the environment
        all_resources = self.config_manager.get_all_resources_all_providers(env_name)

        # Build a map of resources by provider and type for dependency resolution
        resources_by_provider: dict[str, list[ResourceConfig]] = {}
        for resource in all_resources:
            if resource.provider not in resources_by_provider:
                resources_by_provider[resource.provider] = []
            resources_by_provider[resource.provider].append(resource)

        # Add all resources to graph with their dependencies
        for resource in all_resources:
            provider_name = resource.provider
            dependencies: list[str] = []

            if provider_name in self.providers:
                provider = self.providers[provider_name]
                dependency_rules = provider.get_dependencies()

                # Check if this resource type has dependencies
                if resource.type in dependency_rules:
                    required_types = dependency_rules[resource.type]

                    # Find resources of required types from same provider
                    provider_resources = resources_by_provider.get(provider_name, [])
                    for other_resource in provider_resources:
                        if (
                            other_resource.type in required_types
                            and other_resource.name != resource.name
                        ):
                            dependencies.append(other_resource.name)

            graph.add_resource(
                provider=resource.provider,
                resource_type=resource.type,
                name=resource.name,
                dependencies=dependencies,
            )

        return graph

    def check_policies(
        self, env_name: str, resources: list[ResourceConfig], enforce: bool = False
    ) -> tuple[bool, list[PolicyViolation]]:
        """Check resources against policies.

        Delegates to PolicyChecker.

        Args:
            env_name: Environment name
            resources: List of resources to check
            enforce: If True, raise exception on ERROR-level violations

        Returns:
            Tuple of (passed, violations)

        Raises:
            Exception: If enforce=True and ERROR-level violations exist
        """
        return self.policy_checker.check(env_name, resources, enforce)

    def detect_drift(self, env_name: str) -> dict[str, Any]:
        """Detect infrastructure drift from declared configuration.

        Delegates to DriftDetector.

        Args:
            env_name: Environment name

        Returns:
            Dict with drift detection results per provider
        """
        return self.drift_orchestrator.detect(env_name)

    def validate(
        self,
        env_name: str,
        resource_filter: list[str] | None = None,
        verbose: bool = False,
    ) -> dict[str, Any]:
        """Validate infrastructure configuration against provider APIs.

        Performs pre-flight validation checks:
        - Connectivity to provider APIs
        - Referenced resources exist (templates, networks, storage, etc.)
        - No conflicts (duplicate VMIDs, MAC addresses, etc.)

        Args:
            env_name: Environment name
            resource_filter: Optional list of resource names to validate
            verbose: If True, show detailed validation output

        Returns:
            Dict with validation results per provider:
            {
                "provider_name": {
                    "passed": bool,
                    "report": ValidationReport,
                "errors": int,
                "warnings": int
                }
            }
        """
        return self.validation_orchestrator.validate(env_name, resource_filter, verbose)

    def plan(
        self,
        env_name: str,
        dry_run: bool = False,
        resource_filter: list[str] | None = None,
        enforce_policies: bool = False,
        package_filter: str | None = None,
        add_only: bool = False,
        provider_filter: list[str] | None = None,
    ) -> dict[str, Any]:
        """Plan infrastructure changes.

        Args:
            env_name: Environment name
            dry_run: If True, only show what would be done
            resource_filter: Optional list of resource names to target
            enforce_policies: If True, block on policy violations
            package_filter: Optional package name to restrict event handlers
            add_only: If True, suppress deletes for live resources not
                described in YAML. Honored by direct-API runners; other
                runners accept and ignore.
            provider_filter: Optional list of provider names to target.
                Cross-provider dependency edges pointing at filtered-out
                providers are silently skipped for this run. Raises
                ``ProviderFilterError`` if any name is unknown.

        Returns:
            Dict with plan results per provider
        """
        return self.plan_orchestrator.plan(
            env_name,
            dry_run,
            resource_filter,
            enforce_policies,
            package_filter,
            add_only=add_only,
            provider_filter=provider_filter,
        )

    def apply(
        self,
        env_name: str,
        auto_approve: bool = False,
        resource_filter: list[str] | None = None,
        parallel: bool = False,
        max_workers: int = 4,
        package_filter: str | None = None,
        lock_timeout: int = 0,
        lock_ttl: int = 600,
        add_only: bool = False,
        provider_filter: list[str] | None = None,
    ) -> dict[str, Any]:
        """Apply infrastructure changes.

        Args:
            env_name: Environment name
            auto_approve: If True, skip confirmation prompts
            resource_filter: Optional list of resource names to target
            parallel: If True, apply resources in parallel where possible
            max_workers: Maximum number of parallel workers (default: 4)
            package_filter: Optional package name to restrict event handlers
            lock_timeout: Seconds to wait for the environment lock before
                failing. ``0`` (default) fails fast.
            lock_ttl: Lock TTL in seconds (default: 10 minutes). The lock is
                extended automatically while the process runs, so this only
                governs stale-lock recovery after a crash.
            add_only: If True, suppress deletes for live resources not
                described in YAML. Honored by direct-API runners; other
                runners accept and ignore.
            provider_filter: Optional list of provider names to target.
                Cross-provider dependency edges pointing at filtered-out
                providers are silently skipped for this run. Raises
                ``ProviderFilterError`` if any name is unknown.

        Returns:
            Dict with apply results per provider
        """
        locked_by = _build_lock_holder_id()
        with environment_lock(
            self.state_manager,
            env_name,
            ttl=lock_ttl,
            locked_by=locked_by,
            timeout=lock_timeout,
            event_manager=self.event_manager,
        ):
            # First, generate the plans
            self.plan(
                env_name,
                dry_run=False,
                resource_filter=resource_filter,
                package_filter=package_filter,
                add_only=add_only,
                provider_filter=provider_filter,
            )
            return self.apply_orchestrator.apply(
                env_name=env_name,
                resource_filter=resource_filter,
                auto_approve=auto_approve,
                parallel=parallel,
                max_workers=max_workers,
                package_filter=package_filter,
                add_only=add_only,
                provider_filter=provider_filter,
            )

    def _apply_providers_serial(
        self,
        env_name: str,
        deployment_id: int,
        resources_by_provider: dict[str, list[ResourceConfig]],
        resource_filter: list[str] | None,
        auto_approve: bool,
        package_filter: str | None = None,
        *,
        add_only: bool = False,
    ) -> dict[str, Any]:
        """Apply providers sequentially."""
        # Load runner priorities, IaC tool, and provider order from environment config
        env_config = self.config_manager.load_environment(env_name)
        if env_config:
            self.deployment_executor.runner_priorities = env_config.runner_priorities
            self.deployment_executor.iac_tool = env_config.iac_tool
            # Update execution planner with environment-specific provider order
            self.deployment_executor.provider_order = env_config.provider_order or None
            self.deployment_executor.execution_planner = ExecutionPlanner(
                provider_order=env_config.provider_order or None
            )

        return self.deployment_executor.apply_serial(
            env_name,
            deployment_id,
            resources_by_provider,
            resource_filter,
            auto_approve,
            package_filter=package_filter,
            add_only=add_only,
        )

    def _apply_providers_parallel(
        self,
        env_name: str,
        deployment_id: int,
        resources_by_provider: dict[str, list[ResourceConfig]],
        resource_filter: list[str] | None,
        auto_approve: bool,
        max_workers: int,
        package_filter: str | None = None,
        *,
        add_only: bool = False,
    ) -> dict[str, Any]:
        """Apply providers in parallel."""
        # Load runner priorities, IaC tool, and provider order from environment config
        env_config = self.config_manager.load_environment(env_name)
        if env_config:
            self.deployment_executor.runner_priorities = env_config.runner_priorities
            self.deployment_executor.iac_tool = env_config.iac_tool
            # Update execution planner with environment-specific provider order
            self.deployment_executor.provider_order = env_config.provider_order or None
            self.deployment_executor.execution_planner = ExecutionPlanner(
                provider_order=env_config.provider_order or None
            )

        return self.deployment_executor.apply_parallel(
            env_name,
            deployment_id,
            resources_by_provider,
            resource_filter,
            auto_approve,
            max_workers,
            package_filter=package_filter,
            add_only=add_only,
        )

    def _apply_single_provider(
        self,
        env_name: str,
        deployment_id: int,
        provider_name: str,
        provider: ProviderBase,
        resources: list[ResourceConfig],
        auto_approve: bool,
    ) -> dict[str, Any]:
        """Apply a single provider's resources."""
        self.deployment_executor.providers = self.providers
        return self.deployment_executor.apply_single_provider(
            env_name, deployment_id, provider_name, provider, resources, auto_approve
        )

    def destroy(
        self,
        env_name: str,
        auto_approve: bool = False,
        resource_filter: list[str] | None = None,
        confirm_callback: Callable[[], bool] | None = None,
        package_filter: str | None = None,
        lock_timeout: int = 0,
        lock_ttl: int = 600,
        provider_filter: list[str] | None = None,
    ) -> dict[str, Any]:
        """Destroy infrastructure.

        Args:
            env_name: Environment name
            auto_approve: If True, skip confirmation prompts
            resource_filter: Optional list of resource names to target
            confirm_callback: Optional callback for user confirmation
            package_filter: Optional package name to restrict event handlers
            lock_timeout: Seconds to wait for the environment lock before
                failing. ``0`` (default) fails fast.
            lock_ttl: Lock TTL in seconds (default: 10 minutes). The lock is
                extended automatically while the process runs, so this only
                governs stale-lock recovery after a crash.
            provider_filter: Optional list of provider names to target.
                Cross-provider dependency edges pointing at filtered-out
                providers are silently skipped for this run. Raises
                ``ProviderFilterError`` if any name is unknown.

        Returns:
            Dict with destroy results per provider
        """
        locked_by = _build_lock_holder_id()
        with environment_lock(
            self.state_manager,
            env_name,
            ttl=lock_ttl,
            locked_by=locked_by,
            timeout=lock_timeout,
            event_manager=self.event_manager,
        ):
            return self.destroy_orchestrator.destroy(
                env_name,
                resource_filter,
                auto_approve,
                confirm_callback,
                package_filter,
                provider_filter=provider_filter,
            )

    def rollback(
        self,
        deployment_id: int,
        auto_approve: bool = False,
        confirm_callback: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        """Rollback infrastructure to a previous deployment state.

        Args:
            deployment_id: ID of deployment to rollback to
            auto_approve: If True, skip confirmation prompts
            confirm_callback: Optional callback for user confirmation

        Returns:
            Dict with rollback results

        Raises:
            ValueError: If deployment not found or has no rollback data
        """
        return self.rollback_orchestrator.rollback(deployment_id, auto_approve, confirm_callback)

    def status(self, env_name: str) -> None:
        """Show status of infrastructure.

        Args:
            env_name: Environment name
        """
        self.status_orchestrator.show(env_name)


def _build_lock_holder_id() -> str:
    """Construct a ``user@host:pid`` identifier for the current process."""
    try:
        user = getpass.getuser()
    except Exception:
        user = os.environ.get("USER", "unknown")
    try:
        host = socket.gethostname()
    except Exception:
        host = "unknown"
    return f"{user}@{host}:{os.getpid()}"
