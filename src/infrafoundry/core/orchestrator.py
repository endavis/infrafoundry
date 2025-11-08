"""Core orchestration for infrastructure deployment."""

import os
import subprocess
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table

from infrafoundry.core.config import ConfigManager
from infrafoundry.core.events import EventManager, EventType
from infrafoundry.core.provider import ProviderBase
from infrafoundry.core.secrets import SecretManager
from infrafoundry.core.state import DeploymentStatus, ResourceState, StateManager


class Orchestrator:
    """Orchestrates infrastructure deployment across providers."""

    def __init__(
        self,
        config_manager: ConfigManager,
        secret_manager: SecretManager,
        output_dir: Path | None = None,
        state_manager: StateManager | None = None,
        event_manager: EventManager | None = None,
    ) -> None:
        """Initialize orchestrator.

        Args:
            config_manager: Configuration manager instance
            secret_manager: Secret manager instance
            output_dir: Directory for generated files (defaults to ./generated)
            state_manager: State manager instance (creates default if None)
            event_manager: Event manager instance (creates default if None)
        """
        self.config_manager = config_manager
        self.secret_manager = secret_manager
        self.output_dir = output_dir or Path.cwd() / "generated"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.console = Console()
        self.providers: dict[str, ProviderBase] = {}

        # Initialize state and event managers
        self.state_manager = state_manager or StateManager()
        self.event_manager = event_manager or EventManager()

        # Get current user for tracking
        self._current_user = os.environ.get("USER") or os.environ.get("USERNAME") or "unknown"

    def register_provider(self, provider: ProviderBase) -> None:
        """Register a provider plugin.

        Args:
            provider: Provider instance to register
        """
        self.providers[provider.name] = provider

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

    def build_dependency_graph(self, env_name: str) -> "DependencyGraph":
        """Build dependency graph for an environment.

        Args:
            env_name: Environment name

        Returns:
            DependencyGraph with all resources and dependencies
        """
        from infrafoundry.core.dependencies import DependencyGraph

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

    def plan(
        self, env_name: str, dry_run: bool = False, resource_filter: list[str] | None = None
    ) -> dict[str, Any]:
        """Plan infrastructure changes.

        Args:
            env_name: Environment name
            dry_run: If True, only show what would be done
            resource_filter: Optional list of resource names to target

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
                tf_result = self._run_terraform(provider, "plan", auto_approve=False)

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
    ) -> dict[str, Any]:
        """Apply infrastructure changes.

        Args:
            env_name: Environment name
            auto_approve: If True, skip confirmation prompts
            resource_filter: Optional list of resource names to target

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

                self.console.print(f"\n[bold]Applying {provider_name}...[/bold]")

                # Track resources being applied and store their IDs
                resource_ids = {}
                for resource in resources:
                    tracked_resource = self.state_manager.track_resource(
                        deployment_id=deployment_id,
                        environment=env_name,
                        provider=provider_name,
                        resource_type=resource.type,
                        name=resource.name,
                        state=ResourceState.CREATING,
                        config=resource.config,
                    )
                    resource_ids[resource.name] = tracked_resource.id
                    self.event_manager.emit_event(
                        EventType.RESOURCE_CREATING,
                        env_name,
                        {
                            "resource_id": tracked_resource.id,
                            "provider": provider_name,
                            "name": resource.name,
                        },
                    )

                # Run Terraform apply
                tf_result = self._run_terraform(provider, "apply", auto_approve)

                # Run Ansible playbook (check mode for dry run)
                ansible_result = self._run_ansible(provider, check_mode=not auto_approve)

                # Update resource states to ACTIVE after successful apply
                for resource in resources:
                    if resource.name in resource_ids:
                        self.state_manager.update_resource_state(
                            resource_id=resource_ids[resource.name],
                            state=ResourceState.ACTIVE,
                        )
                        self.event_manager.emit_event(
                            EventType.RESOURCE_CREATED,
                            env_name,
                            {"provider": provider_name, "name": resource.name},
                        )

                results[provider_name] = {
                    "terraform": tf_result,
                    "ansible": ansible_result,
                }

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
                tf_result = self._run_terraform(provider, "destroy", auto_approve)

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

    def _run_terraform(
        self, provider: ProviderBase, command: str, auto_approve: bool = False
    ) -> dict[str, Any]:
        """Run Terraform command for a provider.

        Args:
            provider: Provider instance
            command: Terraform command (plan, apply, destroy)
            auto_approve: If True, add -auto-approve flag

        Returns:
            Dict with command results
        """
        tf_dir = provider.terraform_dir

        # Initialize if needed
        if not (tf_dir / ".terraform").exists():
            self.console.print("[dim]Initializing Terraform...[/dim]")
            subprocess.run(["terraform", "init"], cwd=tf_dir, check=True)

        # Build command
        cmd = ["terraform", command]
        if auto_approve and command in {"apply", "destroy"}:
            cmd.append("-auto-approve")

        # Run command
        result = subprocess.run(cmd, cwd=tf_dir, capture_output=False)

        return {"exit_code": result.returncode, "success": result.returncode == 0}

    def _run_ansible(self, provider: ProviderBase, check_mode: bool = True) -> dict[str, Any]:
        """Run Ansible playbook for a provider.

        Args:
            provider: Provider instance
            check_mode: If True, run in check mode (dry run)

        Returns:
            Dict with command results
        """
        ansible_dir = provider.ansible_dir
        playbook = ansible_dir / "playbook.yml"
        inventory = ansible_dir / "inventory.yml"

        if not playbook.exists():
            self.console.print("[dim]No Ansible playbook found, skipping...[/dim]")
            return {"skipped": True}

        # Build command
        cmd = ["ansible-playbook", "-i", str(inventory), str(playbook)]
        if check_mode:
            cmd.append("--check")
            self.console.print("[dim]Running Ansible in check mode (dry run)...[/dim]")
        else:
            self.console.print("[dim]Running Ansible playbook...[/dim]")

        # Run command
        try:
            result = subprocess.run(cmd, cwd=ansible_dir, capture_output=False)
            return {"exit_code": result.returncode, "success": result.returncode == 0}
        except FileNotFoundError:
            self.console.print(
                "[yellow]ansible-playbook not found. Install Ansible to use this feature.[/yellow]"
            )
            return {"error": "ansible-playbook not found", "success": False}

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
