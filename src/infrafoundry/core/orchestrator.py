"""Core orchestration for infrastructure deployment."""

import os
from datetime import datetime
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table

from infrafoundry.core.ansible_runner import AnsibleRunner
from infrafoundry.core.config import ConfigManager
from infrafoundry.core.dependencies import DependencyGraph
from infrafoundry.core.deployment_executor import DeploymentExecutor
from infrafoundry.core.drift_detector import DriftDetector
from infrafoundry.core.events import Event, EventManager, EventType
from infrafoundry.core.notifications import NotificationManager
from infrafoundry.core.policy import PolicyEngine
from infrafoundry.core.policy_checker import PolicyChecker
from infrafoundry.core.provider import ProviderBase
from infrafoundry.core.secrets import SecretManager
from infrafoundry.core.state import DeploymentStatus, ResourceState, StateManager
from infrafoundry.core.terraform_runner import TerraformRunner


class Orchestrator:
    """Orchestrates infrastructure deployment across providers."""

    def __init__(
        self,
        config_manager: ConfigManager,
        secret_manager: SecretManager,
        output_dir: Path | None = None,
        state_manager: StateManager | None = None,
        event_manager: EventManager | None = None,
        policy_dir: Path | None = None,
        notifications_config: Path | None = None,
    ) -> None:
        """Initialize orchestrator.

        Args:
            config_manager: Configuration manager instance
            secret_manager: Secret manager instance
            output_dir: Directory for generated files (defaults to ./generated)
            state_manager: State manager instance (creates default if None)
            event_manager: Event manager instance (creates default if None)
            policy_dir: Directory containing policy files (defaults to ./policies)
            notifications_config: Path to notifications config file
        """
        self.config_manager = config_manager
        self.secret_manager = secret_manager
        self.output_dir = output_dir or Path.cwd() / "generated"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.console = Console()
        self.providers: dict[str, ProviderBase] = {}

        # Initialize state, event, policy, and notification managers
        self.state_manager = state_manager or StateManager()
        self.state_manager.initialize()  # Initialize database schema
        self.event_manager = event_manager or EventManager()
        self.policy_engine = PolicyEngine(policy_dir)
        self.notification_manager = NotificationManager(notifications_config)

        # Initialize helper classes for orchestration tasks
        self.terraform_runner = TerraformRunner(self.secret_manager, self.console)
        self.ansible_runner = AnsibleRunner(self.console)
        self.policy_checker = PolicyChecker(self.policy_engine, self.event_manager, self.console)
        self.drift_detector = DriftDetector(
            self.config_manager,
            self.terraform_runner,
            self.event_manager,
            self.providers,
            self.console,
        )
        self.deployment_executor = DeploymentExecutor(
            self.terraform_runner,
            self.ansible_runner,
            self.state_manager,
            self.event_manager,
            self.providers,
            self.console,
        )

        # Subscribe notification manager to events
        self._setup_notifications()

        # Get current user for tracking
        self._current_user = os.environ.get("USER") or os.environ.get("USERNAME") or "unknown"

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
        self.providers[provider.name] = provider
        # Sync providers to helper classes that need them
        self.deployment_executor.providers = self.providers
        self.drift_detector.providers = self.providers

    def validate_resources(self, resources: list[Any]) -> None:
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
        resources_by_provider: dict[str, list[Any]] = {}
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
        self, env_name: str, resources: list[Any], enforce: bool = False
    ) -> tuple[bool, list]:
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
        # Update drift detector's provider references
        self.drift_detector.providers = self.providers
        return self.drift_detector.detect(env_name)

    def plan(
        self,
        env_name: str,
        dry_run: bool = False,
        resource_filter: list[str] | None = None,
        enforce_policies: bool = False,
    ) -> dict[str, Any]:
        """Plan infrastructure changes.

        Args:
            env_name: Environment name
            dry_run: If True, only show what would be done
            resource_filter: Optional list of resource names to target
            enforce_policies: If True, block on policy violations

        Returns:
            Dict with plan results per provider
        """
        # Create deployment record
        deployment_id = self.state_manager.create_deployment(
            environment=env_name,
            command="plan",
            user=self._current_user,
            dry_run=dry_run,
            metadata={"resource_filter": resource_filter},
        )

        # Emit before_plan event
        self.event_manager.emit_event(
            EventType.BEFORE_PLAN,
            env_name,
            {"deployment_id": deployment_id, "dry_run": dry_run},
        )

        results = {}

        try:
            if resource_filter:
                self.console.print(
                    f"\n[bold cyan]Planning infrastructure for: {env_name} "
                    f"(resources: {', '.join(resource_filter)})[/bold cyan]"
                )
            else:
                self.console.print(
                    f"\n[bold cyan]Planning infrastructure for: {env_name}[/bold cyan]"
                )

            # Get all resources and discover providers dynamically
            all_resources = self.config_manager.get_all_resources_all_providers(env_name)

            # Check policies if there are any defined
            if self.policy_engine.policies:
                self.check_policies(env_name, all_resources, enforce=enforce_policies)

            # Group resources by provider
            resources_by_provider: dict[str, list[Any]] = {}
            for resource in all_resources:
                if resource.provider not in resources_by_provider:
                    resources_by_provider[resource.provider] = []
                resources_by_provider[resource.provider].append(resource)

            for provider_name, resources in resources_by_provider.items():
                if provider_name not in self.providers:
                    self.console.print(
                        f"[yellow]Warning: Provider '{provider_name}' not registered[/yellow]"
                    )
                    continue

                provider = self.providers[provider_name]

                # Validate resources before processing
                self.validate_resources(resources)

                # Filter resources if specified
                if resource_filter:
                    original_count = len(resources)
                    resources = [r for r in resources if r.name in resource_filter]
                    if not resources:
                        continue  # Skip provider if no matching resources
                    self.console.print(
                        f"\n[bold]{provider_name}[/bold]: {len(resources)} of "
                        f"{original_count} resources (filtered)"
                    )
                else:
                    self.console.print(
                        f"\n[bold]{provider_name}[/bold]: {len(resources)} resources"
                    )

                # Track resources in state
                for resource in resources:
                    tracked_resource = self.state_manager.track_resource(
                        deployment_id=deployment_id,
                        environment=env_name,
                        provider=provider_name,
                        resource_type=resource.type,
                        name=resource.name,
                        state=ResourceState.PLANNED,
                        config=resource.config,
                    )
                    self.event_manager.emit_event(
                        EventType.RESOURCE_PLANNED,
                        env_name,
                        {
                            "resource_id": tracked_resource.id,
                            "provider": provider_name,
                            "name": resource.name,
                        },
                    )

                if dry_run:
                    self.console.print("  [dim]Would generate Terraform and Ansible files[/dim]")
                    results[provider_name] = {"resources": len(resources), "dry_run": True}
                    continue

                # Set environment for provider to ensure correct output directory
                provider.set_environment(env_name)

                # Generate Terraform and Ansible files
                provider.ensure_directories()
                provider.generate_terraform(resources)
                provider.generate_ansible(resources)

                # Export secrets for this provider
                try:
                    secrets_file = f"{provider_name}.yaml"
                    tf_vars = provider.terraform_dir / "secrets.auto.tfvars"
                    self.secret_manager.export_for_terraform(secrets_file, tf_vars)
                except FileNotFoundError:
                    self.console.print(f"[yellow]No secrets file for {provider_name}[/yellow]")

                # Run terraform plan
                self.console.print("  [dim]Running terraform plan...[/dim]")
                tf_result = self.terraform_runner.run(provider, "plan", auto_approve=False)

                results[provider_name] = {
                    "resources": len(resources),
                    "terraform_plan": tf_result,
                }

            # Mark deployment as completed
            self.state_manager.update_deployment_status(deployment_id, DeploymentStatus.COMPLETED)

            # Emit after_plan event
            self.event_manager.emit_event(
                EventType.AFTER_PLAN,
                env_name,
                {"deployment_id": deployment_id, "results": results},
            )

        except Exception as e:
            # Mark deployment as failed
            self.state_manager.update_deployment_status(
                deployment_id, DeploymentStatus.FAILED, str(e)
            )
            self.event_manager.emit_event(
                EventType.PLAN_FAILED, env_name, {"deployment_id": deployment_id, "error": str(e)}
            )
            raise

        return results

    def apply(
        self,
        env_name: str,
        auto_approve: bool = False,
        resource_filter: list[str] | None = None,
        parallel: bool = False,
        max_workers: int = 4,
    ) -> dict[str, Any]:
        """Apply infrastructure changes.

        Args:
            env_name: Environment name
            auto_approve: If True, skip confirmation prompts
            resource_filter: Optional list of resource names to target
            parallel: If True, apply resources in parallel where possible
            max_workers: Maximum number of parallel workers (default: 4)

        Returns:
            Dict with apply results per provider
        """
        # First, generate the plans
        self.plan(env_name, dry_run=False, resource_filter=resource_filter)

        # Create deployment record for apply
        deployment_id = self.state_manager.create_deployment(
            environment=env_name,
            command="apply",
            user=self._current_user,
            dry_run=False,
            metadata={"resource_filter": resource_filter, "auto_approve": auto_approve},
        )

        # Emit before_apply event
        self.event_manager.emit_event(
            EventType.BEFORE_APPLY,
            env_name,
            {"deployment_id": deployment_id, "auto_approve": auto_approve},
        )

        results = {}

        try:
            if resource_filter:
                self.console.print(
                    f"\n[bold green]Applying infrastructure for: {env_name} "
                    f"(resources: {', '.join(resource_filter)})[/bold green]"
                )
            else:
                self.console.print(
                    f"\n[bold green]Applying infrastructure for: {env_name}[/bold green]"
                )

            # Get all resources and discover providers dynamically
            all_resources = self.config_manager.get_all_resources_all_providers(env_name)

            # Capture configuration snapshot for rollback
            rollback_snapshot = {
                "environment": env_name,
                "timestamp": datetime.utcnow().isoformat(),
                "resources": [
                    {
                        "provider": r.provider,
                        "type": r.type,
                        "name": r.name,
                        "config": r.config,
                    }
                    for r in all_resources
                ],
            }

            # Store rollback data in deployment
            self.state_manager.update_deployment_rollback_data(
                deployment_id=deployment_id, rollback_data=rollback_snapshot
            )

            # Group resources by provider
            resources_by_provider: dict[str, list[Any]] = {}
            for resource in all_resources:
                if resource.provider not in resources_by_provider:
                    resources_by_provider[resource.provider] = []
                resources_by_provider[resource.provider].append(resource)

            # Apply providers (parallel or serial based on flag)
            if parallel and len(resources_by_provider) > 1:
                results = self._apply_providers_parallel(
                    env_name=env_name,
                    deployment_id=deployment_id,
                    resources_by_provider=resources_by_provider,
                    resource_filter=resource_filter,
                    auto_approve=auto_approve,
                    max_workers=max_workers,
                )
            else:
                results = self._apply_providers_serial(
                    env_name=env_name,
                    deployment_id=deployment_id,
                    resources_by_provider=resources_by_provider,
                    resource_filter=resource_filter,
                    auto_approve=auto_approve,
                )

            # Mark deployment as completed
            self.state_manager.update_deployment_status(deployment_id, DeploymentStatus.COMPLETED)

            # Emit after_apply event
            self.event_manager.emit_event(
                EventType.AFTER_APPLY,
                env_name,
                {"deployment_id": deployment_id, "results": results},
            )

        except Exception as e:
            # Mark deployment as failed
            self.state_manager.update_deployment_status(
                deployment_id, DeploymentStatus.FAILED, str(e)
            )
            self.event_manager.emit_event(
                EventType.APPLY_FAILED, env_name, {"deployment_id": deployment_id, "error": str(e)}
            )
            raise

        return results

    def _apply_providers_serial(
        self,
        env_name: str,
        deployment_id: int,
        resources_by_provider: dict[str, list[Any]],
        resource_filter: list[str] | None,
        auto_approve: bool,
    ) -> dict[str, Any]:
        """Apply providers sequentially."""
        self.deployment_executor.providers = self.providers
        return self.deployment_executor.apply_serial(
            env_name, deployment_id, resources_by_provider, resource_filter, auto_approve
        )

    def _apply_providers_parallel(
        self,
        env_name: str,
        deployment_id: int,
        resources_by_provider: dict[str, list[Any]],
        resource_filter: list[str] | None,
        auto_approve: bool,
        max_workers: int,
    ) -> dict[str, Any]:
        """Apply providers in parallel."""
        self.deployment_executor.providers = self.providers
        return self.deployment_executor.apply_parallel(
            env_name,
            deployment_id,
            resources_by_provider,
            resource_filter,
            auto_approve,
            max_workers,
        )

    def _apply_single_provider(
        self,
        env_name: str,
        deployment_id: int,
        provider_name: str,
        provider: ProviderBase,
        resources: list[Any],
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
    ) -> dict[str, Any]:
        """Destroy infrastructure.

        Args:
            env_name: Environment name
            auto_approve: If True, skip confirmation prompts
            resource_filter: Optional list of resource names to target

        Returns:
            Dict with destroy results per provider
        """
        # Create deployment record for destroy
        deployment_id = self.state_manager.create_deployment(
            environment=env_name,
            command="destroy",
            user=self._current_user,
            dry_run=False,
            metadata={"resource_filter": resource_filter, "auto_approve": auto_approve},
        )

        # Emit before_destroy event
        self.event_manager.emit_event(
            EventType.BEFORE_DESTROY,
            env_name,
            {"deployment_id": deployment_id, "auto_approve": auto_approve},
        )

        results = {}

        try:
            if resource_filter:
                self.console.print(
                    f"\n[bold red]Destroying infrastructure for: {env_name} "
                    f"(resources: {', '.join(resource_filter)})[/bold red]"
                )
            else:
                self.console.print(
                    f"\n[bold red]Destroying infrastructure for: {env_name}[/bold red]"
                )

            if not auto_approve:
                response = input("Are you sure you want to destroy? (yes/no): ")
                if response.lower() != "yes":
                    self.console.print("[yellow]Aborted[/yellow]")
                    # Mark deployment as failed with abort message
                    self.state_manager.update_deployment_status(
                        deployment_id, DeploymentStatus.FAILED, "User aborted"
                    )
                    return {}

            # Get all resources and discover providers dynamically
            all_resources = self.config_manager.get_all_resources_all_providers(env_name)

            # Group resources by provider
            resources_by_provider: dict[str, list[Any]] = {}
            for resource in all_resources:
                if resource.provider not in resources_by_provider:
                    resources_by_provider[resource.provider] = []
                resources_by_provider[resource.provider].append(resource)

            for provider_name, resources in resources_by_provider.items():
                if provider_name not in self.providers:
                    continue

                provider = self.providers[provider_name]

                # Check if any resources match filter for this provider
                if resource_filter:
                    resources = [r for r in resources if r.name in resource_filter]
                    if not resources:
                        continue  # Skip provider if no matching resources

                self.console.print(f"\n[bold]Destroying {provider_name}...[/bold]")

                # Set environment for provider to ensure correct output directory
                provider.set_environment(env_name)

                # Track resources being destroyed and store their IDs
                resource_ids = {}
                for resource in resources:
                    tracked_resource = self.state_manager.track_resource(
                        deployment_id=deployment_id,
                        environment=env_name,
                        provider=provider_name,
                        resource_type=resource.type,
                        name=resource.name,
                        state=ResourceState.DELETING,
                        config=resource.config,
                    )
                    resource_ids[resource.name] = tracked_resource.id
                    self.event_manager.emit_event(
                        EventType.RESOURCE_DELETING,
                        env_name,
                        {
                            "resource_id": tracked_resource.id,
                            "provider": provider_name,
                            "name": resource.name,
                        },
                    )

                # Run Terraform destroy
                tf_result = self.terraform_runner.run(provider, "destroy", auto_approve)

                # Update resource states to DELETED after successful destroy
                for resource in resources:
                    if resource.name in resource_ids:
                        self.state_manager.update_resource_state(
                            resource_id=resource_ids[resource.name],
                            state=ResourceState.DELETED,
                        )
                        self.event_manager.emit_event(
                            EventType.RESOURCE_DELETED,
                            env_name,
                            {"provider": provider_name, "name": resource.name},
                        )

                results[provider_name] = {"terraform": tf_result}

            # Mark deployment as completed
            self.state_manager.update_deployment_status(deployment_id, DeploymentStatus.COMPLETED)

            # Emit after_destroy event
            self.event_manager.emit_event(
                EventType.AFTER_DESTROY,
                env_name,
                {"deployment_id": deployment_id, "results": results},
            )

        except Exception as e:
            # Mark deployment as failed
            self.state_manager.update_deployment_status(
                deployment_id, DeploymentStatus.FAILED, str(e)
            )
            self.event_manager.emit_event(
                EventType.DESTROY_FAILED,
                env_name,
                {"deployment_id": deployment_id, "error": str(e)},
            )
            raise

        return results

    def rollback(self, deployment_id: int, auto_approve: bool = False) -> dict[str, Any]:
        """Rollback infrastructure to a previous deployment state.

        Args:
            deployment_id: ID of deployment to rollback to
            auto_approve: If True, skip confirmation prompts

        Returns:
            Dict with rollback results

        Raises:
            ValueError: If deployment not found or has no rollback data
        """
        # Get deployment with rollback data
        deployment = self.state_manager.get_deployment_by_id(deployment_id)
        if not deployment:
            raise ValueError(f"Deployment {deployment_id} not found")

        if not deployment.rollback_data:
            raise ValueError(f"Deployment {deployment_id} has no rollback data")

        rollback_data = deployment.rollback_data
        env_name = rollback_data["environment"]

        self.console.print(
            f"\n[bold yellow]Rolling back {env_name} to deployment {deployment_id}[/bold yellow]"
        )
        self.console.print(
            f"[dim]Deployment from: {deployment.started_at.strftime('%Y-%m-%d %H:%M:%S')}[/dim]"
        )
        self.console.print(f"[dim]Resources: {len(rollback_data.get('resources', []))}[/dim]\n")

        if not auto_approve:
            confirm = input("Are you sure you want to rollback? (yes/no): ")
            if confirm.lower() != "yes":
                self.console.print("[yellow]Rollback cancelled.[/yellow]")
                return {}

        # Create deployment record for rollback
        rollback_deployment_id = self.state_manager.create_deployment(
            environment=env_name,
            command="apply",
            user=self._current_user,
            dry_run=False,
            metadata={"rollback_from": deployment_id, "rollback": True},
        )

        try:
            # Write rollback configurations to temporary files
            # For now, we'll use the current config structure and rely on users
            # having the correct configuration in their repo
            # In a production system, you'd want to write the configs to temp files

            self.console.print(
                f"\n[bold yellow]⚠ Note: Rollback requires the configuration "
                f"repository to be at the state from deployment {deployment_id}[/bold yellow]"
            )
            self.console.print(
                "[dim]Consider using git to checkout the appropriate commit if needed.[/dim]\n"
            )

            # Apply the infrastructure using current configuration
            # This assumes the user has set their config repo to the correct state
            results = self.apply(env_name, auto_approve=True, resource_filter=None)

            self.state_manager.update_deployment_status(
                rollback_deployment_id, DeploymentStatus.COMPLETED
            )

            self.console.print(
                f"\n[bold green]✓ Rollback to deployment {deployment_id} completed![/bold green]"
            )

            return results

        except Exception as e:
            self.state_manager.update_deployment_status(
                rollback_deployment_id, DeploymentStatus.FAILED, str(e)
            )
            self.console.print(f"\n[bold red]✗ Rollback failed: {e}[/bold red]")
            raise

    def status(self, env_name: str) -> None:
        """Show status of infrastructure.

        Args:
            env_name: Environment name
        """
        table = Table(title=f"Infrastructure Status: {env_name}")
        table.add_column("Provider", style="cyan")
        table.add_column("Resources", style="magenta")
        table.add_column("Status", style="green")

        # Get all resources and discover providers dynamically
        all_resources = self.config_manager.get_all_resources_all_providers(env_name)

        # Group resources by provider
        resources_by_provider: dict[str, list[Any]] = {}
        for resource in all_resources:
            if resource.provider not in resources_by_provider:
                resources_by_provider[resource.provider] = []
            resources_by_provider[resource.provider].append(resource)

        for provider_name, resources in sorted(resources_by_provider.items()):
            if provider_name not in self.providers:
                table.add_row(provider_name, "N/A", "[yellow]Not registered[/yellow]")
                continue

            provider = self.providers[provider_name]

            # Check if Terraform state exists
            state_file = provider.terraform_dir / "terraform.tfstate"
            status = "[green]Deployed[/green]" if state_file.exists() else "[dim]Not deployed[/dim]"

            table.add_row(provider_name, str(len(resources)), status)

        self.console.print(table)
