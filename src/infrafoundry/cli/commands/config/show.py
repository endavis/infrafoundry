"""Show command to display resolved configuration."""

from __future__ import annotations

import json
from typing import Any

import click
import yaml
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from infrafoundry.core.config import ConfigManager
from infrafoundry.core.exceptions import (
    ConfigurationError,
    EnvironmentNotFoundError,
    InfraFoundryError,
)

from ...utils import console, raise_cli_error


def _resource_to_dict(resource: Any) -> dict[str, Any]:
    """Convert a ResourceConfig to a dictionary.

    Args:
        resource: ResourceConfig object

    Returns:
        Dictionary representation
    """
    result: dict[str, Any] = {
        "name": resource.name,
        "provider": resource.provider,
        "type": resource.type,
        "config": resource.config,
    }

    # Include depends_on from config if present
    if resource.config.get("depends_on"):
        result["depends_on"] = resource.config["depends_on"]

    return result


def _format_yaml(data: dict[str, Any]) -> str:
    """Format data as YAML string.

    Args:
        data: Dictionary to format

    Returns:
        YAML string
    """
    return yaml.safe_dump(data, default_flow_style=False, sort_keys=False)


def _format_json(data: dict[str, Any]) -> str:
    """Format data as JSON string.

    Args:
        data: Dictionary to format

    Returns:
        JSON string
    """
    return json.dumps(data, indent=2)


@click.command()
@click.option("--env", "-e", required=True, help="Environment name")
@click.option(
    "--provider",
    "-p",
    help="Filter by provider (e.g., proxmox, kubernetes)",
)
@click.option(
    "--resource-type",
    "-t",
    help="Filter by resource type (e.g., vm, container)",
)
@click.option(
    "--resource",
    "-r",
    help="Show specific resource by name",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["table", "yaml", "json"]),
    default="table",
    help="Output format (default: table)",
)
@click.option(
    "--settings-only",
    is_flag=True,
    help="Show only environment settings, not resources",
)
@click.pass_context
def show(
    ctx: click.Context,
    env: str,
    provider: str | None,
    resource_type: str | None,
    resource: str | None,
    output_format: str,
    settings_only: bool,
) -> None:
    """Show resolved configuration for an environment.

    Displays the effective configuration after variable substitution,
    with options to filter by provider, resource type, or specific resource.

    Examples:

        # Show all config for dev environment
        foundry config show --env dev

        # Show only Proxmox resources
        foundry config show --env dev --provider proxmox

        # Show specific resource
        foundry config show --env dev --resource my-vm

        # Output as YAML
        foundry config show --env dev --format yaml

        # Show only environment settings
        foundry config show --env dev --settings-only
    """
    try:
        config_dir = ctx.obj.get("config_dir")
        config_manager = ConfigManager(base_dir=config_dir / "envs" if config_dir else None)

        # Load environment settings
        env_config = config_manager.load_environment(env)

        if settings_only:
            _show_settings(env, env_config, output_format)
            return

        # Load all resources
        all_resources = config_manager.get_all_resources_all_providers(env)

        # Apply filters
        filtered_resources = all_resources

        if provider:
            filtered_resources = [r for r in filtered_resources if r.provider == provider]

        if resource_type:
            filtered_resources = [r for r in filtered_resources if r.type == resource_type]

        if resource:
            filtered_resources = [r for r in filtered_resources if r.name == resource]

        if not filtered_resources and (provider or resource_type or resource):
            console.warning("No resources found matching the specified filters.")
            return

        # Display based on format
        if output_format == "table":
            _show_table(env, env_config, filtered_resources)
        elif output_format == "yaml":
            _show_yaml(env, env_config, filtered_resources)
        elif output_format == "json":
            _show_json(env, env_config, filtered_resources)

    except click.ClickException:
        raise
    except (EnvironmentNotFoundError, ConfigurationError) as exc:
        raise_cli_error("Failed to show configuration", exc)
    except InfraFoundryError as exc:
        raise_cli_error("Failed to show configuration", exc)
    except Exception as exc:
        raise_cli_error("Failed to show configuration", exc)


def _show_settings(env: str, env_config: Any, output_format: str) -> None:
    """Show only environment settings.

    Args:
        env: Environment name
        env_config: EnvironmentConfig object
        output_format: Output format (table, yaml, json)
    """
    settings_dict = {
        "name": env_config.name or env,
        "description": env_config.description,
        "providers": env_config.providers,
    }

    # Add any additional settings from the config
    if hasattr(env_config, "settings") and env_config.settings:
        settings_dict["settings"] = env_config.settings

    if output_format == "yaml":
        syntax = Syntax(_format_yaml(settings_dict), "yaml", theme="monokai")
        console.print(Panel(syntax, title=f"Environment: {env}", border_style="cyan"))
    elif output_format == "json":
        syntax = Syntax(_format_json(settings_dict), "json", theme="monokai")
        console.print(Panel(syntax, title=f"Environment: {env}", border_style="cyan"))
    else:
        console.header(f"Environment: {env}")
        console.info(f"  Description: {env_config.description or 'N/A'}")
        console.info(
            f"  Providers: {', '.join(env_config.providers) if env_config.providers else 'N/A'}"
        )


def _show_table(env: str, env_config: Any, resources: list[Any]) -> None:
    """Show configuration as formatted tables.

    Args:
        env: Environment name
        env_config: EnvironmentConfig object
        resources: List of ResourceConfig objects
    """
    # Environment header
    console.header(f"Environment: {env}")
    console.info(f"  Description: {env_config.description or 'N/A'}")
    console.info(
        f"  Providers: {', '.join(env_config.providers) if env_config.providers else 'N/A'}"
    )
    console.print("")

    if not resources:
        console.warning("No resources defined.")
        return

    # Group resources by provider
    by_provider: dict[str, list[Any]] = {}
    for r in resources:
        if r.provider not in by_provider:
            by_provider[r.provider] = []
        by_provider[r.provider].append(r)

    # Display each provider's resources
    for provider_name, provider_resources in sorted(by_provider.items()):
        table = Table(title=f"Provider: {provider_name}", show_header=True)
        table.add_column("Name", style="cyan")
        table.add_column("Type", style="green")
        table.add_column("Dependencies", style="dim")
        table.add_column("Config Keys", style="yellow")

        for r in sorted(provider_resources, key=lambda x: x.name):
            deps_list = r.config.get("depends_on", [])
            deps = ", ".join(deps_list) if deps_list else "-"
            config_keys = ", ".join(sorted(r.config.keys())) if r.config else "-"
            table.add_row(r.name, r.type, deps, config_keys)

        console.print(table)
        console.print("")


def _show_yaml(env: str, env_config: Any, resources: list[Any]) -> None:
    """Show configuration as YAML.

    Args:
        env: Environment name
        env_config: EnvironmentConfig object
        resources: List of ResourceConfig objects
    """
    output = {
        "environment": {
            "name": env_config.name or env,
            "description": env_config.description,
            "providers": env_config.providers,
        },
        "resources": [_resource_to_dict(r) for r in resources],
    }

    syntax = Syntax(_format_yaml(output), "yaml", theme="monokai", line_numbers=True)
    console.print(Panel(syntax, title=f"Configuration: {env}", border_style="cyan"))


def _show_json(env: str, env_config: Any, resources: list[Any]) -> None:
    """Show configuration as JSON.

    Args:
        env: Environment name
        env_config: EnvironmentConfig object
        resources: List of ResourceConfig objects
    """
    output = {
        "environment": {
            "name": env_config.name or env,
            "description": env_config.description,
            "providers": env_config.providers,
        },
        "resources": [_resource_to_dict(r) for r in resources],
    }

    syntax = Syntax(_format_json(output), "json", theme="monokai", line_numbers=True)
    console.print(Panel(syntax, title=f"Configuration: {env}", border_style="cyan"))
