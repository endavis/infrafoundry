"""Rollback infrastructure to previous deployment command."""

import click
from rich.console import Console

from ..decorators import with_orchestrator

console = Console()


@click.command()
@click.option("--deployment-id", "-d", required=True, type=int, help="Deployment ID to rollback to")
@click.option(
    "--auto-approve",
    is_flag=True,
    help="Skip confirmation prompt and apply immediately",
)
@with_orchestrator("Rollback command failed", require_env=False, load_credentials=False)
def rollback(_ctx: click.Context, orchestrator, deployment_id: int, auto_approve: bool) -> None:
    """Rollback infrastructure to a previous deployment state."""
    orchestrator.rollback(deployment_id=deployment_id, auto_approve=auto_approve)
