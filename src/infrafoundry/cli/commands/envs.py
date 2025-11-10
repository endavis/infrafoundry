"""Envs command - List available environments."""

import sys

import click
from rich.console import Console

from infrafoundry.core.config import ConfigManager

console = Console()


@click.command()
@click.pass_context
def envs(ctx: click.Context) -> None:
    """List available environments."""
    try:
        config_repo = ctx.obj.get("config_dir")
        if config_repo:
            config_manager = ConfigManager(base_dir=config_repo / "envs")
        else:
            config_manager = ConfigManager()
        environments = config_manager.list_environments()

        if not environments:
            console.print(
                "[yellow]No environments found. Create one in the envs/ directory.[/yellow]"
            )
            return

        console.print("[bold cyan]Available environments:[/bold cyan]")
        for env_name in environments:
            env_config = config_manager.load_environment(env_name)
            console.print(f"  • {env_name}: {env_config.description or 'No description'}")
            console.print(f"    Providers: {', '.join(env_config.providers)}")

    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        sys.exit(1)
