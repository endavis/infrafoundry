"""Infrastructure test command."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any

import click
from rich.table import Table

from infrafoundry.cli.decorators import with_orchestrator
from infrafoundry.cli.utils import console
from infrafoundry.core.testing import (
    InfraTestRunner,
    InfraTestSuite,
    assert_no_duplicate_names,
    assert_resource_count,
)

if TYPE_CHECKING:
    from infrafoundry.core.orchestrator import Orchestrator


@click.command("test")
@click.option("--env", "-e", required=True, help="Environment to test")
@click.option(
    "--test",
    "-t",
    "test_filter",
    multiple=True,
    help="Run only specific tests (can be specified multiple times)",
)
@click.option(
    "--output",
    "-o",
    type=click.Choice(["table", "json"]),
    default="table",
    help="Output format (default: table)",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Show all test results including passed tests",
)
@with_orchestrator("Infrastructure test failed", require_env=True, load_credentials=False)
def test(
    _ctx: click.Context,
    orchestrator: Orchestrator,
    env: str,
    test_filter: tuple[str, ...],
    output: str,
    verbose: bool,
) -> None:
    """Run infrastructure tests against configurations.

    Validates infrastructure configurations using built-in and custom tests.
    Tests check for common issues like duplicate names, missing references,
    and configuration problems.

    Example:
        infra test --env prod
        infra test --env dev --verbose
        infra test --env staging --test no_duplicate_names
    """
    import json as json_module

    console.header(f"Infrastructure Tests: {env}")

    # Load environment config first
    env_config = orchestrator.config_manager.load_environment(env)
    env_data = env_config.model_dump()

    # Load resources
    try:
        all_resources, _resources_by_provider = orchestrator._load_resources(env)
    except Exception as exc:
        console.error(f"Failed to load resources: {exc}")
        sys.exit(1)

    if not all_resources:
        console.warning("No resources found for environment")
        sys.exit(0)

    console.status(f"Found {len(all_resources)} resources")

    # Create test runner with built-in tests
    runner = InfraTestRunner()

    # Add built-in test suite
    builtin_suite = InfraTestSuite(
        name="builtin",
        description="Built-in infrastructure validation tests",
    )

    # Add standard tests
    builtin_suite.add_test(assert_no_duplicate_names())
    builtin_suite.add_test(assert_resource_count(min_count=1))

    # Add provider-specific duplicate checks
    providers = {r.provider for r in all_resources}
    for provider in providers:
        builtin_suite.add_test(assert_no_duplicate_names(provider=provider))

    runner.add_suite(builtin_suite)

    # Run tests
    console.status("Running tests...")
    filter_list = list(test_filter) if test_filter else None
    results = runner.run(all_resources, env_data, test_filter=filter_list)

    # Output results
    if output == "json":
        console.print(json_module.dumps(results, indent=2))
    else:
        _display_table_results(results, verbose)

    # Exit with appropriate code
    if not results["passed"]:
        sys.exit(1)


def _display_table_results(results: dict[str, Any], verbose: bool) -> None:
    """Display test results as a formatted table."""
    summary = results["summary"]

    # Summary
    console.print()
    console.header("Test Summary")
    console.info(f"  Total tests: {summary['total']}")
    console.success(f"  Passed: {summary['passed']}")
    if summary["failed"] > 0:
        console.error(f"  Failed: {summary['failed']}")
    else:
        console.info(f"  Failed: {summary['failed']}")
    if summary["skipped"] > 0:
        console.info(f"  Skipped: {summary['skipped']}")
    if summary["errors"] > 0:
        console.error(f"  Errors: {summary['errors']}")
    console.status(f"  Duration: {results['duration_seconds']:.2f}s")

    # Filter results for display
    test_results = results["results"]
    if not verbose:
        test_results = [r for r in test_results if r["status"] != "passed"]

    if not test_results:
        if results["passed"]:
            console.print()
            console.success("All tests passed!")
        return

    # Results table
    console.print()
    header = "Test Results" if verbose else "Failed Tests"
    console.header(f"{header} ({len(test_results)} shown)")

    table = Table(show_header=True, header_style="bold")
    table.add_column("Status", style="bold", width=8)
    table.add_column("Test Name", style="cyan", width=35)
    table.add_column("Message", width=50)

    status_styles = {
        "passed": "green",
        "failed": "red",
        "skipped": "yellow",
        "error": "bold red",
    }

    status_symbols = {
        "passed": "✓",
        "failed": "✗",
        "skipped": "○",
        "error": "!",
    }

    for result in test_results:
        status = result["status"]
        style = status_styles.get(status, "")
        symbol = status_symbols.get(status, "?")

        table.add_row(
            f"[{style}]{symbol} {status.upper()}[/{style}]",
            result["test_name"],
            _truncate(result["message"], 50),
        )

    console.print(table)

    # Show details for failed tests
    failed_results = [r for r in results["results"] if r["status"] in ("failed", "error")]
    if failed_results:
        console.print()
        console.header("Failure Details")
        for result in failed_results:
            console.print(f"\n[bold]{result['test_name']}[/bold]")
            console.print(f"  {result['message']}")
            if result.get("details"):
                for key, value in result["details"].items():
                    if isinstance(value, list) and len(value) > 5:
                        console.print(f"  {key}: [{len(value)} items]")
                    else:
                        console.print(f"  {key}: {value}")

    # Overall result
    console.print()
    if results["passed"]:
        console.success("All tests passed!")
    else:
        console.error(f"Tests failed: {summary['failed']} failures, {summary['errors']} errors")


def _truncate(text: str, max_length: int) -> str:
    """Truncate text to max length with ellipsis."""
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."
