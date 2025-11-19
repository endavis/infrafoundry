"""Rollback infrastructure to previous deployment command."""

import click
from rich.console import Console

from ..utils import raise_cli_error

console = Console()


@click.command()
@click.option("--deployment-id", "-d", required=True, type=int, help="Deployment ID to rollback to")
@click.option(
    "--auto-approve",
    is_flag=True,
    help="Skip confirmation prompt and apply immediately",
)
@click.pass_context
def rollback(ctx: click.Context, deployment_id: int, auto_approve: bool) -> None:
    """Rollback infrastructure to a previous deployment state."""
    try:
        # Import helper function from main module
        from ..main import _get_orchestrator

        orchestrator = _get_orchestrator(ctx.obj.get("config_dir"))

        # Perform rollback
        orchestrator.rollback(deployment_id=deployment_id, auto_approve=auto_approve)

    except Exception as exc:
        raise_cli_error("Rollback command failed", exc)
