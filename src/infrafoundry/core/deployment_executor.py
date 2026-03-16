import logging
import traceback
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, cast

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from infrafoundry.core.config.models import IaCTool
from infrafoundry.core.events import EventManager, EventType
from infrafoundry.core.exceptions import InfraFoundryError, ResourceFilterError
from infrafoundry.core.execution_planner import ExecutionPlanner
from infrafoundry.core.protocols import Applyable, StateAware
from infrafoundry.core.provider import ProviderBase, ResourceConfig
from infrafoundry.core.runners import RunnerRegistry
from infrafoundry.core.runners.base_runner import BaseRunner
from infrafoundry.core.state import ResourceState, StateManager
from infrafoundry.core.types import ResourceEventData, ResourceOutcome, RunnerEventData

logger = logging.getLogger(__name__)

# Registry keys for mutually exclusive IaC runners
_IAC_TOOL_KEYS = {tool.value for tool in IaCTool}


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
        self.iac_tool: IaCTool = IaCTool.TERRAFORM

        # Create execution planner with configured provider order
        self.execution_planner = ExecutionPlanner(provider_order=provider_order)

        # Dynamically create all registered runners
        self.runners: dict[str, BaseRunner] = {}
        for tool_name in self.runner_registry.list_runners():
            runner = self.runner_registry.create_runner(tool_name, console=self.console)
            if runner:
                self.runners[tool_name] = runner

    def _validate_resource_filter(
        self,
        resources_by_provider: dict[str, list[ResourceConfig]],
        filter_set: set[str],
    ) -> None:
        """Validate that resource filter matches at least one resource.

        Args:
            resources_by_provider: Dict mapping provider names to resources
            filter_set: Set of resource names to filter by

        Raises:
            ResourceFilterError: If no resources match the filter
        """
        all_resource_names: set[str] = set()
        matched_names: set[str] = set()
        for resources in resources_by_provider.values():
            for r in resources:
                all_resource_names.add(r.name)
                if r.name in filter_set:
                    matched_names.add(r.name)

        unmatched = filter_set - matched_names
        if not matched_names:
            raise ResourceFilterError(
                f"No resources matched filter: {', '.join(sorted(filter_set))}. "
                f"Available resources: {', '.join(sorted(all_resource_names))}"
            )
        elif unmatched:
            self.console.print(
                f"[yellow]Warning: Some resources not found: "
                f"{', '.join(sorted(unmatched))}[/yellow]"
            )

    def _get_sorted_runners(self) -> list[tuple[str, BaseRunner]]:
        """Get runners sorted by priority, filtering by configured IaC tool.

        Only the IaC runner matching ``self.iac_tool`` is included; the other
        IaC runner is skipped.  Non-IaC runners (Ansible, PyInfra, etc.) are
        always included.

        Priority is determined by:
        1. Environment config override (if present)
        2. Runner class default priority
        3. Registration order (implicit stability of sort)

        Returns:
            List of (tool_name, runner) tuples sorted by priority.
        """
        active_iac = self.iac_tool.value

        def get_priority(item: tuple[str, BaseRunner]) -> int:
            name, runner = item
            # Check for override first
            if name in self.runner_priorities:
                return self.runner_priorities[name]
            # Fallback to default
            return runner.priority

        filtered = {
            name: runner
            for name, runner in self.runners.items()
            if name not in _IAC_TOOL_KEYS or name == active_iac
        }
        return sorted(filtered.items(), key=get_priority)

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

        # Validate resource filter before proceeding
        if filter_set:
            self._validate_resource_filter(resources_by_provider, filter_set)

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
                resource_filter=resource_filter,
            )
            results[provider_name] = result

        # Emit aggregate RESOURCE_CREATED event AFTER all providers complete.
        # This ensures group handlers (requires: [...]) only fire once when
        # all required resources exist across all providers.
        seen_created: set[str] = set()
        all_created: list[str] = []
        for result in results.values():
            if isinstance(result, dict):
                for tool_result in result.values():
                    if isinstance(tool_result, dict):
                        for outcome in tool_result.get("resource_outcomes", []):
                            name = (
                                outcome.get("resource_name", "")
                                if isinstance(outcome, dict)
                                else ""
                            )
                            action = outcome.get("action", "") if isinstance(outcome, dict) else ""
                            if action == "create" and name and name not in seen_created:
                                seen_created.add(name)
                                all_created.append(name)
        if all_created:
            self.event_manager.emit_event(
                EventType.RESOURCE_CREATED,
                env_name,
                {"action": "create", "resources": all_created},
                target_resources=all_created,
            )

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

        # Validate resource filter before proceeding
        if filter_set:
            self._validate_resource_filter(resources_by_provider, filter_set)

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
                        resource_filter=resource_filter,
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
        resource_filter: list[str] | None = None,
    ) -> dict[str, Any]:
        """Apply a single provider's resources.

        Only IaC runners (Terraform, OpenTofu) auto-run.  Non-IaC runners
        (Ansible, PyInfra) are skipped here; they run as resource-level
        event handlers instead.

        After the IaC runner completes, resource lifecycle events
        (``on_create``, ``on_update``, ``on_destroy``) are fired based
        on the actual terraform outcomes so that event handlers declared
        on each resource can execute.

        Args:
            env_name: Environment name
            deployment_id: Deployment ID
            provider_name: Provider name
            provider: Provider instance
            resources: List of resources to apply
            auto_approve: If True, skip confirmation prompts
            resource_filter: Optional list of resource names to target with -target

        Returns:
            Dict with apply results including terraform outcomes
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
                target_resources=resource_filter,
            )

        runner_results: dict[str, Any] = {}
        terraform_ids: dict[str, str] = {}
        all_outcomes: list[ResourceOutcome] = []

        for tool_name, runner in self._get_sorted_runners():
            # Only IaC runners auto-run; config tools run as event handlers
            if not runner.is_iac_runner:
                continue

            if not isinstance(runner, Applyable):
                self.console.print(f"  [dim]Skipping {tool_name}: does not support apply[/dim]")
                continue

            self.console.print(f"  [dim]Running {tool_name} apply...[/dim]")

            starting_event: RunnerEventData = {
                "provider": provider_name,
                "runner": tool_name,
                "phase": "apply",
            }
            warnings.warn(
                "RUNNER_STARTING event is deprecated. "
                "Use resource lifecycle events (on_create, on_update, on_destroy) instead.",
                DeprecationWarning,
                stacklevel=1,
            )
            self.event_manager.emit_event(
                EventType.RUNNER_STARTING,
                env_name,
                starting_event,
                provider=provider_name,
                runner=tool_name,
                target_resources=resource_filter,
            )

            try:
                run_result = runner.apply(
                    provider,
                    auto_approve=auto_approve,
                    target_resources=resource_filter if resource_filter else None,
                )
                runner_results[tool_name] = run_result

                # Collect resource outcomes from IaC runner
                raw_outcomes = run_result.get("resource_outcomes", [])
                outcomes = cast(list[ResourceOutcome], raw_outcomes)
                all_outcomes.extend(outcomes)

                completed_event: RunnerEventData = {
                    "provider": provider_name,
                    "runner": tool_name,
                    "phase": "apply",
                    "success": run_result.get("success", True),
                }
                warnings.warn(
                    "RUNNER_COMPLETED event is deprecated. "
                    "Use resource lifecycle events (on_create, on_update, on_destroy) instead.",
                    DeprecationWarning,
                    stacklevel=1,
                )
                self.event_manager.emit_event(
                    EventType.RUNNER_COMPLETED,
                    env_name,
                    completed_event,
                    provider=provider_name,
                    runner=tool_name,
                    target_resources=resource_filter,
                )
            except Exception as exc:
                failed_event: RunnerEventData = {
                    "provider": provider_name,
                    "runner": tool_name,
                    "phase": "apply",
                    "error": str(exc),
                }
                self.event_manager.emit_event(
                    EventType.RUNNER_FAILED,
                    env_name,
                    failed_event,
                    provider=provider_name,
                    runner=tool_name,
                    target_resources=resource_filter,
                )
                raise

            # Update state with resource IDs if the runner supports state tracking
            if run_result["success"] and isinstance(runner, StateAware):
                state_runner = cast(StateAware, runner)
                terraform_ids = state_runner.get_resource_ids(provider)
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
                    target_resources=[resource.name],
                )

        # Fire resource lifecycle events based on IaC outcomes
        self._fire_resource_lifecycle_events(
            env_name, provider_name, provider, resources, all_outcomes, resource_filter
        )

        # Replace ResourceOutcome objects with JSON-safe dicts for audit logging
        for result in runner_results.values():
            if isinstance(result, dict) and "resource_outcomes" in result:
                result["resource_outcomes"] = [
                    o.to_dict() if hasattr(o, "to_dict") else o for o in result["resource_outcomes"]
                ]

        return runner_results

    def _fire_resource_lifecycle_events(
        self,
        env_name: str,
        provider_name: str,
        provider: ProviderBase,
        resources: list[ResourceConfig],
        outcomes: list[ResourceOutcome],
        resource_filter: list[str] | None,
    ) -> None:
        """Fire resource lifecycle events based on terraform outcomes.

        Maps terraform actions to resource event keys and registers/executes
        any handlers declared in the resource's ``events`` configuration.
        Uses the provider's terraform resource type mapping to ensure that
        only primary terraform resources (not helper resources like
        cloud-init files) trigger event handlers.

        Args:
            env_name: Environment name
            provider_name: Provider name
            provider: Provider instance (used for terraform type mapping)
            resources: List of resource configurations
            outcomes: List of terraform resource outcomes
            resource_filter: Optional resource name filter
        """
        if not outcomes:
            return

        # Map action -> event key
        action_to_event_key: dict[str, str] = {
            "create": "on_create",
            "update": "on_update",
            "delete": "on_destroy",
        }

        # Build reverse map: terraform_type -> set of InfraFoundry types
        tf_type_map = provider.get_terraform_resource_types()
        tf_to_infra: dict[str, set[str]] = {}
        for infra_type, tf_types in tf_type_map.items():
            for tf_type in tf_types:
                tf_to_infra.setdefault(tf_type, set()).add(infra_type)

        # Build resource lookup by name
        resource_by_name: dict[str, ResourceConfig] = {r.name: r for r in resources}

        for outcome in outcomes:
            event_key = action_to_event_key.get(outcome.action)
            if not event_key:
                continue

            resource = resource_by_name.get(outcome.resource_name)
            if not resource or not resource.events:
                continue

            # Extract terraform resource type from address (part before the dot)
            tf_type = outcome.address.split(".")[0] if "." in outcome.address else ""

            # Only fire if the terraform type maps to this resource's InfraFoundry type
            allowed_infra_types = tf_to_infra.get(tf_type, set())
            if resource.type not in allowed_infra_types:
                continue

            handlers = resource.events.get(event_key, [])
            if not handlers:
                continue

            logger.info(
                "Firing %s handlers for resource '%s' (action=%s)",
                event_key,
                outcome.resource_name,
                outcome.action,
            )

            # Register and fire handlers for this resource event
            for handler_config in handlers:
                try:
                    self.event_manager.register_handler(
                        EventType.RESOURCE_CREATED
                        if outcome.action == "create"
                        else EventType.RESOURCE_UPDATED
                        if outcome.action == "update"
                        else EventType.RESOURCE_DELETED,
                        handler_config,
                    )
                except ValueError as e:
                    logger.error(
                        "Failed to register %s handler for resource '%s': %s",
                        event_key,
                        outcome.resource_name,
                        e,
                    )
                    continue

            # Emit per-resource event for resource-level handlers.
            # Pass only the single resource name as target so that group
            # handlers with ``requires`` don't match individual emissions.
            event_type = (
                EventType.RESOURCE_CREATED
                if outcome.action == "create"
                else EventType.RESOURCE_UPDATED
                if outcome.action == "update"
                else EventType.RESOURCE_DELETED
            )
            self.event_manager.emit_event(
                event_type,
                env_name,
                {
                    "provider": provider_name,
                    "name": outcome.resource_name,
                    "address": outcome.address,
                    "action": outcome.action,
                },
                provider=provider_name,
                resource=outcome.resource_name,
                target_resources=[outcome.resource_name],
            )

        # NOTE: Aggregate events for group handlers (requires: [...]) are NOT
        # emitted here. They must be emitted after ALL providers complete to
        # avoid firing before all required resources exist. See apply_serial().
