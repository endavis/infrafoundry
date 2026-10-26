"""Options and rendering shared by ``deps check`` and ``deps sync``."""

from collections.abc import Callable
from typing import Any

import click
from rich.markup import escape
from rich.table import Table

from infrafoundry.core.requirements.manager import RequirementsReport

from ...utils import console


def scope_options(func: Callable[..., Any]) -> Callable[..., Any]:
    """Add ``--env``, ``--package`` and ``--provider``, as ``infra plan`` takes them."""
    func = click.option(
        "--provider",
        "-P",
        "provider",
        multiple=True,
        help=(
            "Only packages targeting these provider(s) (can be used multiple times). "
            "Mutually exclusive with --package."
        ),
    )(func)
    func = click.option(
        "--package",
        "-p",
        "package_name",
        help="Only this package (mutually exclusive with -P)",
    )(func)
    return click.option("--env", "-e", required=True, help="Environment name")(func)


def resolve_scope(
    package_name: str | None, provider: tuple[str, ...]
) -> tuple[str | None, list[str] | None]:
    """Turn the scope options into the filters ``RequirementsManager`` takes.

    Raises:
        click.UsageError: If both ``--package`` and ``--provider`` are given
    """
    if package_name and provider:
        raise click.UsageError("--package and --provider are mutually exclusive")
    return package_name, list(provider) if provider else None


def render_report(report: RequirementsReport) -> None:
    """Print one row per requirement, with its status and fix."""
    if not report.statuses:
        console.info(f"No blueprint requirements in scope for {report.env_name}.")
        return
    table = Table(show_header=True)
    table.add_column("Requirement", style="cyan")
    table.add_column("Kind", style="blue")
    table.add_column("Installed")
    table.add_column("Status")
    table.add_column("Needed by", style="magenta")
    for status in report.statuses:
        label = f"{status.name}{status.wanted}" if status.wanted else status.name
        table.add_row(
            escape(label),
            status.kind.value,
            escape(status.installed or "-"),
            "[green]ok[/green]" if status.satisfied else f"[red]{escape(status.problem)}[/red]",
            escape(", ".join(status.blueprints)),
        )
    console.print(table)
