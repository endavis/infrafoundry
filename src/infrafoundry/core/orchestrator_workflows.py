"""Supporting workflows for orchestrator operations."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from rich.console import Console

from infrafoundry.core.config import ConfigManager
from infrafoundry.core.provider import ProviderBase
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
        ],  # noqa: E501
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
