"""Show infrastructure status command."""

import click
from rich.console import Console

from infrafoundry.core.orchestrator import Orchestrator

from ..decorators import with_orchestrator

console = Console()


@click.command()
@click.option("--env", "-e", required=True, help="Environment name")
@with_orchestrator("Status failed")
def status(_ctx: click.Context, orchestrator: Orchestrator, env: str) -> None:
    """Show infrastructure status."""
    orchestrator.status(env)
