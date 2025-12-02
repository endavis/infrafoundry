"""List tracked infrastructure resources command."""

import click
from rich.table import Table

from infrafoundry.core.orchestrator import Orchestrator

from ..decorators import with_orchestrator
from ..utils import console


@click.command()
@click.option("--env", "-e", help="Filter by environment name")
@click.option("--provider", "-p", help="Filter by provider (proxmox, opnsense, kubernetes)")
@click.option(
    "--type",
    "-t",
    help="Filter by resource type (vm, deployment, firewall_rule, etc.)",
)
@click.option(
    "--state",
    "-s",
    help="Filter by state (PLANNED, CREATING, ACTIVE, DELETING, DELETED, FAILED)",
)
@with_orchestrator("Failed to list resources", require_env=False, load_credentials=False)
def resources(
    _ctx: click.Context,
    orchestrator: Orchestrator,
    env: str | None,
    provider: str | None,
    type: str | None,
    state: str | None,
) -> None:
    """List tracked infrastructure resources."""
    resource_state = None
    if state:
        from infrafoundry.core.state import ResourceState

        try:
            resource_state = ResourceState[state.upper()]
        except KeyError as exc:
            raise click.ClickException(
                f"Invalid state '{state}'. Valid: PLANNED, CREATING, ACTIVE, "
                "DELETING, DELETED, FAILED"
            ) from exc

    resources_list = orchestrator.state_manager.get_resources(
        environment=env,
        provider=provider,
        resource_type=type,
        state=resource_state,
    )

    if not resources_list:
        console.warning("No resources found matching filters.")
        return

    table = Table(title="Infrastructure Resources", show_header=True)
    table.add_column("Environment", style="cyan")
    table.add_column("Provider", style="magenta")
    table.add_column("Type", style="blue")
    table.add_column("Name", style="green")
    table.add_column("State", style="yellow")
    table.add_column("Terraform ID", style="dim")
    table.add_column("Last Updated", style="dim")

    state_colors = {
        "PLANNED": "blue",
        "CREATING": "yellow",
        "ACTIVE": "green",
        "DELETING": "orange",
        "DELETED": "red",
        "FAILED": "bold red",
    }
    for resource in resources_list:
        state_color = state_colors.get(resource.state.name, "white")
        state_text = f"[{state_color}]{resource.state.name}[/{state_color}]"

        table.add_row(
            resource.environment,
            resource.provider,
            resource.resource_type,
            resource.name,
            state_text,
            resource.terraform_id or "[dim]N/A",
            resource.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
        )

    console.print()
    console.print(table)
    console.print(f"\n[dim]Total: {len(resources_list)} resource(s)")
