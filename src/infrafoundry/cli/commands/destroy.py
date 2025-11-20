"""Destroy infrastructure command."""

import click
from rich.console import Console

from infrafoundry.core.orchestrator import Orchestrator

from ..decorators import with_orchestrator

console = Console()


@click.command()
@click.option("--env", "-e", required=True, help="Environment name")
@click.option("--auto-approve", is_flag=True, help="Skip confirmation prompts")
@click.option(
    "--resource",
    "-r",
    multiple=True,
    help="Specific resource name(s) to target (can be used multiple times)",
)
@with_orchestrator("Destroy failed")
def destroy(
    _ctx: click.Context,
    orchestrator: Orchestrator,
    env: str,
    auto_approve: bool,
    resource: tuple[str, ...],
) -> None:
    """Destroy infrastructure."""
    orchestrator.destroy(
        env,
        auto_approve=auto_approve,
        resource_filter=list(resource) if resource else None,
    )
    console.print("\n[bold green]Destroy complete![/bold green]")
