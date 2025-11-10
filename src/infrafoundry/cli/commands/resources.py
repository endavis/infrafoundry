"""List tracked infrastructure resources command."""

import sys

import click
from rich.console import Console
from rich.table import Table

console = Console()


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
@click.pass_context
def resources(
    ctx: click.Context,
    env: str | None,
    provider: str | None,
    type: str | None,
    state: str | None,
) -> None:
    """List tracked infrastructure resources."""
    try:
        # Import helper function from main module
        from ..main import _get_orchestrator

        orchestrator = _get_orchestrator(ctx.obj.get("config_dir"))

        # Parse state filter
        resource_state = None
        if state:
            from infrafoundry.core.state import ResourceState

            try:
                resource_state = ResourceState[state.upper()]
            except KeyError:
                console.print(f"[bold red]Invalid state:[/bold red] {state}")
                console.print("Valid states: PLANNED, CREATING, ACTIVE, DELETING, DELETED, FAILED")
                sys.exit(1)

        # Get resources
        resources_list = orchestrator.state_manager.get_resources(
            environment=env,
            provider=provider,
            resource_type=type,
            state=resource_state,
        )

        if not resources_list:
            console.print("\n[yellow]No resources found matching filters.[/yellow]")
            return

        # Display resources in a table
        table = Table(title="Infrastructure Resources", show_header=True)
        table.add_column("Environment", style="cyan")
        table.add_column("Provider", style="magenta")
        table.add_column("Type", style="blue")
        table.add_column("Name", style="green")
        table.add_column("State", style="yellow")
        table.add_column("Terraform ID", style="dim")
        table.add_column("Last Updated", style="dim")

        for resource in resources_list:
            # Color code state
            state_colors = {
                "PLANNED": "blue",
                "CREATING": "yellow",
                "ACTIVE": "green",
                "DELETING": "orange",
                "DELETED": "red",
                "FAILED": "bold red",
            }
            state_color = state_colors.get(resource.state.name, "white")
            state_text = f"[{state_color}]{resource.state.name}[/{state_color}]"

            table.add_row(
                resource.environment,
                resource.provider,
                resource.resource_type,
                resource.name,
                state_text,
                resource.terraform_id or "[dim]N/A[/dim]",
                resource.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
            )

        console.print()
        console.print(table)
        console.print(f"\n[dim]Total: {len(resources_list)} resource(s)[/dim]")

    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        import traceback

        console.print(traceback.format_exc())
        sys.exit(1)
