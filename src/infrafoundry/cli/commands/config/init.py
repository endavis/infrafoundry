"""Init command to scaffold new environments."""

from __future__ import annotations

import shutil
from pathlib import Path

import click
import yaml

from infrafoundry.core.config import ConfigManager
from infrafoundry.core.exceptions import EnvironmentNotFoundError

from ...utils import console


def _copy_environment(
    source_dir: Path,
    target_dir: Path,
    new_env_name: str,
    description: str | None,
) -> None:
    """Copy environment directory and update settings.

    Args:
        source_dir: Source environment directory
        target_dir: Target environment directory
        new_env_name: Name for the new environment
        description: Optional description for the new environment
    """
    # Copy the entire directory
    shutil.copytree(source_dir, target_dir)

    # Update settings.yaml with new environment info
    settings_file = target_dir / "settings.yaml"
    if settings_file.exists():
        with open(settings_file) as f:
            settings = yaml.safe_load(f) or {}

        # Update environment-specific settings
        settings["name"] = new_env_name
        if description:
            settings["description"] = description
        elif "description" in settings:
            settings["description"] = "Environment scaffolded from source"

        with open(settings_file, "w") as f:
            yaml.safe_dump(settings, f, default_flow_style=False, sort_keys=False)


def _create_minimal_environment(target_dir: Path, env_name: str, description: str | None) -> None:
    """Create a minimal environment structure.

    Args:
        target_dir: Target environment directory
        env_name: Name for the new environment
        description: Optional description
    """
    target_dir.mkdir(parents=True, exist_ok=True)

    settings = {
        "name": env_name,
        "description": description or f"New environment: {env_name}",
        "providers": [],
    }

    settings_file = target_dir / "settings.yaml"
    with open(settings_file, "w") as f:
        yaml.safe_dump(settings, f, default_flow_style=False, sort_keys=False)

    # Create empty resources directory
    resources_dir = target_dir / "resources"
    resources_dir.mkdir(exist_ok=True)

    # Create a sample resource file
    sample_file = resources_dir / "sample.yaml"
    sample_content = """\
# Sample resource configuration
# Uncomment and modify as needed
#
# resources:
#   - name: my-resource
#     provider: proxmox
#     type: vm
#     config:
#       # Add your configuration here
"""
    with open(sample_file, "w") as f:
        f.write(sample_content)


@click.command()
@click.argument("env_name")
@click.option(
    "--from",
    "from_env",
    help="Existing environment to scaffold from (copies and customizes configs)",
)
@click.option(
    "--description",
    "-d",
    help="Description for the new environment",
)
@click.option(
    "--force",
    "-f",
    is_flag=True,
    help="Overwrite existing environment directory",
)
@click.pass_context
def init(
    ctx: click.Context,
    env_name: str,
    from_env: str | None,
    description: str | None,
    force: bool,
) -> None:
    """Initialize a new environment.

    Creates a new environment directory structure. Use --from to scaffold
    from an existing environment (copies configs and customizes for new env).

    Examples:

        # Create minimal new environment
        foundry config init staging

        # Scaffold from existing environment
        foundry config init staging --from dev

        # With description
        foundry config init prod --from staging -d "Production environment"
    """
    config_dir = ctx.obj.get("config_dir")

    if not config_dir:
        console.error("Config directory not set. Use --config-dir or set INFRAFOUNDRY_CONFIG_REPO.")
        raise click.Abort()

    envs_dir = config_dir / "envs"
    target_dir = envs_dir / env_name

    # Check if target already exists
    if target_dir.exists():
        if force:
            console.warning(f"Removing existing environment: {env_name}")
            shutil.rmtree(target_dir)
        else:
            console.error(f"Environment '{env_name}' already exists. Use --force to overwrite.")
            raise click.Abort()

    if from_env:
        # Scaffold from existing environment
        try:
            config_manager = ConfigManager(base_dir=envs_dir)

            # Verify source environment exists
            if not config_manager.validate_environment(from_env):
                raise EnvironmentNotFoundError(
                    f"Source environment '{from_env}' not found",
                    context={"environment": from_env},
                )

            source_dir = envs_dir / from_env
            console.info(f"Scaffolding '{env_name}' from '{from_env}'...")

            _copy_environment(source_dir, target_dir, env_name, description)

            console.success(f"Environment '{env_name}' created from '{from_env}'")
            console.info(f"  Location: {target_dir}")
            console.info("")
            console.info("Next steps:")
            console.info(f"  1. Review and update: {target_dir}/settings.yaml")
            console.info("  2. Modify resource configs for the new environment")
            console.info("  3. Update any environment-specific secrets")

        except EnvironmentNotFoundError:
            console.error(f"Source environment '{from_env}' not found.")
            console.info("Available environments:")
            try:
                config_manager = ConfigManager(base_dir=envs_dir)
                for env in config_manager.list_environments():
                    console.info(f"  - {env}")
            except Exception:
                console.info("  (unable to list environments)")
            raise click.Abort() from None
        except Exception as e:
            console.error(f"Failed to scaffold environment: {e}")
            # Cleanup partial directory if it was created
            if target_dir.exists():
                shutil.rmtree(target_dir)
            raise click.Abort() from e
    else:
        # Create minimal new environment
        console.info(f"Creating new environment: {env_name}")

        try:
            _create_minimal_environment(target_dir, env_name, description)

            console.success(f"Environment '{env_name}' created")
            console.info(f"  Location: {target_dir}")
            console.info("")
            console.info("Next steps:")
            console.info(f"  1. Edit: {target_dir}/settings.yaml")
            console.info(f"  2. Add resources in: {target_dir}/resources/")
            console.info("  3. Run: foundry config validate --env " + env_name)

        except Exception as e:
            console.error(f"Failed to create environment: {e}")
            # Cleanup partial directory if it was created
            if target_dir.exists():
                shutil.rmtree(target_dir)
            raise click.Abort() from e
