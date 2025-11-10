"""Rollback infrastructure to previous deployment command."""

import sys

import click
from rich.console import Console

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

    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        import traceback

        console.print(traceback.format_exc())
        sys.exit(1)
