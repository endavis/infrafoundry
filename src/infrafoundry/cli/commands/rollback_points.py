"""List available rollback points command."""

import click
from rich.console import Console
from rich.table import Table

from infrafoundry.core.orchestrator import Orchestrator

from ..decorators import with_orchestrator

console = Console()


@click.command(name="rollback-points")
@click.option("--env", "-e", required=True, help="Environment name")
@click.option("--limit", "-l", default=10, help="Maximum number of rollback points to show")
@with_orchestrator(
    "Failed to list rollback points",
    load_credentials=False,
)
def rollback_points(_ctx: click.Context, orchestrator: Orchestrator, env: str, limit: int) -> None:
    """List available rollback points for an environment."""
    deployments = orchestrator.state_manager.get_rollback_points(env, limit=limit)

    if not deployments:
        console.print(f"\n[yellow]No rollback points found for {env}.[/yellow]")
        console.print("[dim]Rollback points are created from successful apply operations.[/dim]")
        return

    table = Table(title=f"Rollback Points for {env}", show_header=True)
    table.add_column("ID", style="cyan")
    table.add_column("Date", style="green")
    table.add_column("User", style="blue")
    table.add_column("Resources", style="yellow")
    table.add_column("Commit", style="dim")

    for deployment in deployments:
        resource_count = len(deployment.rollback_data.get("resources", [])) if deployment.rollback_data else 0
        completed_time = deployment.completed_at.strftime("%Y-%m-%d %H:%M:%S") if deployment.completed_at else "N/A"
        table.add_row(
            str(deployment.id),
            completed_time,
            deployment.user or "unknown",
            str(resource_count),
            deployment.commit_sha or "N/A",
        )

    console.print()
    console.print(table)
    console.print(
        "\n[dim]Use 'infra rollback --deployment-id <ID>' to rollback to a specific point[/dim]"
    )
