"""Supporting workflows for orchestrator operations."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from rich.console import Console

from infrafoundry.core.config import ConfigManager
from infrafoundry.core.events import EventType
from infrafoundry.core.provider import ProviderBase
from infrafoundry.core.runners import TerraformRunner
from infrafoundry.core.secrets import SecretManager
from infrafoundry.core.state import DeploymentStatus, ResourceState, StateManager
from infrafoundry.core.validation import ValidationReport


@dataclass(slots=True)
class ProviderResourceBatch:
    """Represents the resources for a single provider after optional filtering."""

    name: str
    resources: list[Any]
    original_count: int


class ValidationWorkflow:
    """Handle per-provider validation, keeping Orchestrator lean."""

    def __init__(
        self,
        config_manager: ConfigManager,
        console: Console,
        get_providers: Callable[[], dict[str, ProviderBase]],
        load_resources: Callable[[str], tuple[list[Any], dict[str, list[Any]]]],
        iter_provider_batches: Callable[
            [dict[str, list[Any]], list[str] | None], list[ProviderResourceBatch]
        ],
    ) -> None:
        self.config_manager = config_manager
        self.console = console
        self._get_providers = get_providers
        self._load_resources = load_resources
        self._iter_provider_batches = iter_provider_batches

    def run(
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

        env_data = env_config.model_dump()
        all_resources, resources_by_provider = self._load_resources(env_name)
        filtered_resources = all_resources
        if resource_filter:
            filtered_resources = [r for r in all_resources if r.name in resource_filter]
            self.console.print(
                f"[yellow]Validating {len(filtered_resources)} resources: "
                f"{', '.join(resource_filter)}[/yellow]\n"
            )

        results: dict[str, Any] = {}

        providers = self._get_providers()
        for batch in self._iter_provider_batches(resources_by_provider, resource_filter):
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
        env_data: dict[str, Any],
        resources: list[Any],
        report: ValidationReport,
    ) -> None:
        """Invoke provider validation hooks with error protection."""
        try:
            provider.validate_connectivity(env_data, report)
        except Exception as exc:  # noqa: BLE001 - surfacing provider errors
            self.console.print(f"[red]✗ Connectivity validation failed: {exc}[/red]")

        try:
            provider.validate_references(resources, env_data, report)
        except Exception as exc:  # noqa: BLE001 - surfacing provider errors
            self.console.print(f"[red]✗ Reference validation failed: {exc}[/red]")

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


class PlanWorkflow:
    """Handle plan execution for each provider."""

    def __init__(
        self,
        console: Console,
        state_manager: StateManager,
        event_manager,
        terraform_runner: TerraformRunner,
        get_providers: Callable[[], dict[str, ProviderBase]],
        load_resources: Callable[[str], tuple[list[Any], dict[str, list[Any]]]],
        iter_provider_batches: Callable[
            [dict[str, list[Any]], list[str] | None], list[ProviderResourceBatch]
        ],
        validate_resources: Callable[[list[Any]], None],
        has_policies: Callable[[], bool],
        check_policies: Callable[[str, list[Any], bool], None],
        secret_manager_factory: Callable[[str], SecretManager],
        get_current_user: Callable[[], str],
        fail_on_missing_secrets: bool,
    ) -> None:
        self.console = console
        self.state_manager = state_manager
        self.event_manager = event_manager
        self.terraform_runner = terraform_runner
        self._get_providers = get_providers
        self._load_resources = load_resources
        self._iter_provider_batches = iter_provider_batches
        self._validate_resources = validate_resources
        self._has_policies = has_policies
        self._check_policies = check_policies
        self._secret_manager_factory = secret_manager_factory
        self._get_current_user = get_current_user
        self._fail_on_missing_secrets = fail_on_missing_secrets

    def run(
        self,
        env_name: str,
        dry_run: bool,
        resource_filter: list[str] | None,
        enforce_policies: bool,
    ) -> dict[str, Any]:
        """Execute the plan workflow for the requested environment."""
        deployment_id = self.state_manager.create_deployment(
            environment=env_name,
            command="plan",
            user=self._get_current_user(),
            dry_run=dry_run,
            metadata={"resource_filter": resource_filter},
        )
        self.event_manager.emit_event(
            EventType.BEFORE_PLAN,
            env_name,
            {"deployment_id": deployment_id, "dry_run": dry_run},
        )

        results: dict[str, Any] = {}

        try:
            self._print_header("Planning", env_name, resource_filter, style="bold cyan")
            all_resources, resources_by_provider = self._load_resources(env_name)

            if self._has_policies():
                self._check_policies(env_name, all_resources, enforce=enforce_policies)

            providers = self._get_providers()
            for batch in self._iter_provider_batches(resources_by_provider, resource_filter):
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

                if dry_run:
                    self.console.print("  [dim]Would generate Terraform and Ansible files[/dim]")
                    results[provider_name] = {
                        "resources": len(provider_resources),
                        "dry_run": True,
                    }
                    continue

                provider.set_environment(env_name)
                provider.ensure_directories()
                provider.generate_terraform(provider_resources)
                provider.generate_ansible(provider_resources)
                self._export_secrets(provider_name, env_name, provider)

                self.console.print("  [dim]Running terraform plan...[/dim]")
                tf_result = self.terraform_runner.run(provider, "plan", auto_approve=False)
                results[provider_name] = {
                    "resources": len(provider_resources),
                    "terraform_plan": tf_result,
                }

            self.state_manager.update_deployment_status(deployment_id, DeploymentStatus.COMPLETED)
            self.event_manager.emit_event(
                EventType.AFTER_PLAN,
                env_name,
                {"deployment_id": deployment_id, "results": results},
            )
        except Exception as exc:
            self.state_manager.update_deployment_status(
                deployment_id, DeploymentStatus.FAILED, str(exc)
            )
            self.event_manager.emit_event(
                EventType.PLAN_FAILED,
                env_name,
                {"deployment_id": deployment_id, "error": str(exc)},
            )
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
        provider_resources: list[Any],
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
        resources: list[Any],
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
                },
            )

    def _export_secrets(self, provider_name: str, env_name: str, provider: ProviderBase) -> None:
        try:
            secret_manager = self._secret_manager_factory(env_name)
            secrets_file = f"{provider_name}.yaml"
            tf_vars = provider.terraform_dir / "secrets.auto.tfvars"
            secret_manager.export_for_terraform(secrets_file, tf_vars)
        except FileNotFoundError as exc:
            message = f"No secrets file for {provider_name}"
            if self._fail_on_missing_secrets:
                raise FileNotFoundError(message) from exc
            self.console.print(f"[yellow]{message}[/yellow]")
        except ValueError as exc:
            if self._fail_on_missing_secrets:
                raise
            self.console.print(f"[dim]Skipping secrets export: {exc}[/dim]")


class RollbackWorkflow:
    """Handle rollbacks by orchestrating confirmation and apply execution."""

    def __init__(
        self,
        console: Console,
        state_manager: StateManager,
        apply_workflow: ApplyWorkflow,
        get_current_user: Callable[[], str],
    ) -> None:
        self.console = console
        self.state_manager = state_manager
        self.apply_workflow = apply_workflow
        self._get_current_user = get_current_user

    def run(self, deployment_id: int, auto_approve: bool) -> dict[str, Any]:
        deployment = self.state_manager.get_deployment_by_id(deployment_id)
        if not deployment:
            raise ValueError(f"Deployment {deployment_id} not found")

        if not deployment.rollback_data:
            raise ValueError(f"Deployment {deployment_id} has no rollback data")

        rollback_data = deployment.rollback_data
        env_name = rollback_data["environment"]
        self._print_header(env_name, deployment_id, deployment, rollback_data)

        if not auto_approve and not self._confirm_rollback():
            self.console.print("[yellow]Rollback cancelled.[/yellow]")
            return {}

        rollback_deployment_id = self.state_manager.create_deployment(
            environment=env_name,
            command="apply",
            user=self._get_current_user(),
            dry_run=False,
            metadata={"rollback_from": deployment_id, "rollback": True},
        )

        try:
            self._print_note(deployment_id)
            results = self.apply_workflow.run(
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

    def _confirm_rollback(self) -> bool:
        response = input("Are you sure you want to rollback? (yes/no): ")
        return response.lower() == "yes"

    def _print_note(self, deployment_id: int) -> None:
        self.console.print(
            f"\n[bold yellow]⚠ Note: Rollback requires the configuration "
            f"repository to be at the state from deployment {deployment_id}[/bold yellow]"
        )
        self.console.print(
            "[dim]Consider using git to checkout the appropriate commit if needed.[/dim]\n"
        )


class ApplyWorkflow:
    """Coordinate apply deployments after planning."""

    def __init__(
        self,
        console: Console,
        state_manager: StateManager,
        event_manager,
        load_resources: Callable[[str], tuple[list[Any], dict[str, list[Any]]]],
        apply_serial: Callable[
            [str, int, dict[str, list[Any]], list[str] | None, bool], dict[str, Any]
        ],
        apply_parallel: Callable[
            [str, int, dict[str, list[Any]], list[str] | None, bool, int], dict[str, Any]
        ],
        get_current_user: Callable[[], str],
    ) -> None:
        self.console = console
        self.state_manager = state_manager
        self.event_manager = event_manager
        self._load_resources = load_resources
        self._apply_serial = apply_serial
        self._apply_parallel = apply_parallel
        self._get_current_user = get_current_user

    def run(
        self,
        env_name: str,
        resource_filter: list[str] | None,
        auto_approve: bool,
        parallel: bool,
        max_workers: int,
    ) -> dict[str, Any]:
        """Apply infrastructure across providers."""
        deployment_id = self.state_manager.create_deployment(
            environment=env_name,
            command="apply",
            user=self._get_current_user(),
            dry_run=False,
            metadata={"resource_filter": resource_filter, "auto_approve": auto_approve},
        )
        self.event_manager.emit_event(
            EventType.BEFORE_APPLY,
            env_name,
            {"deployment_id": deployment_id, "auto_approve": auto_approve},
        )

        results: dict[str, Any] = {}

        try:
            self._print_header("Applying", env_name, resource_filter, "bold green")
            all_resources, resources_by_provider = self._load_resources(env_name)
            self._store_rollback_snapshot(deployment_id, env_name, all_resources)

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

            self.state_manager.update_deployment_status(deployment_id, DeploymentStatus.COMPLETED)
            self.event_manager.emit_event(
                EventType.AFTER_APPLY,
                env_name,
                {"deployment_id": deployment_id, "results": results},
            )
        except Exception as exc:
            self.state_manager.update_deployment_status(
                deployment_id, DeploymentStatus.FAILED, str(exc)
            )
            self.event_manager.emit_event(
                EventType.APPLY_FAILED,
                env_name,
                {"deployment_id": deployment_id, "error": str(exc)},
            )
            raise

        return results

    def _store_rollback_snapshot(
        self,
        deployment_id: int,
        env_name: str,
        all_resources: list[Any],
    ) -> None:
        snapshot = {
            "environment": env_name,
            "timestamp": datetime.utcnow().isoformat(),
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


class DestroyWorkflow:
    """Handle destroy operations with consistent tracking."""

    def __init__(
        self,
        console: Console,
        state_manager: StateManager,
        event_manager,
        terraform_runner: TerraformRunner,
        get_providers: Callable[[], dict[str, ProviderBase]],
        load_resources: Callable[[str], tuple[list[Any], dict[str, list[Any]]]],
        iter_provider_batches: Callable[
            [dict[str, list[Any]], list[str] | None], list[ProviderResourceBatch]
        ],
        get_current_user: Callable[[], str],
    ) -> None:
        self.console = console
        self.state_manager = state_manager
        self.event_manager = event_manager
        self.terraform_runner = terraform_runner
        self._get_providers = get_providers
        self._load_resources = load_resources
        self._iter_provider_batches = iter_provider_batches
        self._get_current_user = get_current_user

    def run(
        self,
        env_name: str,
        resource_filter: list[str] | None,
        auto_approve: bool,
    ) -> dict[str, Any]:
        """Destroy all requested resources."""
        deployment_id = self.state_manager.create_deployment(
            environment=env_name,
            command="destroy",
            user=self._get_current_user(),
            dry_run=False,
            metadata={"resource_filter": resource_filter, "auto_approve": auto_approve},
        )
        self.event_manager.emit_event(
            EventType.BEFORE_DESTROY,
            env_name,
            {"deployment_id": deployment_id, "auto_approve": auto_approve},
        )

        results: dict[str, Any] = {}

        try:
            self._print_header("Destroying", env_name, resource_filter, "bold red")
            if not auto_approve and not self._confirm_destroy():
                self.console.print("[yellow]Aborted[/yellow]")
                self.state_manager.update_deployment_status(
                    deployment_id, DeploymentStatus.FAILED, "User aborted"
                )
                return {}

            _, resources_by_provider = self._load_resources(env_name)
            providers = self._get_providers()

            for batch in self._iter_provider_batches(resources_by_provider, resource_filter):
                provider_name = batch.name
                resources = batch.resources
                provider = providers.get(provider_name)
                if not provider:
                    continue

                self.console.print(f"\n[bold]Destroying {provider_name}...[/bold]")
                provider.set_environment(env_name)
                resource_ids = self._track_destroying_resources(
                    deployment_id, env_name, provider_name, resources
                )

                tf_result = self.terraform_runner.run(provider, "destroy", auto_approve)
                self._finalize_destroyed_resources(env_name, provider_name, resource_ids)
                results[provider_name] = {"terraform": tf_result}

            self.state_manager.update_deployment_status(deployment_id, DeploymentStatus.COMPLETED)
            self.event_manager.emit_event(
                EventType.AFTER_DESTROY,
                env_name,
                {"deployment_id": deployment_id, "results": results},
            )
        except Exception as exc:
            self.state_manager.update_deployment_status(
                deployment_id, DeploymentStatus.FAILED, str(exc)
            )
            self.event_manager.emit_event(
                EventType.DESTROY_FAILED,
                env_name,
                {"deployment_id": deployment_id, "error": str(exc)},
            )
            raise

        return results

    def _confirm_destroy(self) -> bool:
        response = input("Are you sure you want to destroy? (yes/no): ")
        return response.lower() == "yes"

    def _track_destroying_resources(
        self,
        deployment_id: int,
        env_name: str,
        provider_name: str,
        resources: list[Any],
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
                {"provider": provider_name, "name": resource_name},
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
