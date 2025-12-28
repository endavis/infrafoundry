import click
from rich.table import Table

from infrafoundry.core.exceptions import InfraFoundryError, StateError
from infrafoundry.core.orchestrator import Orchestrator
from infrafoundry.core.state import DeploymentStatus

from ...decorators import with_orchestrator
from ...utils import console, raise_cli_error


@click.command()
@click.option("--env", "-e", help="Filter by environment")
@click.option(
    "--command",
    "-c",
    type=click.Choice(["plan", "apply", "destroy"]),
    help="Filter by command type",
)
@click.option(
    "--status",
    "-s",
    type=click.Choice(["completed", "failed", "in_progress", "planned"]),
    help="Filter by status",
)
@click.option("--limit", "-n", default=50, help="Number of deployments to show")
@click.option("--exclude-dry-runs", is_flag=True, help="Exclude dry-run deployments from history")
@with_orchestrator("Failed to show history", require_env=False, load_credentials=False)
def history(
    _ctx: click.Context,  # Added ctx argument to capture orchestrator
    orchestrator: Orchestrator,  # Added orchestrator argument
    env: str | None,
    command: str | None,
    status: str | None,
    limit: int,
    exclude_dry_runs: bool,
) -> None:
    """Show deployment history."""
    try:
        # Use orchestrator's state_manager
        state_manager = orchestrator.state_manager

        # Convert status string to enum if provided
        status_enum = None
        if status:
            status_enum = DeploymentStatus(status)

        deployments = state_manager.get_deployment_history(
            environment=env,
            command=command,
            status=status_enum,
            limit=limit,
            exclude_dry_run=exclude_dry_runs,
        )

        if not deployments:
            console.warning("No deployment history found.")
            # This info is relevant if the state DB is not initialized.
            # However, orchestrator._setup_state_manager should handle this.
            # If the DB doesn't exist, get_deployment_history would raise StateError.
            # So, we can remove the explicit "Run 'infra init'" here if StateError is caught below.
            console.info(
                "Run 'infra init' to initialize state tracking."
            )  # Keep for now, will remove below
            return

        table = Table(title="Deployment History")
        table.add_column("ID", style="cyan")
        table.add_column("Environment", style="green")
        table.add_column("Command", style="blue")
        table.add_column("Status", style="magenta")
        table.add_column("Dry Run", style="yellow")
        table.add_column("Started", style="dim")
        table.add_column("User", style="yellow")

        for deployment in deployments:
            status_str = (
                deployment.status.value
                if hasattr(deployment.status, "value")
                else str(deployment.status)
            )

            status_color = {
                "completed": "green",
                "failed": "red",
                "in_progress": "yellow",
                "planned": "cyan",
            }.get(status_str, "white")

            dry_run_indicator = "✓" if deployment.dry_run else ""

            table.add_row(
                str(deployment.id),
                deployment.environment,
                deployment.command,
                f"[{status_color}]{status_str}[/{status_color}]",
                dry_run_indicator,
                (
                    deployment.started_at.strftime("%Y-%m-%d %H:%M:%S")
                    if deployment.started_at
                    else ""
                ),
                deployment.user or "unknown",
            )

        console.print(table)

    except click.ClickException:
        raise
    except StateError as exc:
        if "no such table" in str(exc).lower():
            console.info("Run 'infra init' to initialize state tracking.")
        raise_cli_error("Failed to show history", exc)
    except InfraFoundryError as exc:
        raise_cli_error("Failed to show history", exc)
    except Exception as exc:
        if "no such table" in str(exc).lower():
            console.info("Run 'infra init' to initialize state tracking.")
        raise_cli_error("Failed to show history", exc)
