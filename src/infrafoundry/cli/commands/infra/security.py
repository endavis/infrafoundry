"""Security scanning commands."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import click
from rich.table import Table

from infrafoundry.cli.decorators import with_orchestrator
from infrafoundry.cli.utils import console
from infrafoundry.core.security import ScanResult, ScanSeverity, SecurityScanner

if TYPE_CHECKING:
    from infrafoundry.core.orchestrator import Orchestrator


@click.command("security")
@click.option("--env", "-e", required=True, help="Environment to scan")
@click.option(
    "--severity",
    "-s",
    type=click.Choice(["critical", "high", "medium", "low", "info"], case_sensitive=False),
    default="high",
    help="Minimum severity to fail on (default: high)",
)
@click.option(
    "--skip-check",
    multiple=True,
    help="Check IDs to skip (can be specified multiple times)",
)
@click.option(
    "--output",
    "-o",
    type=click.Choice(["table", "json"]),
    default="table",
    help="Output format (default: table)",
)
@click.option(
    "--timeout",
    type=int,
    default=300,
    help="Scan timeout in seconds (default: 300)",
)
@with_orchestrator("Security scan failed", require_env=True, load_credentials=False)
def security(
    _ctx: click.Context,
    orchestrator: Orchestrator,
    env: str,
    severity: str,
    skip_check: tuple[str, ...],
    output: str,
    timeout: int,
) -> None:
    """Scan infrastructure configurations for security issues.

    Uses Checkov to scan generated Terraform and Ansible configurations
    for security vulnerabilities, misconfigurations, and compliance issues.

    Example:
        infra security --env prod
        infra security --env dev --severity medium
        infra security --env staging --skip-check CKV_AWS_1 --skip-check CKV_AWS_2
    """
    import json as json_module
    import sys

    # Map severity string to enum
    severity_map = {
        "critical": ScanSeverity.CRITICAL,
        "high": ScanSeverity.HIGH,
        "medium": ScanSeverity.MEDIUM,
        "low": ScanSeverity.LOW,
        "info": ScanSeverity.INFO,
    }
    severity_threshold = severity_map[severity.lower()]

    # Initialize scanner
    scanner = SecurityScanner(
        severity_threshold=severity_threshold,
        skip_checks=list(skip_check),
    )

    # Check if checkov is available
    if not scanner.is_available():
        console.error("Checkov is not installed.")
        console.info("Install with: pip install checkov")
        console.info("Or: pipx install checkov")
        sys.exit(1)

    version = scanner.get_version()
    console.header(f"Security Scan: {env}")
    if version:
        console.status(f"Using Checkov {version}")

    # Determine scan directory (generated configs)
    generated_dir = Path("generated") / env
    if not generated_dir.exists():
        console.error(f"Generated directory not found: {generated_dir}")
        console.info("Run 'infra plan --env {env}' first to generate configurations.")
        sys.exit(1)

    console.status(f"Scanning {generated_dir}...")

    # Run scan
    result = scanner.scan(generated_dir, timeout=timeout)

    # Handle errors
    if result.error:
        console.error(f"Scan error: {result.error}")
        sys.exit(1)

    # Output results
    if output == "json":
        console.print(json_module.dumps(result.to_dict(), indent=2))
    else:
        _display_table_results(result, severity_threshold)

    # Exit with appropriate code
    if not result.passed:
        sys.exit(1)


def _display_table_results(result: ScanResult, threshold: ScanSeverity) -> None:
    """Display scan results as a formatted table."""
    # Summary
    console.print()
    console.header("Scan Summary")
    console.info(f"  Total checks: {result.total_checks}")
    console.success(f"  Passed: {result.passed_checks}")
    if result.failed_checks > 0:
        console.error(f"  Failed: {result.failed_checks}")
    else:
        console.info(f"  Failed: {result.failed_checks}")
    if result.skipped_checks > 0:
        console.info(f"  Skipped: {result.skipped_checks}")
    console.status(f"  Duration: {result.scan_duration_seconds:.1f}s")
    console.info(f"  Severity threshold: {threshold.value}")

    if not result.violations:
        console.print()
        console.success("No security issues found!")
        return

    # Violations table
    console.print()
    console.header(f"Security Issues ({len(result.violations)} found)")

    table = Table(show_header=True, header_style="bold")
    table.add_column("Severity", style="bold", width=10)
    table.add_column("Check ID", style="cyan", width=15)
    table.add_column("Resource", width=30)
    table.add_column("Description", width=40)

    # Sort by severity
    severity_order = {
        ScanSeverity.CRITICAL: 0,
        ScanSeverity.HIGH: 1,
        ScanSeverity.MEDIUM: 2,
        ScanSeverity.LOW: 3,
        ScanSeverity.INFO: 4,
    }
    sorted_violations = sorted(result.violations, key=lambda v: severity_order[v.severity])

    severity_styles = {
        ScanSeverity.CRITICAL: "bold red",
        ScanSeverity.HIGH: "red",
        ScanSeverity.MEDIUM: "yellow",
        ScanSeverity.LOW: "blue",
        ScanSeverity.INFO: "dim",
    }

    for violation in sorted_violations:
        style = severity_styles.get(violation.severity, "")
        table.add_row(
            f"[{style}]{violation.severity.value.upper()}[/{style}]",
            violation.check_id,
            _truncate(violation.resource, 30),
            _truncate(violation.description, 40),
        )

    console.print(table)

    # Overall result
    console.print()
    if result.passed:
        console.success(f"Scan passed (no issues at {threshold.value} severity or above)")
    else:
        blocking = [
            v for v in result.violations if severity_order[v.severity] <= severity_order[threshold]
        ]
        console.error(
            f"Scan failed: {len(blocking)} issue(s) at {threshold.value} severity or above"
        )


def _truncate(text: str, max_length: int) -> str:
    """Truncate text to max length with ellipsis."""
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."
