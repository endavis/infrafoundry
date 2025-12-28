"""Rollback infrastructure to previous deployment commands."""

import click
from rich.table import Table

from infrafoundry.core.orchestrator import Orchestrator

from ...decorators import with_orchestrator
from ...utils import console


@click.group()
def rollback() -> None:
    """Rollback infrastructure to a previous deployment state."""
    pass


@rollback.command("list")
@click.option("--env", "-e", required=True, help="Environment name")
@click.option("--limit", "-l", default=10, help="Maximum number of rollback points to show")
@with_orchestrator(
    "Failed to list rollback points",
    load_credentials=False,
)
def rollback_list(_ctx: click.Context, orchestrator: Orchestrator, env: str, limit: int) -> None:
    """List available rollback points for an environment."""
    deployments = orchestrator.state_manager.get_rollback_points(env, limit=limit)

    if not deployments:
        console.warning(f"No rollback points found for {env}.")
        console.info("Rollback points are created from successful apply operations.")
        return

    table = Table(title=f"Rollback Points for {env}", show_header=True)
    table.add_column("ID", style="cyan")
    table.add_column("Date", style="green")
    table.add_column("User", style="blue")
    table.add_column("Resources", style="yellow")
    table.add_column("Commit", style="dim")

    for deployment in deployments:
        resource_count = (
            len(deployment.rollback_data.get("resources", [])) if deployment.rollback_data else 0
        )
        completed_time = (
            deployment.completed_at.strftime("%Y-%m-%d %H:%M:%S")
            if deployment.completed_at
            else "N/A"
        )
        table.add_row(
            str(deployment.id),
            completed_time,
            deployment.user or "unknown",
            str(resource_count),
            deployment.commit_sha or "N/A",
        )

    console.print()
    console.print(table)
    console.info("Use 'foundry infra rollback to <ID>' to rollback to a specific point")


@rollback.command("to")
@click.argument("deployment_id", type=int)
@click.option(
    "--auto-approve",
    is_flag=True,
    help="Skip confirmation prompt and apply immediately",
)
@with_orchestrator("Rollback command failed", require_env=False, load_credentials=False)
def rollback_to(
    _ctx: click.Context, orchestrator: Orchestrator, deployment_id: int, auto_approve: bool
) -> None:
    """Rollback infrastructure to a specific deployment ID."""

    def confirm_callback() -> bool:
        return click.confirm("Are you sure you want to rollback?")

    orchestrator.rollback(
        deployment_id=deployment_id,
        auto_approve=auto_approve,
        confirm_callback=confirm_callback,
    )
