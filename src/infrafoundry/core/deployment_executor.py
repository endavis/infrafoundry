"""Deployment execution for infrastructure resources."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from infrafoundry.core.events import EventManager, EventType
from infrafoundry.core.provider import ProviderBase
from infrafoundry.core.runners import AnsibleRunner, TerraformRunner
from infrafoundry.core.state import ResourceState, StateManager


class DeploymentExecutor:
    """Executes infrastructure deployments across providers."""

    def __init__(
        self,
        terraform_runner: TerraformRunner,
        ansible_runner: AnsibleRunner,
        state_manager: StateManager,
        event_manager: EventManager,
        providers: dict[str, ProviderBase],
        console: Console | None = None,
    ) -> None:
        """Initialize deployment executor.

        Args:
            terraform_runner: Terraform runner for infrastructure provisioning
            ansible_runner: Ansible runner for configuration management
            state_manager: State manager for tracking resources
            event_manager: Event manager for notifications
            providers: Dict of registered provider instances
            console: Rich console for output (creates default if None)
        """
        self.terraform_runner = terraform_runner
        self.ansible_runner = ansible_runner
        self.state_manager = state_manager
        self.event_manager = event_manager
        self.providers = providers
        self.console = console or Console()

    def apply_serial(
        self,
        env_name: str,
        deployment_id: int,
        resources_by_provider: dict[str, list[Any]],
        resource_filter: list[str] | None,
        auto_approve: bool,
    ) -> dict[str, Any]:
        """Apply providers sequentially.

        Args:
            env_name: Environment name
            deployment_id: Deployment ID
            resources_by_provider: Dict mapping provider names to resources
            resource_filter: Optional list of resource names to target
            auto_approve: If True, skip confirmation prompts

        Returns:
            Dict with apply results per provider
        """
        results = {}

        # Define provider execution order
        # Providers earlier in the list are applied first
        # This ensures network/DHCP config is ready before VMs
        provider_order = ["opnsense", "proxmox", "kubernetes"]

        # Sort providers by defined order, putting undefined ones at the end
        sorted_providers = sorted(
            resources_by_provider.keys(),
            key=lambda p: provider_order.index(p) if p in provider_order else len(provider_order),
        )

        for provider_name in sorted_providers:
            if provider_name not in self.providers:
                continue

            provider = self.providers[provider_name]

            # Get resources for this provider
            resources = resources_by_provider[provider_name]

            # Check if any resources match filter for this provider
            if resource_filter:
                resources = [r for r in resources if r.name in resource_filter]
                if not resources:
                    continue  # Skip provider if no matching resources

            self.console.print(f"\n[bold]Applying {provider_name}...[/bold]")

            # Set environment for provider to ensure correct output directory
            provider.set_environment(env_name)

            result = self.apply_single_provider(
                env_name=env_name,
                deployment_id=deployment_id,
                provider_name=provider_name,
                provider=provider,
                resources=resources,
                auto_approve=auto_approve,
            )
            results[provider_name] = result

        return results

    def apply_parallel(
        self,
        env_name: str,
        deployment_id: int,
        resources_by_provider: dict[str, list[Any]],
        resource_filter: list[str] | None,
        auto_approve: bool,
        max_workers: int,
    ) -> dict[str, Any]:
        """Apply providers in parallel.

        Args:
            env_name: Environment name
            deployment_id: Deployment ID
            resources_by_provider: Dict mapping provider names to resources
            resource_filter: Optional list of resource names to target
            auto_approve: If True, skip confirmation prompts
            max_workers: Maximum number of parallel workers

        Returns:
            Dict with apply results per provider
        """
        results = {}
        self.console.print(
            f"\n[bold cyan]Applying {len(resources_by_provider)} providers in parallel "
            f"(max {max_workers} workers)...[/bold cyan]"
        )

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all provider apply tasks
            future_to_provider = {}
            for provider_name, resources in resources_by_provider.items():
                if provider_name not in self.providers:
                    continue

                provider = self.providers[provider_name]

                # Set environment for provider to ensure correct output directory
                provider.set_environment(env_name)

                # Check if any resources match filter for this provider
                if resource_filter:
                    resources = [r for r in resources if r.name in resource_filter]
                    if not resources:
                        continue  # Skip provider if no matching resources

                future = executor.submit(
                    self.apply_single_provider,
                    env_name=env_name,
                    deployment_id=deployment_id,
                    provider_name=provider_name,
                    provider=provider,
                    resources=resources,
                    auto_approve=auto_approve,
                )
                future_to_provider[future] = provider_name

            # Collect results as they complete
            with Progress(
                SpinnerColumn(), TextColumn("[progress.description]{task.description}")
            ) as progress:
                task = progress.add_task(
                    "[cyan]Applying providers...", total=len(future_to_provider)
                )

                for future in as_completed(future_to_provider):
                    provider_name = future_to_provider[future]
                    try:
                        result = future.result()
                        results[provider_name] = result
                        self.console.print(f"[green]✓ {provider_name} completed[/green]")
                    except Exception as e:
                        self.console.print(f"[red]✗ {provider_name} failed: {e}[/red]")
                        results[provider_name] = {"error": str(e)}
                    progress.update(task, advance=1)

        return results

    def apply_single_provider(
        self,
        env_name: str,
        deployment_id: int,
        provider_name: str,
        provider: ProviderBase,
        resources: list[Any],
        auto_approve: bool,
    ) -> dict[str, Any]:
        """Apply a single provider's resources.

        Args:
            env_name: Environment name
            deployment_id: Deployment ID
            provider_name: Provider name
            provider: Provider instance
            resources: List of resources to apply
            auto_approve: If True, skip confirmation prompts

        Returns:
            Dict with apply results including terraform and ansible outcomes
        """
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
        tf_result = self.terraform_runner.run(provider, "apply", auto_approve)

        # Extract Terraform resource IDs from state if apply was successful
        if tf_result["success"]:
            terraform_ids = self.terraform_runner.get_resource_ids(provider)

            # Update tracked resources with Terraform IDs
            for resource_name, terraform_id in terraform_ids.items():
                if resource_name in resource_ids:
                    db_resource_id = resource_ids[resource_name]
                    # Update resource with Terraform ID
                    self.state_manager.update_resource(
                        resource_id=db_resource_id,
                        terraform_id=terraform_id,
                    )

        # Run Ansible playbook (check mode for dry run)
        ansible_result = self.ansible_runner.run(provider, check_mode=not auto_approve)

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

        return {
            "terraform": tf_result,
            "ansible": ansible_result,
        }
