"""Diff configurations between environments."""

import click

from infrafoundry.core.config import ConfigManager
from infrafoundry.core.config.diff import diff_environments
from infrafoundry.core.exceptions import (
    ConfigurationError,
    EnvironmentNotFoundError,
    InfraFoundryError,
)

from ..utils import console, raise_cli_error


@click.command()
@click.option("--env-a", required=True, help="First environment name to compare")
@click.option("--env-b", required=True, help="Second environment name to compare")
@click.option(
    "--provider",
    "-p",
    help="Scope diff to a single provider (e.g., proxmox, opnsense, kubernetes)",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Show detailed configuration differences for changed resources",
)
@click.pass_context
def diff(ctx: click.Context, env_a: str, env_b: str, provider: str | None, verbose: bool) -> None:
    """Compare configurations between two environments."""
    try:
        config_repo = ctx.obj.get("config_dir")
        config_manager = ConfigManager(base_dir=config_repo / "envs" if config_repo else None)

        result = diff_environments(config_manager, env_a, env_b, provider_filter=provider)

        console.header(f"Comparing {env_a} vs {env_b}")

        if result.is_empty():
            console.success("No differences found.")
            return

        if result.settings_changes:
            console.header("Settings differences")
            for change in result.settings_changes:
                console.info(f"  • {change}")

        if result.resources_added:
            console.header(f"Resources only in {env_b}")
            for key in result.resources_added:
                console.info(f"  • {key}")

        if result.resources_removed:
            console.header(f"Resources only in {env_a}")
            for key in result.resources_removed:
                console.info(f"  • {key}")

        if result.resources_changed:
            console.header("Resources changed")
            for key in result.resources_changed:
                console.info(f"  • {key}")
                if verbose and key in result.resources_changed_details:
                    for detail in result.resources_changed_details[key]:
                        console.info(f"    {detail}")

    except click.ClickException:
        raise
    except (EnvironmentNotFoundError, ConfigurationError) as exc:
        raise_cli_error("Failed to diff configurations", exc)
    except InfraFoundryError as exc:
        raise_cli_error("Failed to diff configurations", exc)
    except Exception as exc:
        raise_cli_error("Failed to diff configurations", exc)
