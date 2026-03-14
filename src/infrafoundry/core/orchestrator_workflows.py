"""Supporting workflows for orchestrator operations."""

from __future__ import annotations

import traceback
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast

from rich.console import Console
from rich.table import Table

from infrafoundry.core.config import ConfigManager
from infrafoundry.core.config.models import EnvironmentConfig, IaCTool
from infrafoundry.core.drift_detector import DriftDetector
from infrafoundry.core.events import EventManager, EventType
from infrafoundry.core.exceptions import SecretNotFoundError
from infrafoundry.core.hooks import HookExecutionMixin, HookManager
from infrafoundry.core.protocols import Destroyable, Plannable
from infrafoundry.core.provider import ProviderBase, ResourceConfig
from infrafoundry.core.runners import RunnerRegistry
from infrafoundry.core.runners.base_runner import BaseRunner
from infrafoundry.core.secrets.secret_manager import SecretManager
from infrafoundry.core.state import DeploymentStatus, ResourceState, StateManager
from infrafoundry.core.types import (
    ApplyDeploymentMetadata,
    DestroyDeploymentMetadata,
    EnvironmentData,
    PlanDeploymentMetadata,
    RollbackData,
    RollbackDeploymentMetadata,
    RunnerEventData,
)
from infrafoundry.core.validation import ValidationReport

# Registry keys for mutually exclusive IaC runners
_IAC_TOOL_KEYS = {tool.value for tool in IaCTool}


@dataclass(slots=True)
class ProviderResourceBatch:
    """Represents the resources for a single provider after optional filtering."""

    name: str
    resources: list[ResourceConfig]
    original_count: int


class DriftOrchestrator:
    """Wrap drift detection to keep orchestrator slim."""

    def __init__(
        self,
        drift_detector: DriftDetector,
        get_providers: Callable[[], dict[str, ProviderBase]],
    ) -> None:
        self.drift_detector = drift_detector
        self._get_providers = get_providers

    def detect(self, env_name: str) -> dict[str, Any]:
        """Detect drift for the provided environment."""
        self.drift_detector.providers = self._get_providers()
        return self.drift_detector.detect(env_name)


class StatusOrchestrator:
    """Render provider/resource status tables."""

    def __init__(
        self,
        console: Console,
        config_manager: ConfigManager,
        get_providers: Callable[[], dict[str, ProviderBase]],
    ) -> None:
        self.console = console
        self.config_manager = config_manager
        self._get_providers = get_providers

    def show(self, env_name: str) -> None:
        """Print infrastructure status table."""
        table = Table(title=f"Infrastructure Status: {env_name}")
        table.add_column("Provider", style="cyan")
        table.add_column("Resources", style="magenta")
        table.add_column("Status", style="green")

        all_resources = self.config_manager.get_all_resources_all_providers(env_name)
        resources_by_provider: dict[str, list[ResourceConfig]] = {}
        for resource in all_resources:
            resources_by_provider.setdefault(resource.provider, []).append(resource)

        providers = self._get_providers()
        for provider_name in sorted(resources_by_provider.keys()):
            resources = resources_by_provider[provider_name]
            provider = providers.get(provider_name)
            if not provider:
                table.add_row(provider_name, "N/A", "[yellow]Not registered[/yellow]")
                continue

            state_file = provider.terraform_dir / "terraform.tfstate"
            status_message = (
                "[green]Deployed[/green]" if state_file.exists() else "[dim]Not deployed[/dim]"
            )
            table.add_row(provider_name, str(len(resources)), status_message)

        self.console.print(table)


class ValidationOrchestrator:
    """Handle per-provider validation, keeping Orchestrator lean."""

    def __init__(
        self,
        config_manager: ConfigManager,
        console: Console,
        get_providers: Callable[[], dict[str, ProviderBase]],
        load_resources: Callable[
            [str], tuple[list[ResourceConfig], dict[str, list[ResourceConfig]]]
        ],
        iter_provider_batches: Callable[
            [dict[str, list[ResourceConfig]], list[str] | None, bool, str | None],
            list[ProviderResourceBatch],
        ],
    ) -> None:
        self.config_manager = config_manager
        self.console = console
        self._get_providers = get_providers
        self._load_resources = load_resources
        self._iter_provider_batches = iter_provider_batches

    def validate(
        self,
        env_name: str,
        resource_filter: list[str] | None,
        verbose: bool,
    ) -> dict[str, Any]:
        """Perform validation for all providers in the environment."""
        self.console.print(f"\n[bold cyan]Validating configuration for: {env_name}[/bold cyan]\n")

        env_config = self.config_manager.load_environment(env_name)
        if not env_config:
            self.console.print(f"[red]✗ Environment '{env_name}' not found[/red]")
            return {}

        env_data = cast(EnvironmentData, env_config.model_dump())
        all_resources, resources_by_provider = self._load_resources(env_name)

        # Convert to set for O(1) lookups
        filter_set = set(resource_filter) if resource_filter else None

        filtered_resources = all_resources
        if filter_set:
            filtered_resources = [r for r in all_resources if r.name in filter_set]
            self.console.print(
                f"[yellow]Validating {len(filtered_resources)} resources: "
                f"{', '.join(filter_set)}[/yellow]\n"
            )

        results: dict[str, Any] = {}

        providers = self._get_providers()
        # Use forward order for validation (same as apply)
        for batch in self._iter_provider_batches(
            resources_by_provider, resource_filter, False, env_name
        ):
            provider_name = batch.name
            resources = batch.resources
            provider = providers.get(provider_name)
            if not provider:
                self.console.print(f"[yellow]⚠ Provider '{provider_name}' not loaded[/yellow]")
                continue

            report = ValidationReport()
            self.console.print(f"[bold]Validating {provider_name}...[/bold]")

            self._run_validation_checks(provider, env_data, resources, report)

            summary = report.get_summary()
            passed = not report.has_errors()
            results[provider_name] = {
                "passed": passed,
                "report": report,
                "errors": summary["errors"],
                "warnings": summary["warnings"],
                "checks": summary["total"],
            }

            self._print_summary(provider_name, summary, passed)
            if verbose or not passed:
                self._print_detailed_report(report, verbose)
            self.console.print()

        self._print_overall_summary(results)
        return results

    def _run_validation_checks(
        self,
        provider: ProviderBase,
        env_data: EnvironmentData,
        resources: list[ResourceConfig],
        report: ValidationReport,
    ) -> None:
        """Invoke provider validation hooks with error protection."""
        try:
            provider.validate_connectivity(env_data, report)
        except Exception as exc:
            self.console.print(f"[red]✗ Connectivity validation failed: {exc}[/red]")
            self.console.print(traceback.format_exc(), style="dim red")  # Log full traceback

        try:
            provider.validate_references(resources, env_data, report)
        except Exception as exc:
            self.console.print(f"[red]✗ Reference validation failed: {exc}[/red]")
            self.console.print(traceback.format_exc(), style="dim red")  # Log full traceback

    def _print_summary(self, provider_name: str, summary: dict[str, Any], passed: bool) -> None:
        """Render summary results to the console."""
        if passed:
            self.console.print(
                f"[green]✓ {provider_name}: {summary['passed']}/{summary['total']} "
                f"checks passed[/green]"
            )
            if summary["warnings"] > 0:
                self.console.print(f"  [yellow]⚠ {summary['warnings']} warnings[/yellow]")
        else:
            self.console.print(
                f"[red]✗ {provider_name}: {summary['errors']} errors, "
                f"{summary['warnings']} warnings[/red]"
            )

    def _print_detailed_report(self, report: ValidationReport, verbose: bool) -> None:
        """Print detailed report entries when helpful."""
        self.console.print("\nDetailed Results:")
        for result in report.results:
            if result.passed:
                if verbose:
                    self.console.print(f"  [green]✓[/green] {result.message}")
                continue

            symbol = "⚠" if result.level.value == "warning" else "✗"
            color = "yellow" if result.level.value == "warning" else "red"
            self.console.print(f"  [{color}]{symbol}[/{color}] {result.message}")
            if verbose and result.details:
                for key, value in result.details.items():
                    self.console.print(f"      {key}: {value}")

    def _print_overall_summary(self, results: dict[str, Any]) -> None:
        """Summarize validation results across all providers."""
        if not results:
            return

        total_errors = sum(r["errors"] for r in results.values())
        total_warnings = sum(r["warnings"] for r in results.values())
        all_passed = all(r["passed"] for r in results.values())

        self.console.print("[bold]Validation Summary:[/bold]")
        if all_passed:
            self.console.print("[green]✓ All validation checks passed[/green]")
            if total_warnings:
                self.console.print(
                    f"[yellow]  {total_warnings} warnings (review recommended)[/yellow]"
                )
        else:
            self.console.print(
                f"[red]✗ Validation failed: {total_errors} errors, {total_warnings} warnings[/red]"
            )
            self.console.print("[yellow]  Fix errors before deploying[/yellow]")


class PlanOrchestrator(HookExecutionMixin):
    """Handle plan execution for each provider."""

    def __init__(
        self,
        console: Console,
        state_manager: StateManager,
        event_manager: EventManager,
        runner_registry: RunnerRegistry,
        get_providers: Callable[[], dict[str, ProviderBase]],
        load_resources: Callable[
            [str], tuple[list[ResourceConfig], dict[str, list[ResourceConfig]]]
        ],
        iter_provider_batches: Callable[
            [dict[str, list[ResourceConfig]], list[str] | None, bool, str | None],
            list[ProviderResourceBatch],
        ],
        validate_resources: Callable[[list[ResourceConfig]], None],
        has_policies: Callable[[], bool],
        check_policies: Callable[[str, list[ResourceConfig], bool], None],
        secret_manager_factory: Callable[[str], SecretManager],
        get_current_user: Callable[[], str],
        fail_on_missing_secrets: bool,
        get_runner_priorities: Callable[[str], dict[str, int]],
        hook_manager: HookManager | None = None,
        load_environment: Callable[[str], EnvironmentConfig | None] | None = None,
        get_resource_package_map: Callable[[], dict[str, str]] | None = None,
    ) -> None:
        self.console = console
        self.state_manager = state_manager
        self.event_manager = event_manager
        self.runner_registry = runner_registry
        self._get_providers = get_providers
        self._load_resources = load_resources
        self._iter_provider_batches = iter_provider_batches
        self._validate_resources = validate_resources
        self._has_policies = has_policies
        self._check_policies = check_policies
        self._secret_manager_factory = secret_manager_factory
        self._get_current_user = get_current_user
        self._fail_on_missing_secrets = fail_on_missing_secrets
        self._get_runner_priorities = get_runner_priorities
        self._hook_manager = hook_manager
        self._load_environment = load_environment
        self._get_resource_package_map = get_resource_package_map or (lambda: {})

        # Dynamically create all registered runners
        self.runners: dict[str, BaseRunner] = {}
        for tool_name in self.runner_registry.list_runners():
            runner = self.runner_registry.create_runner(tool_name, console=self.console)
            if runner:
                self.runners[tool_name] = runner

    @staticmethod
    def _group_by_package(
        resources: list[ResourceConfig],
        package_map: dict[str, str],
    ) -> list[tuple[str | None, list[ResourceConfig]]]:
        """Split resources into (package_name, resources) groups.

        Resources belonging to a package are grouped under the package name.
        Loose resources (not in any package) are grouped under ``None``.
        Package groups are returned first, then the loose group (if any).

        Args:
            resources: Resources to split
            package_map: Mapping of resource name to package name

        Returns:
            List of (package_name_or_None, resources) tuples
        """
        groups: dict[str | None, list[ResourceConfig]] = {}
        for resource in resources:
            pkg = package_map.get(resource.name)
            groups.setdefault(pkg, []).append(resource)

        # Packages first (sorted for deterministic order), then loose
        result: list[tuple[str | None, list[ResourceConfig]]] = []
        for pkg_name in sorted(k for k in groups if k is not None):
            result.append((pkg_name, groups[pkg_name]))
        if None in groups:
            result.append((None, groups[None]))
        return result

    def _get_sorted_runners(
        self,
        priorities: dict[str, int],
        iac_tool: IaCTool = IaCTool.TERRAFORM,
    ) -> list[tuple[str, BaseRunner]]:
        """Get runners sorted by priority, filtering by configured IaC tool.

        Only the IaC runner matching *iac_tool* is included; the other
        IaC runner is skipped.  Non-IaC runners are always included.
        """

        def get_priority(item: tuple[str, BaseRunner]) -> int:
            name, runner = item
            return priorities.get(name, runner.priority)

        active_iac = iac_tool.value
        filtered = {
            name: runner
            for name, runner in self.runners.items()
            if name not in _IAC_TOOL_KEYS or name == active_iac
        }
        return sorted(filtered.items(), key=get_priority)

    def plan(
        self,
        env_name: str,
        dry_run: bool,
        resource_filter: list[str] | None,
        enforce_policies: bool,
    ) -> dict[str, Any]:
        """Execute the plan workflow for the requested environment."""
        plan_metadata: PlanDeploymentMetadata = {"resource_filter": resource_filter}
        deployment_id = self.state_manager.create_deployment(
            environment=env_name,
            command="plan",
            user=self._get_current_user(),
            dry_run=dry_run,
            metadata=plan_metadata,
        )
        self.event_manager.emit_event(
            EventType.BEFORE_PLAN,
            env_name,
            {"deployment_id": deployment_id, "dry_run": dry_run},
            target_resources=resource_filter,
        )

        results: dict[str, Any] = {}
        runner_priorities = self._get_runner_priorities(env_name)

        # Load environment config for hooks and event handlers
        env_config = self._load_environment(env_name) if self._load_environment else None
        self._load_event_config(env_config)

        try:
            self._print_header("Planning", env_name, resource_filter, style="bold cyan")
            all_resources, resources_by_provider = self._load_resources(env_name)

            if self._has_policies():
                self._check_policies(env_name, all_resources, enforce_policies)

            # Execute environment-level before_plan hooks
            self._execute_env_hooks(env_name, "before_plan", env_config)

            providers = self._get_providers()
            # Use forward order for plan (same as apply)
            for batch in self._iter_provider_batches(
                resources_by_provider, resource_filter, False, env_name
            ):
                provider_name = batch.name
                provider_resources = batch.resources
                provider = providers.get(provider_name)
                if not provider:
                    self.console.print(
                        f"[yellow]Warning: Provider '{provider_name}' not registered[/yellow]"
                    )
                    continue

                self._validate_resources(provider_resources)
                self._print_provider_header(
                    provider_name, provider_resources, batch, resource_filter
                )
                self._track_planned_resources(
                    deployment_id, env_name, provider_name, provider_resources
                )

                provider_results: dict[str, Any] = {"resources": len(provider_resources)}

                # Execute resource-level before_plan hooks
                for resource in provider_resources:
                    self._execute_resource_hooks(env_name, "before_plan", resource, provider_name)

                if dry_run:
                    self.console.print("  [dim]Would generate configurations and run plans[/dim]")
                    provider_results["dry_run"] = True
                else:
                    provider.set_environment(env_name)

                    # Always generate with ALL resources to avoid terraform
                    # seeing filtered-out resources as deleted. The resource
                    # filter is applied via terraform -target instead.
                    all_provider_resources = resources_by_provider.get(provider_name, [])
                    generate_resources = (
                        all_provider_resources if resource_filter else provider_resources
                    )

                    # Split resources by package for state isolation
                    package_map = self._get_resource_package_map()
                    package_groups = self._group_by_package(generate_resources, package_map)

                    iac_tool = env_config.iac_tool if env_config else IaCTool.TERRAFORM

                    for pkg_name, pkg_resources in package_groups:
                        # Set or clear package context on the provider
                        if pkg_name is not None:
                            provider.set_package_context(pkg_name)
                            self.console.print(
                                f"  [dim]Package: {pkg_name} ({len(pkg_resources)} resources)[/dim]"
                            )
                        else:
                            provider.clear_package_context()

                        provider.ensure_directories()
                        self._export_secrets(provider_name, env_name, provider)

                        for tool_name, runner in self._get_sorted_runners(
                            runner_priorities, iac_tool
                        ):
                            generate_method = getattr(provider, f"generate_{tool_name}", None)
                            if generate_method and callable(generate_method):
                                if not isinstance(runner, Plannable):
                                    self.console.print(
                                        f"  [dim]Skipping {tool_name}: does not support plan[/dim]"
                                    )
                                    continue

                                self.console.print(
                                    f"  [dim]Generating {tool_name} configuration...[/dim]"
                                )
                                generate_method(pkg_resources)
                                self.console.print(f"  [dim]Running {tool_name} plan...[/dim]")

                                starting_event: RunnerEventData = {
                                    "provider": provider_name,
                                    "runner": tool_name,
                                    "phase": "plan",
                                }
                                self.event_manager.emit_event(
                                    EventType.RUNNER_STARTING,
                                    env_name,
                                    starting_event,
                                    provider=provider_name,
                                    runner=tool_name,
                                    target_resources=resource_filter,
                                )

                                try:
                                    # Pass resource filter as target names
                                    runner_result = runner.plan(
                                        provider,
                                        target_resources=(
                                            resource_filter if resource_filter else None
                                        ),
                                    )
                                    # Use package-qualified key when multiple groups
                                    result_key = (
                                        f"{tool_name}_plan_{pkg_name}"
                                        if pkg_name
                                        else f"{tool_name}_plan"
                                    )
                                    provider_results[result_key] = runner_result

                                    completed_event: RunnerEventData = {
                                        "provider": provider_name,
                                        "runner": tool_name,
                                        "phase": "plan",
                                        "success": True,
                                    }
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
                                        "phase": "plan",
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
                            else:
                                self.console.print(
                                    f"  [dim]Skipping {tool_name} for {provider_name}: "
                                    f"no generate_{tool_name} method[/dim]"
                                )

                    # Restore provider-scoped terraform_dir after processing
                    provider.clear_package_context()

                # Execute resource-level after_plan hooks
                for resource in provider_resources:
                    self._execute_resource_hooks(env_name, "after_plan", resource, provider_name)

                results[provider_name] = provider_results

            # Execute environment-level after_plan hooks
            self._execute_env_hooks(env_name, "after_plan", env_config)

            self.state_manager.update_deployment_status(deployment_id, DeploymentStatus.COMPLETED)
            self.event_manager.emit_event(
                EventType.AFTER_PLAN,
                env_name,
                {"deployment_id": deployment_id, "results": results},
                target_resources=resource_filter,
            )
        except Exception as exc:
            self.state_manager.update_deployment_status(
                deployment_id, DeploymentStatus.FAILED, str(exc)
            )
            self.event_manager.emit_event(
                EventType.PLAN_FAILED,
                env_name,
                {"deployment_id": deployment_id, "error": str(exc)},
                target_resources=resource_filter,
            )
            self.console.print(traceback.format_exc(), style="dim red")  # Log full traceback
            raise

        return results

    def _print_header(
        self, label: str, env_name: str, resource_filter: list[str] | None, style: str
    ) -> None:
        if resource_filter:
            self.console.print(
                f"\n[{style}]{label} infrastructure for: {env_name} "
                f"(resources: {', '.join(resource_filter)})[/{style}]"
            )
        else:
            self.console.print(f"\n[{style}]{label} infrastructure for: {env_name}[/{style}]")

    def _print_provider_header(
        self,
        provider_name: str,
        provider_resources: list[ResourceConfig],
        batch: ProviderResourceBatch,
        resource_filter: list[str] | None,
    ) -> None:
        if resource_filter:
            self.console.print(
                f"\n[bold]{provider_name}[/bold]: {len(provider_resources)} of "
                f"{batch.original_count} resources (filtered)"
            )
        else:
            self.console.print(
                f"\n[bold]{provider_name}[/bold]: {len(provider_resources)} resources"
            )

    def _track_planned_resources(
        self,
        deployment_id: int,
        env_name: str,
        provider_name: str,
        resources: list[ResourceConfig],
    ) -> None:
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
                    "terraform_id": tracked_resource.terraform_id,
                },
            )

    def _export_secrets(self, provider_name: str, env_name: str, provider: ProviderBase) -> None:
        try:
            secret_manager = self._secret_manager_factory(env_name)
            secrets_file = f"{provider_name}.yaml"
            tf_vars = provider.terraform_dir / "secrets.auto.tfvars"
            secret_manager.export_for_terraform(secrets_file, tf_vars)
        except (FileNotFoundError, SecretNotFoundError) as exc:
            message = f"No secrets file for {provider_name}"
            if self._fail_on_missing_secrets:
                raise FileNotFoundError(message) from exc
            self.console.print(f"[yellow]{message}[/yellow]")
        except ValueError as exc:
            if self._fail_on_missing_secrets:
                raise
            self.console.print(f"[dim]Skipping secrets export: {exc}[/dim]")


class RollbackOrchestrator:
    """Handle rollbacks by orchestrating confirmation and apply execution."""

    def __init__(
        self,
        console: Console,
        state_manager: StateManager,
        apply_orchestrator: ApplyOrchestrator,
        get_current_user: Callable[[], str],
    ) -> None:
        self.console = console
        self.state_manager = state_manager
        self.apply_orchestrator = apply_orchestrator
        self._get_current_user = get_current_user

    def rollback(
        self,
        deployment_id: int,
        auto_approve: bool,
        confirm_callback: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        deployment = self.state_manager.get_deployment_by_id(deployment_id)
        if not deployment:
            raise ValueError(f"Deployment {deployment_id} not found")

        if not deployment.rollback_data:
            raise ValueError(f"Deployment {deployment_id} has no rollback data")

        rollback_data = deployment.rollback_data
        env_name = rollback_data["environment"]
        self._print_header(env_name, deployment_id, deployment, rollback_data)

        if not auto_approve:
            should_continue = False
            if confirm_callback:
                should_continue = confirm_callback()

            if not should_continue:
                self.console.print("[yellow]Rollback cancelled.[/yellow]")
                return {}

        rollback_metadata: RollbackDeploymentMetadata = {
            "rollback_from": deployment_id,
            "rollback": True,
        }
        rollback_deployment_id = self.state_manager.create_deployment(
            environment=env_name,
            command="apply",
            user=self._get_current_user(),
            dry_run=False,
            metadata=rollback_metadata,
        )

        try:
            self._print_note(deployment_id)
            results = self.apply_orchestrator.apply(
                env_name=env_name,
                resource_filter=None,
                auto_approve=True,
                parallel=False,
                max_workers=4,
            )
            self.state_manager.update_deployment_status(
                rollback_deployment_id, DeploymentStatus.COMPLETED
            )
            self.console.print(
                f"\n[bold green]✓ Rollback to deployment {deployment_id} completed![/bold green]"
            )
            return results
        except Exception as exc:
            self.state_manager.update_deployment_status(
                rollback_deployment_id, DeploymentStatus.FAILED, str(exc)
            )
            self.console.print(f"\n[bold red]✗ Rollback failed: {exc}[/bold red]")
            self.console.print(traceback.format_exc(), style="dim red")  # Log full traceback
            raise

    def _print_header(
        self,
        env_name: str,
        deployment_id: int,
        deployment: Any,
        rollback_data: dict[str, Any],
    ) -> None:
        self.console.print(
            f"\n[bold yellow]Rolling back {env_name} to deployment {deployment_id}[/bold yellow]"
        )
        if deployment.started_at:
            self.console.print(
                f"[dim]Deployment from: {deployment.started_at.strftime('%Y-%m-%d %H:%M:%S')}[/dim]"
            )
        self.console.print(f"[dim]Resources: {len(rollback_data.get('resources', []))}[/dim]\n")

    def _print_note(self, deployment_id: int) -> None:
        self.console.print(
            f"\n[bold yellow]⚠ Note: Rollback requires the configuration "
            f"repository to be at the state from deployment {deployment_id}[/bold yellow]"
        )
        self.console.print(
            "[dim]Consider using git to checkout the appropriate commit if needed.[/dim]\n"
        )


class ApplyOrchestrator(HookExecutionMixin):
    """Coordinate apply deployments after planning."""

    def __init__(
        self,
        console: Console,
        state_manager: StateManager,
        event_manager: EventManager,
        load_resources: Callable[
            [str], tuple[list[ResourceConfig], dict[str, list[ResourceConfig]]]
        ],
        apply_serial: Callable[
            [str, int, dict[str, list[ResourceConfig]], list[str] | None, bool], dict[str, Any]
        ],
        apply_parallel: Callable[
            [str, int, dict[str, list[ResourceConfig]], list[str] | None, bool, int],
            dict[str, Any],
        ],
        get_current_user: Callable[[], str],
        hook_manager: HookManager | None = None,
        load_environment: Callable[[str], EnvironmentConfig | None] | None = None,
    ) -> None:
        self.console = console
        self.state_manager = state_manager
        self.event_manager = event_manager
        self._load_resources = load_resources
        self._apply_serial = apply_serial
        self._apply_parallel = apply_parallel
        self._get_current_user = get_current_user
        self._hook_manager = hook_manager
        self._load_environment = load_environment

    def apply(
        self,
        env_name: str,
        resource_filter: list[str] | None,
        auto_approve: bool,
        parallel: bool,
        max_workers: int,
    ) -> dict[str, Any]:
        """Apply infrastructure across providers."""
        apply_metadata: ApplyDeploymentMetadata = {
            "resource_filter": resource_filter,
            "auto_approve": auto_approve,
        }
        deployment_id = self.state_manager.create_deployment(
            environment=env_name,
            command="apply",
            user=self._get_current_user(),
            dry_run=False,
            metadata=apply_metadata,
        )
        self.event_manager.emit_event(
            EventType.BEFORE_APPLY,
            env_name,
            {"deployment_id": deployment_id, "auto_approve": auto_approve},
            target_resources=resource_filter,
        )

        results: dict[str, Any] = {}

        # Load environment config for hooks and event handlers
        env_config = self._load_environment(env_name) if self._load_environment else None
        self._load_event_config(env_config)

        try:
            self._print_header("Applying", env_name, resource_filter, "bold green")
            all_resources, resources_by_provider = self._load_resources(env_name)
            self._store_rollback_snapshot(deployment_id, env_name, all_resources)

            # Convert to set for O(1) lookups
            filter_set = set(resource_filter) if resource_filter else None

            # Execute environment-level before_apply hooks
            self._execute_env_hooks(env_name, "before_apply", env_config)

            # Execute resource-level before_apply hooks
            for resources in resources_by_provider.values():
                for resource in resources:
                    if not filter_set or resource.name in filter_set:
                        self._execute_resource_hooks(
                            env_name, "before_apply", resource, resource.provider
                        )

            if parallel and len(resources_by_provider) > 1:
                results = self._apply_parallel(
                    env_name,
                    deployment_id,
                    resources_by_provider,
                    resource_filter,
                    auto_approve,
                    max_workers,
                )
            else:
                results = self._apply_serial(
                    env_name,
                    deployment_id,
                    resources_by_provider,
                    resource_filter,
                    auto_approve,
                )

            # Execute resource-level after_apply hooks
            for resources in resources_by_provider.values():
                for resource in resources:
                    if not filter_set or resource.name in filter_set:
                        self._execute_resource_hooks(
                            env_name, "after_apply", resource, resource.provider
                        )

            # Execute environment-level after_apply hooks
            self._execute_env_hooks(env_name, "after_apply", env_config)

            self.state_manager.update_deployment_status(deployment_id, DeploymentStatus.COMPLETED)
            self.event_manager.emit_event(
                EventType.AFTER_APPLY,
                env_name,
                {"deployment_id": deployment_id, "results": results},
                target_resources=resource_filter,
            )
        except Exception as exc:
            self.state_manager.update_deployment_status(
                deployment_id, DeploymentStatus.FAILED, str(exc)
            )
            self.event_manager.emit_event(
                EventType.APPLY_FAILED,
                env_name,
                {"deployment_id": deployment_id, "error": str(exc)},
                target_resources=resource_filter,
            )
            self.console.print(traceback.format_exc(), style="dim red")  # Log full traceback
            raise

        return results

    def _store_rollback_snapshot(
        self,
        deployment_id: int,
        env_name: str,
        all_resources: list[ResourceConfig],
    ) -> None:
        snapshot: RollbackData = {
            "environment": env_name,
            "timestamp": datetime.now(UTC).isoformat(),
            "resources": [
                {"provider": r.provider, "type": r.type, "name": r.name, "config": r.config}
                for r in all_resources
            ],
        }
        self.state_manager.update_deployment_rollback_data(
            deployment_id=deployment_id, rollback_data=snapshot
        )

    def _print_header(
        self, label: str, env_name: str, resource_filter: list[str] | None, style: str
    ) -> None:
        if resource_filter:
            self.console.print(
                f"\n[{style}]{label} infrastructure for: {env_name} "
                f"(resources: {', '.join(resource_filter)})[/{style}]"
            )
        else:
            self.console.print(f"\n[{style}]{label} infrastructure for: {env_name}[/{style}]")


class DestroyOrchestrator(HookExecutionMixin):
    """Handle destroy operations with consistent tracking."""

    def __init__(
        self,
        console: Console,
        state_manager: StateManager,
        event_manager: EventManager,
        runner_registry: RunnerRegistry,
        get_providers: Callable[[], dict[str, ProviderBase]],
        load_resources: Callable[
            [str], tuple[list[ResourceConfig], dict[str, list[ResourceConfig]]]
        ],
        iter_provider_batches: Callable[
            [dict[str, list[ResourceConfig]], list[str] | None, bool, str | None],
            list[ProviderResourceBatch],
        ],
        get_current_user: Callable[[], str],
        hook_manager: HookManager | None = None,
        load_environment: Callable[[str], EnvironmentConfig | None] | None = None,
        get_resource_package_map: Callable[[], dict[str, str]] | None = None,
    ) -> None:
        self.console = console
        self.state_manager = state_manager
        self.event_manager = event_manager
        self.runner_registry = runner_registry
        self._get_providers = get_providers
        self._load_resources = load_resources
        self._iter_provider_batches = iter_provider_batches
        self._get_current_user = get_current_user
        self._hook_manager = hook_manager
        self._load_environment = load_environment
        self._get_resource_package_map = get_resource_package_map or (lambda: {})

        # Dynamically create all registered runners
        self.runners: dict[str, BaseRunner] = {}
        for tool_name in self.runner_registry.list_runners():
            runner = self.runner_registry.create_runner(tool_name, console=self.console)
            if runner:
                self.runners[tool_name] = runner

    def destroy(
        self,
        env_name: str,
        resource_filter: list[str] | None,
        auto_approve: bool,
        confirm_callback: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        """Destroy all requested resources."""
        destroy_metadata: DestroyDeploymentMetadata = {
            "resource_filter": resource_filter,
            "auto_approve": auto_approve,
        }
        deployment_id = self.state_manager.create_deployment(
            environment=env_name,
            command="destroy",
            user=self._get_current_user(),
            dry_run=False,
            metadata=destroy_metadata,
        )
        self.event_manager.emit_event(
            EventType.BEFORE_DESTROY,
            env_name,
            {"deployment_id": deployment_id, "auto_approve": auto_approve},
            target_resources=resource_filter,
        )

        results: dict[str, Any] = {}

        # Load environment config for hooks and event handlers
        env_config = self._load_environment(env_name) if self._load_environment else None
        self._load_event_config(env_config)

        try:
            self._print_header("Destroying", env_name, resource_filter, "bold red")

            if not auto_approve:
                if confirm_callback:
                    should_continue = confirm_callback()
                else:
                    # If auto_approve is False and no callback, then CLI should have handled it.
                    # This indicates an improper call from the CLI.
                    self.console.print(
                        "[red]Error: Confirmation callback needed for destroy.[/red]"
                    )
                    self.state_manager.update_deployment_status(
                        deployment_id,
                        DeploymentStatus.FAILED,
                        "Confirmation callback required but not provided",
                    )
                    return {"success": False, "error": "Confirmation not provided"}

                if not should_continue:
                    self.console.print("[yellow]Aborted[/yellow]")
                    self.state_manager.update_deployment_status(
                        deployment_id, DeploymentStatus.FAILED, "User aborted"
                    )
                    return {"success": False, "message": "User aborted"}

            _, resources_by_provider = self._load_resources(env_name)
            providers = self._get_providers()

            # Execute environment-level before_destroy hooks
            self._execute_env_hooks(env_name, "before_destroy", env_config)

            # Use REVERSE order for destroy - application providers (kubernetes) before
            # infrastructure providers (proxmox, opnsense)
            for batch in self._iter_provider_batches(
                resources_by_provider, resource_filter, True, env_name
            ):
                provider_name = batch.name
                resources = batch.resources
                provider = providers.get(provider_name)
                if not provider:
                    continue

                self.console.print(f"\n[bold]Destroying {provider_name}...[/bold]")
                provider.set_environment(env_name)

                # Execute resource-level before_destroy hooks
                for resource in resources:
                    self._execute_resource_hooks(
                        env_name, "before_destroy", resource, provider_name
                    )

                resource_ids = self._track_destroying_resources(
                    deployment_id, env_name, provider_name, resources
                )

                provider_results: dict[str, Any] = {}
                active_iac = env_config.iac_tool.value if env_config else IaCTool.TERRAFORM.value

                # Group resources by package for state isolation
                package_map = self._get_resource_package_map()
                package_groups = PlanOrchestrator._group_by_package(resources, package_map)

                for pkg_name, pkg_resources in package_groups:
                    if pkg_name is not None:
                        provider.set_package_context(pkg_name)
                        self.console.print(
                            f"  [dim]Package: {pkg_name} ({len(pkg_resources)} resources)[/dim]"
                        )
                    else:
                        provider.clear_package_context()

                    # Build resource filter for this package sub-group
                    pkg_resource_names = [r.name for r in pkg_resources]

                    for tool_name, runner in self.runners.items():
                        # Skip IaC runners that don't match the configured tool
                        if tool_name in _IAC_TOOL_KEYS and tool_name != active_iac:
                            continue
                        if not isinstance(runner, Destroyable):
                            self.console.print(
                                f"  [dim]Skipping {tool_name}: does not support destroy[/dim]"
                            )
                            continue

                        self.console.print(f"  [dim]Running {tool_name} destroy...[/dim]")

                        starting_event: RunnerEventData = {
                            "provider": provider_name,
                            "runner": tool_name,
                            "phase": "destroy",
                        }
                        self.event_manager.emit_event(
                            EventType.RUNNER_STARTING,
                            env_name,
                            starting_event,
                            provider=provider_name,
                            runner=tool_name,
                            target_resources=resource_filter,
                        )

                        try:
                            # Use package-scoped resource names or original
                            # filter as target names for terraform
                            destroy_targets = (
                                (resource_filter if resource_filter else pkg_resource_names)
                                if pkg_name is not None
                                else (resource_filter if resource_filter else None)
                            )
                            runner_result = runner.destroy(
                                provider,
                                auto_approve=auto_approve,
                                target_resources=destroy_targets,
                            )
                            result_key = f"{tool_name}_{pkg_name}" if pkg_name else tool_name
                            provider_results[result_key] = runner_result

                            completed_event: RunnerEventData = {
                                "provider": provider_name,
                                "runner": tool_name,
                                "phase": "destroy",
                                "success": True,
                            }
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
                                "phase": "destroy",
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

                # Restore provider context after processing all packages
                provider.clear_package_context()

                self._finalize_destroyed_resources(env_name, provider_name, resource_ids)

                # Execute resource-level after_destroy hooks
                for resource in resources:
                    self._execute_resource_hooks(env_name, "after_destroy", resource, provider_name)

                results[provider_name] = provider_results

            # Execute environment-level after_destroy hooks
            self._execute_env_hooks(env_name, "after_destroy", env_config)

            self.state_manager.update_deployment_status(deployment_id, DeploymentStatus.COMPLETED)
            self.event_manager.emit_event(
                EventType.AFTER_DESTROY,
                env_name,
                {"deployment_id": deployment_id, "results": results},
                target_resources=resource_filter,
            )
        except Exception as exc:
            self.state_manager.update_deployment_status(
                deployment_id, DeploymentStatus.FAILED, str(exc)
            )
            self.event_manager.emit_event(
                EventType.DESTROY_FAILED,
                env_name,
                {"deployment_id": deployment_id, "error": str(exc)},
                target_resources=resource_filter,
            )
            self.console.print(traceback.format_exc(), style="dim red")  # Log full traceback
            raise

        return results

    def _track_destroying_resources(
        self,
        deployment_id: int,
        env_name: str,
        provider_name: str,
        resources: list[ResourceConfig],
    ) -> dict[str, int]:
        resource_ids: dict[str, int] = {}
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
                    "terraform_id": tracked_resource.terraform_id,
                },
            )
        return resource_ids

    def _finalize_destroyed_resources(
        self,
        env_name: str,
        provider_name: str,
        resource_ids: dict[str, int],
    ) -> None:
        for resource_name, resource_id in resource_ids.items():
            self.state_manager.update_resource_state(
                resource_id=resource_id,
                state=ResourceState.DELETED,
            )
            self.event_manager.emit_event(
                EventType.RESOURCE_DELETED,
                env_name,
                {"resource_id": resource_id, "provider": provider_name, "name": resource_name},
            )

    def _print_header(
        self, label: str, env_name: str, resource_filter: list[str] | None, style: str
    ) -> None:
        if resource_filter:
            self.console.print(
                f"\n[{style}]{label} infrastructure for: {env_name} "
                f"(resources: {', '.join(resource_filter)})[/{style}]"
            )
        else:
            self.console.print(f"\n[{style}]{label} infrastructure for: {env_name}[/{style}]")
