"""Move a package between environments."""

import os
from pathlib import Path

import click

from infrafoundry.core.exceptions import (
    ConfigurationError,
    EnvironmentNotFoundError,
    InfraFoundryError,
    PackageNotFoundError,
)
from infrafoundry.core.package_mover import PackageMover

from ...utils import console, raise_cli_error


@click.command("move-package")
@click.option("--env", "-e", required=True, help="Source environment name")
@click.option("--package", "-p", required=True, help="Package name to move")
@click.option("--to-env", required=True, help="Target environment name")
@click.option("--create-env", is_flag=True, help="Create target environment if it doesn't exist")
@click.option("--dry-run", is_flag=True, help="Show what would be done without executing")
@click.pass_context
def move_package(
    ctx: click.Context,
    env: str,
    package: str,
    to_env: str,
    create_env: bool,
    dry_run: bool,
) -> None:
    """Move a package from one environment to another.

    Safely relocates the package config directory, copies terraform state
    to the target, removes the moved resources from source state, and
    updates the InfraFoundry state database.
    """
    try:
        config_dir = ctx.obj.get("config_dir")
        if not config_dir:
            raise ConfigurationError(
                "No config directory configured. Use --config-dir or set INFRAFOUNDRY_CONFIG_REPO."
            )

        # config_dir from context points to the repo root (or repo/envs in some paths).
        # PackageMover expects the repo root containing envs/.
        # If config_dir already ends with /envs, go up one level.
        repo_root = config_dir.parent if config_dir.name == "envs" else config_dir

        generated_dir = Path(os.getenv("INFRAFOUNDRY_OUTPUT_DIR", "generated"))

        mover = PackageMover(config_dir=repo_root, generated_dir=generated_dir)

        if dry_run:
            console.header(f"Dry run: move package '{package}' from '{env}' to '{to_env}'")

        result = mover.execute(
            source_env=env,
            package_name=package,
            target_env=to_env,
            create_env=create_env,
            dry_run=dry_run,
        )

        if dry_run:
            console.info("")
            console.info("Planned actions:")
            for action in result["actions"]:
                console.list_item(action)
            console.info("")
            console.warning("No changes made (dry run)")
        else:
            console.success(
                f"Moved package '{package}' from '{env}' to '{to_env}' "
                f"(provider: {result['provider']})"
            )
            rm_count = result.get("state_rm_count", 0)
            if rm_count:
                console.info(f"  Removed {rm_count} resource(s) from source terraform state")
            if result.get("state_db_updated"):
                console.info("  Updated InfraFoundry state DB")

    except click.ClickException:
        raise
    except (PackageNotFoundError, EnvironmentNotFoundError, ConfigurationError) as exc:
        raise_cli_error("Failed to move package", exc)
    except InfraFoundryError as exc:
        raise_cli_error("Failed to move package", exc)
    except Exception as exc:
        raise_cli_error("Failed to move package", exc)
