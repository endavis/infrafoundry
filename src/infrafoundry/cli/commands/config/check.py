"""Check command - Validate consistency between filesystem and state database."""

from typing import Any

import click

from infrafoundry.core.config import ConfigManager
from infrafoundry.core.exceptions import InfraFoundryError

from ...output import output_data
from ...utils import console, raise_cli_error

# Reuse the shared helper from envs to query the state DB
from .envs import _get_state_db_environments


@click.command()
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format (default: text)",
)
@click.option(
    "--deep",
    is_flag=True,
    default=False,
    help="Cross-check resource counts per environment",
)
@click.pass_context
def check(ctx: click.Context, output_format: str, deep: bool) -> None:
    """Check consistency between filesystem environments and state database.

    Compares the environments found on the filesystem with those tracked
    in the state database and reports any divergence. Exits with code 1
    if inconsistencies are found.
    """
    try:
        # Get filesystem environments
        config_repo = ctx.obj.get("config_dir")
        if config_repo:
            config_manager = ConfigManager(base_dir=config_repo / "envs")
        else:
            config_manager = ConfigManager()
        fs_envs = set(config_manager.list_environments())

        # Get state DB environments
        db_env_list, resource_counts, db_available = _get_state_db_environments()
        db_envs = set(db_env_list)

        # If deep was requested but we didn't get counts yet, we already have them
        # from _get_state_db_environments; only need to add FS-only envs with 0 count
        if deep and db_available:
            for env in fs_envs - db_envs:
                resource_counts.setdefault(env, 0)

        consistent = fs_envs & db_envs
        fs_only = fs_envs - db_envs
        db_only = db_envs - fs_envs
        has_issues = bool(fs_only or db_only) and db_available

        result: dict[str, Any] = {
            "state_db_available": db_available,
            "consistent": sorted(consistent),
            "fs_only": sorted(fs_only),
            "db_only": sorted(db_only),
            "has_issues": has_issues,
        }

        if deep and db_available:
            result["resource_counts"] = {
                env: resource_counts.get(env, 0) for env in sorted(db_envs)
            }

        if output_format == "json":
            output_data(result, output_format)
        else:
            if not db_available:
                console.warning("State database unavailable - cannot check consistency")
                return

            if not has_issues:
                console.success(
                    "All environments are consistent between filesystem and state database"
                )
                if consistent:
                    console.info(f"  Consistent: {', '.join(sorted(consistent))}")
            else:
                console.error("Environment consistency check FAILED")
                if consistent:
                    console.info(f"  Consistent: {', '.join(sorted(consistent))}")
                if fs_only:
                    console.warning(
                        f"  Filesystem only (no state DB records): {', '.join(sorted(fs_only))}"
                    )
                if db_only:
                    console.warning(
                        f"  State DB only (no config directory): {', '.join(sorted(db_only))}"
                    )

            if deep and resource_counts:
                console.header("Resource counts:")
                for env in sorted(resource_counts):
                    console.info(f"  {env}: {resource_counts[env]} resource(s)")

        if has_issues:
            ctx.exit(1)

    except click.exceptions.Exit:
        raise
    except InfraFoundryError as exc:
        raise_cli_error("Consistency check failed", exc)
    except Exception as exc:
        raise_cli_error("Consistency check failed", exc)
