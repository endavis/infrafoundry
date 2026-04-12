"""List configured packages in an environment."""

from typing import Any

import click

from infrafoundry.core.config import ConfigManager
from infrafoundry.core.config.package_loader import PackageLoader
from infrafoundry.core.exceptions import (
    ConfigurationError,
    EnvironmentNotFoundError,
    InfraFoundryError,
)

from ...output import output_data
from ...utils import console, raise_cli_error


@click.command("list")
@click.option("--env", "-e", required=True, help="Environment name (e.g., dev, prod)")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format (default: text)",
)
@click.pass_context
def list_packages(ctx: click.Context, env: str, output_format: str) -> None:
    """List configured packages in an environment."""
    try:
        config_repo = ctx.obj.get("config_dir")
        if config_repo:
            config_manager = ConfigManager(base_dir=config_repo / "envs")
        else:
            config_manager = ConfigManager()

        # Discover provider-scoped packages
        discovered_providers = config_manager.provider_centric.discover_providers(env)
        packages: list[dict[str, Any]] = []

        for provider_name in sorted(discovered_providers):
            for package_dir in config_manager._package_loader.discover_packages(env, provider_name):
                manifest = config_manager._package_loader._parse_manifest(
                    package_dir / PackageLoader.MANIFEST_FILENAME
                )
                packages.append(
                    {
                        "provider": provider_name,
                        "name": manifest.name,
                        "description": manifest.description or "",
                        "blueprint": manifest.blueprint or "",
                    }
                )

        # Discover env-root packages
        for package_dir in config_manager._package_loader.discover_env_root_packages(env):
            manifest = config_manager._package_loader._parse_manifest(
                package_dir / PackageLoader.MANIFEST_FILENAME
            )
            packages.append(
                {
                    "provider": manifest.provider or "",
                    "name": manifest.name,
                    "description": manifest.description or "",
                    "blueprint": manifest.blueprint or "",
                }
            )

        if not packages:
            if output_format == "json":
                output_data({"environment": env, "packages": []}, output_format)
            else:
                console.warning(f"No packages found in environment '{env}'.")
            return

        if output_format == "json":
            output_data({"environment": env, "packages": packages}, output_format)
        else:
            console.header(f"Packages in {env}:")
            for pkg in packages:
                provider = pkg["provider"]
                name = pkg["name"]
                description = pkg["description"]
                label = f"{provider}/{name}" if provider else name
                if description:
                    console.list_item(f"{label} — {description}")
                else:
                    console.list_item(label)

    except click.ClickException:
        raise
    except (EnvironmentNotFoundError, ConfigurationError) as exc:
        raise_cli_error("Failed to list packages", exc)
    except InfraFoundryError as exc:
        raise_cli_error("Failed to list packages", exc)
    except Exception as exc:
        raise_cli_error("Failed to list packages", exc)
