"""Shared utilities for doctor commands.

Provides the ``CheckResult`` dataclass, dependency checking helpers, and
rendering functions (Rich table and JSON) used by ``foundry doctor``,
``config doctor``, and ``infra doctor``.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from typing import Any

from rich.console import Console
from rich.table import Table

from ..output import output_data

console = Console()


@dataclass
class CheckResult:
    """Result of a health check."""

    name: str
    status: str  # "ok", "warning", "error"
    message: str
    suggestion: str = ""


def check_dependency(name: str, command: str, suggestion: str) -> CheckResult:
    """Check if a command-line dependency is available.

    Args:
        name: Human-readable name of the dependency.
        command: CLI command to look up via ``shutil.which``.
        suggestion: Help text shown when the dependency is missing.

    Returns:
        A ``CheckResult`` with status ``ok`` or ``error``.
    """
    path = shutil.which(command)
    if path:
        return CheckResult(
            name=name,
            status="ok",
            message=f"Found at {path}",
        )
    return CheckResult(
        name=name,
        status="error",
        message="Not found",
        suggestion=suggestion,
    )


def render_check_results_text(
    results: list[CheckResult],
    *,
    title: str = "Health Check Results",
) -> None:
    """Render a list of check results as a Rich table.

    Args:
        results: Check results to display.
        title: Table title.
    """
    table = Table(title=title, show_header=True)
    table.add_column("Check", style="cyan")
    table.add_column("Status")
    table.add_column("Details")

    status_icons = {
        "ok": "[green]OK[/green]",
        "warning": "[yellow]WARN[/yellow]",
        "error": "[red]FAIL[/red]",
    }

    for result in results:
        status_display = status_icons.get(result.status, result.status)
        details = result.message
        if result.suggestion:
            details += f"\n[dim]{result.suggestion}[/dim]"
        table.add_row(result.name, status_display, details)

    console.print()
    console.print(table)
    console.print()

    errors = sum(1 for r in results if r.status == "error")
    warnings = sum(1 for r in results if r.status == "warning")

    if errors > 0:
        console.print(f"[red]Found {errors} error(s) and {warnings} warning(s)[/red]")
        console.print("[dim]Fix errors before using InfraFoundry[/dim]")
    elif warnings > 0:
        console.print(f"[yellow]Found {warnings} warning(s)[/yellow]")
        console.print("[dim]InfraFoundry should work but some features may be limited[/dim]")
    else:
        console.print("[green]All checks passed![/green]")
        console.print("[dim]InfraFoundry is ready to use[/dim]")

    console.print()


def render_check_results_json(results: list[CheckResult]) -> None:
    """Render a list of check results as JSON.

    Args:
        results: Check results to serialize.
    """
    errors = sum(1 for r in results if r.status == "error")
    warnings = sum(1 for r in results if r.status == "warning")

    check_data: list[dict[str, Any]] = []
    for result in results:
        check_dict: dict[str, Any] = {
            "name": result.name,
            "status": result.status,
            "message": result.message,
        }
        if result.suggestion:
            check_dict["suggestion"] = result.suggestion
        check_data.append(check_dict)

    output_data(
        {
            "checks": check_data,
            "summary": {
                "total": len(results),
                "errors": errors,
                "warnings": warnings,
                "ok": len(results) - errors - warnings,
            },
        },
        "json",
    )
