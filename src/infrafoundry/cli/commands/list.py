"""List resources in an environment command."""

import click

from infrafoundry.core.config import ConfigManager
from infrafoundry.core.exceptions import (
    ConfigurationError,
    EnvironmentNotFoundError,
    InfraFoundryError,
)

from ..utils import console, raise_cli_error


@click.command(name="list")
@click.option("--env", "-e", required=True, help="Environment name")
@click.option("--provider", "-p", help="Filter by provider (e.g., proxmox, opnsense)")
@click.option("--type", "-t", help="Filter by resource type (e.g., vms, firewall_rules)")
@click.pass_context
def list_resources(ctx: click.Context, env: str, provider: str | None, type: str | None) -> None:
    """List all resources in an environment."""
    try:
        config_repo = ctx.obj.get("config_dir")
        if config_repo:
            config_manager = ConfigManager(base_dir=config_repo / "envs")
        else:
            config_manager = ConfigManager()

        # Get all resources from all providers (handles both formats)
        all_resources = config_manager.get_all_resources_all_providers(env)

        # Apply filters
        if provider:
            all_resources = [r for r in all_resources if r.provider == provider]
        if type:
            all_resources = [r for r in all_resources if r.type == type]

        if not all_resources:
            if type and provider:
                console.warning(f"No resources found with provider '{provider}' and type '{type}'")
            elif type:
                console.warning(f"No resources found with type '{type}'")
            elif provider:
                console.warning(f"No resources found with provider '{provider}'")
            else:
                console.warning("No resources found")
            return

        console.header(f"Resources in {env}:")

        # Sort all resources by name
        all_resources.sort(key=lambda r: r.name)

        # Display each resource on a single line
        for resource in all_resources:
            console.info(f"  • {resource.name:<40} {resource.provider:<12} ({resource.type})")

        console.info(f"Total: {len(all_resources)} resources")

    except click.ClickException:
        raise
    except (EnvironmentNotFoundError, ConfigurationError) as exc:
        raise_cli_error("Failed to list resources", exc)
    except InfraFoundryError as exc:
        raise_cli_error("Failed to list resources", exc)
    except Exception as exc:
        raise_cli_error("Failed to list resources", exc)
