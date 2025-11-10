"""List available rollback points command."""

import sys

import click
from rich.console import Console
from rich.table import Table

console = Console()


@click.command(name="rollback-points")
@click.option("--env", "-e", required=True, help="Environment name")
@click.option("--limit", "-l", default=10, help="Maximum number of rollback points to show")
@click.pass_context
def rollback_points(ctx: click.Context, env: str, limit: int) -> None:
    """List available rollback points for an environment."""
    try:
        # Import helper function from main module
        from ..main import _get_orchestrator

        orchestrator = _get_orchestrator(ctx.obj.get("config_dir"))

        # Get rollback points
        deployments = orchestrator.state_manager.get_rollback_points(env, limit=limit)

        if not deployments:
            console.print(f"\n[yellow]No rollback points found for {env}.[/yellow]")
            console.print(
                "[dim]Rollback points are created from successful apply operations.[/dim]"
            )
            return

        # Display rollback points in a table
        table = Table(title=f"Rollback Points for {env}", show_header=True)
        table.add_column("ID", style="cyan")
        table.add_column("Date", style="green")
        table.add_column("User", style="blue")
        table.add_column("Resources", style="yellow")
        table.add_column("Commit", style="dim")

        for deployment in deployments:
            resource_count = len(deployment.rollback_data.get("resources", []))
            table.add_row(
                str(deployment.id),
                deployment.completed_at.strftime("%Y-%m-%d %H:%M:%S"),
                deployment.user or "unknown",
                str(resource_count),
                deployment.commit_sha or "N/A",
            )

        console.print()
        console.print(table)
        console.print(
            "\n[dim]Use 'infra rollback --deployment-id <ID>' to rollback to a specific point[/dim]"
        )

    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        import traceback

        console.print(traceback.format_exc())
        sys.exit(1)
