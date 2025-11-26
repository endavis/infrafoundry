"""Envs command - List available environments."""

import click
from rich.console import Console

from infrafoundry.core.config import ConfigManager
from infrafoundry.core.exceptions import (
    ConfigurationError,
    EnvironmentNotFoundError,
    InfraFoundryError,
)

from ..utils import raise_cli_error

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
                "[yellow]No environments found. "
                "Check that INFRAFOUNDRY_CONFIG_REPO is set correctly.[/yellow]"
            )
            return

        console.print("[bold cyan]Available environments:[/bold cyan]")
        for env_name in environments:
            env_config = config_manager.load_environment(env_name)
            console.print(f"  • {env_name}: {env_config.description or 'No description'}")
            console.print(f"    Providers: {', '.join(env_config.providers)}")

    except click.ClickException:
        raise
    except (EnvironmentNotFoundError, ConfigurationError) as exc:
        raise_cli_error("Failed to list environments", exc)
    except InfraFoundryError as exc:
        raise_cli_error("Failed to list environments", exc)
    except Exception as exc:
        raise_cli_error("Failed to list environments", exc)
