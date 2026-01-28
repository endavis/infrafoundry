import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, cast

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from infrafoundry.core.events import EventManager, EventType
from infrafoundry.core.exceptions import InfraFoundryError
from infrafoundry.core.execution_planner import ExecutionPlanner
from infrafoundry.core.protocols import Applyable, StateAware
from infrafoundry.core.provider import ProviderBase, ResourceConfig
from infrafoundry.core.runners import RunnerRegistry
from infrafoundry.core.runners.base_runner import BaseRunner
from infrafoundry.core.state import ResourceState, StateManager
from infrafoundry.core.types import ResourceEventData


class DeploymentExecutor:
    """Executes infrastructure deployments across providers."""

    def __init__(
        self,
        runner_registry: RunnerRegistry,
        state_manager: StateManager,
        event_manager: EventManager,
        providers: dict[str, ProviderBase],
        console: Console | None = None,
        runner_priorities: dict[str, int] | None = None,
        provider_order: list[str] | None = None,
    ) -> None:
        """Initialize deployment executor.

        Args:
            runner_registry: Registry for creating tool runners
            state_manager: State manager for tracking resources
            event_manager: Event manager for notifications
            providers: Dict of registered provider instances
            console: Rich console for output (creates default if None)
            runner_priorities: Optional dict mapping runner names to priorities
            provider_order: Optional list defining provider execution order.
                           Providers earlier in the list are executed first.
        """
        self.runner_registry = runner_registry
        self.state_manager = state_manager
        self.event_manager = event_manager
        self.providers = providers
        self.console = console or Console()
        self.runner_priorities = runner_priorities or {}
        self.provider_order = provider_order

        # Create execution planner with configured provider order
        self.execution_planner = ExecutionPlanner(provider_order=provider_order)

        # Dynamically create all registered runners
        self.runners: dict[str, BaseRunner] = {}
        for tool_name in self.runner_registry.list_runners():
            runner = self.runner_registry.create_runner(tool_name, console=self.console)
            if runner:
                self.runners[tool_name] = runner

    def _get_sorted_runners(self) -> list[tuple[str, BaseRunner]]:
        """Get runners sorted by priority.

        Priority is determined by:
        1. Environment config override (if present)
        2. Runner class default priority
        3. Registration order (implicit stability of sort)

        Returns:
            List of (tool_name, runner) tuples sorted by priority.
        """

        def get_priority(item: tuple[str, BaseRunner]) -> int:
            name, runner = item
            # Check for override first
            if name in self.runner_priorities:
                return self.runner_priorities[name]
            # Fallback to default
            return runner.priority

        return sorted(self.runners.items(), key=get_priority)

    def apply_serial(
        self,
        env_name: str,
        deployment_id: int,
        resources_by_provider: dict[str, list[ResourceConfig]],
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

        # Convert to set for O(1) lookups
        filter_set = set(resource_filter) if resource_filter else None

        # Sort providers using execution planner (forward order for apply)
        sorted_providers = self.execution_planner.sort_providers(
            list(resources_by_provider.keys()), reverse=False
        )

        for provider_name in sorted_providers:
            if provider_name not in self.providers:
                continue

            provider = self.providers[provider_name]

            # Get resources for this provider
            resources = resources_by_provider[provider_name]

            # Check if any resources match filter for this provider
            if filter_set:
                resources = [r for r in resources if r.name in filter_set]
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
        resources_by_provider: dict[str, list[ResourceConfig]],
        resource_filter: list[str] | None,
        auto_approve: bool,
        max_workers: int,
    ) -> dict[str, Any]:
        """Apply providers in parallel, respecting provider execution order.

        Providers are processed in batches based on their execution order.
        Providers within the same batch can run in parallel, but batches
        are processed sequentially to respect provider dependencies.

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
        results: dict[str, Any] = {}

        # Convert to set for O(1) lookups
        filter_set = set(resource_filter) if resource_filter else None

        # Get execution batches from planner (forward order for apply)
        batches = self.execution_planner.plan_apply(resources_by_provider)

        total_providers = sum(len(batch.providers) for batch in batches)
        self.console.print(
            f"\n[bold cyan]Applying {total_providers} providers in {len(batches)} batch(es) "
            f"(max {max_workers} workers per batch)...[/bold cyan]"
        )

        # Process each batch sequentially
        for batch_idx, batch in enumerate(batches, 1):
            batch_providers = []

            # Filter to providers we have registered and have matching resources
            for provider_name in batch.providers:
                if provider_name not in self.providers:
                    continue

                resources = batch.resources_by_provider.get(provider_name, [])

                # Apply resource filter
                if filter_set:
                    resources = [r for r in resources if r.name in filter_set]
                    if not resources:
                        continue

                batch_providers.append((provider_name, resources))

            if not batch_providers:
                continue

            if len(batches) > 1:
                self.console.print(
                    f"\n[dim]Batch {batch_idx}/{len(batches)}: "
                    f"{', '.join(p[0] for p in batch_providers)}[/dim]"
                )

            # Run providers in this batch in parallel
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_provider: dict[Any, str] = {}

                for provider_name, resources in batch_providers:
                    provider = self.providers[provider_name]
                    provider.set_environment(env_name)

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
                        except InfraFoundryError as e:
                            self.console.print(f"[red]✗ {provider_name} failed: {e.message}[/red]")
                            if e.context:
                                self.console.print(f"  Context: {e.context}", style="dim red")
                            results[provider_name] = {"error": str(e)}
                        except Exception as e:
                            self.console.print(
                                f"[red]✗ {provider_name} failed (unexpected): {e}[/red]"
                            )
                            self.console.print(traceback.format_exc(), style="dim red")
                            results[provider_name] = {"error": str(e)}
                        progress.update(task, advance=1)

        return results

    def apply_single_provider(
        self,
        env_name: str,
        deployment_id: int,
        provider_name: str,
        provider: ProviderBase,
        resources: list[ResourceConfig],
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
        resource_ids: dict[str, int] = {}
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
            creating_event: ResourceEventData = {
                "resource_id": tracked_resource.id,
                "provider": provider_name,
                "name": resource.name,
                "terraform_id": tracked_resource.terraform_id,
            }
            self.event_manager.emit_event(
                EventType.RESOURCE_CREATING,
                env_name,
                creating_event,
            )

        runner_results: dict[str, Any] = {}
        terraform_ids: dict[str, str] = {}

        for tool_name, runner in self._get_sorted_runners():
            if not isinstance(runner, Applyable):
                self.console.print(f"  [dim]Skipping {tool_name}: does not support apply[/dim]")
                continue

            self.console.print(f"  [dim]Running {tool_name} apply...[/dim]")

            # Ansible interprets auto_approve=False as check mode (dry-run)
            # Other runners use it to skip confirmation prompts
            run_result = runner.apply(provider, auto_approve=auto_approve)
            runner_results[tool_name] = run_result

            # Update state with Terraform resource IDs if available
            if (
                tool_name == "terraform"
                and run_result["success"]
                and isinstance(runner, StateAware)
            ):
                state_runner = cast(StateAware, runner)
                terraform_ids = state_runner.get_resource_ids(provider)
                # Update tracked resources with Terraform IDs
                for resource_name, terraform_id in terraform_ids.items():
                    if resource_name in resource_ids:
                        db_resource_id = resource_ids[resource_name]
                        self.state_manager.update_resource(
                            resource_id=db_resource_id,
                            terraform_id=terraform_id,
                        )

        # Update resource states to ACTIVE after successful apply
        for resource in resources:
            if resource.name in resource_ids:
                self.state_manager.update_resource_state(
                    resource_id=resource_ids[resource.name],
                    state=ResourceState.ACTIVE,
                )
                created_event: ResourceEventData = {
                    "resource_id": resource_ids[resource.name],
                    "provider": provider_name,
                    "name": resource.name,
                    "terraform_id": terraform_ids.get(resource.name),
                }
                self.event_manager.emit_event(
                    EventType.RESOURCE_CREATED,
                    env_name,
                    created_event,
                )

        return runner_results
