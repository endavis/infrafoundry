"""New command to scaffold projects from blueprints."""

import click
from rich.console import Console
from rich.table import Table

from infrafoundry.core.blueprints import BlueprintManager

console = Console()


@click.group(invoke_without_command=True)
@click.pass_context
def new(ctx: click.Context) -> None:
    """Create new infrastructure from blueprints."""
    if ctx.invoked_subcommand is None:
        # Default action: list blueprints
        list_blueprints()


def list_blueprints() -> None:
    """List available blueprints."""
    manager = BlueprintManager()
    blueprints = manager.list_blueprints()

    if not blueprints:
        console.print("[yellow]No blueprints found.[/yellow]")
        return

    table = Table(title="Available Blueprints")
    table.add_column("Name", style="cyan")
    table.add_column("Description")
    table.add_column("Version", style="dim")

    for bp in blueprints:
        table.add_row(bp.name, bp.description, bp.version)

    console.print(table)


@new.command()
@click.argument("blueprint_name")
@click.argument("target_dir", type=click.Path())
def create(blueprint_name: str, target_dir: str) -> None:
    """Instantiate a blueprint.

    BLUEPRINT_NAME: Name of the blueprint to use.
    TARGET_DIR: Directory to create the configuration in.
    """
    manager = BlueprintManager()

    try:
        from pathlib import Path

        manager.instantiate_blueprint(blueprint_name, Path(target_dir), context={})
        console.print(f"[green]✓ Successfully created project in {target_dir}[/green]")
    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
    except Exception as e:
        console.print(f"[red]Unexpected error: {e}[/red]")
