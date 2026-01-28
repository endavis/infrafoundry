"""Envs command - List available environments."""

from typing import Any

import click

from infrafoundry.core.config import ConfigManager
from infrafoundry.core.exceptions import (
    ConfigurationError,
    EnvironmentNotFoundError,
    InfraFoundryError,
)

from ...output import output_data
from ...utils import console, raise_cli_error


@click.command()
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format (default: text)",
)
@click.pass_context
def envs(ctx: click.Context, output_format: str) -> None:
    """List available environments."""
    try:
        config_repo = ctx.obj.get("config_dir")
        if config_repo:
            config_manager = ConfigManager(base_dir=config_repo / "envs")
        else:
            config_manager = ConfigManager()
        environments = config_manager.list_environments()

        if not environments:
            if output_format == "json":
                output_data({"environments": []}, output_format)
            else:
                console.warning(
                    "No environments found. Check that INFRAFOUNDRY_CONFIG_REPO is set correctly."
                )
            return

        # Build data structure
        env_data: list[dict[str, Any]] = []
        for env_name in environments:
            env_config = config_manager.load_environment(env_name)
            env_data.append(
                {
                    "name": env_name,
                    "description": env_config.description or "",
                    "providers": env_config.providers,
                }
            )

        if output_format == "json":
            output_data({"environments": env_data}, output_format)
        else:
            console.header("Available environments:")
            for env in env_data:
                console.list_item(f"{env['name']}: {env['description'] or 'No description'}")
                console.info(f"    Providers: {', '.join(env['providers'])}")

    except click.ClickException:
        raise
    except (EnvironmentNotFoundError, ConfigurationError) as exc:
        raise_cli_error("Failed to list environments", exc)
    except InfraFoundryError as exc:
        raise_cli_error("Failed to list environments", exc)
    except Exception as exc:
        raise_cli_error("Failed to list environments", exc)
