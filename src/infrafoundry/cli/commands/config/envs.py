"""Envs command - List available environments with sync status."""

from typing import Any

import click

from infrafoundry.core.config import ConfigManager
from infrafoundry.core.exceptions import (
    ConfigurationError,
    EnvironmentNotFoundError,
    InfraFoundryError,
)
from infrafoundry.core.state.models import EnvironmentSyncStatus

from ...output import output_data
from ...utils import console, raise_cli_error


def _get_state_db_environments() -> tuple[list[str], dict[str, int], bool]:
    """Query the state database for known environments.

    Returns:
        Tuple of (environment names, resource counts per env, success flag).
        On failure returns ([], {}, False).
    """
    try:
        from infrafoundry.core.state.state_manager import StateManager

        state_mgr = StateManager()
        state_mgr.initialize()
        envs = state_mgr.list_environments()
        counts = {env: state_mgr.count_resources(env) for env in envs}
        return envs, counts, True
    except Exception:
        return [], {}, False


def _compute_sync_status(in_filesystem: bool, in_state_db: bool) -> EnvironmentSyncStatus:
    """Compute sync status for an environment.

    Args:
        in_filesystem: Whether the environment exists on the filesystem
        in_state_db: Whether the environment exists in the state database

    Returns:
        The appropriate sync status
    """
    if in_filesystem and in_state_db:
        return EnvironmentSyncStatus.OK
    elif in_filesystem:
        return EnvironmentSyncStatus.FS_ONLY
    else:
        return EnvironmentSyncStatus.DB_ONLY


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
    """List available environments with sync status."""
    try:
        # Get filesystem environments
        config_repo = ctx.obj.get("config_dir")
        if config_repo:
            config_manager = ConfigManager(base_dir=config_repo / "envs")
        else:
            config_manager = ConfigManager()
        fs_environments = config_manager.list_environments()

        # Get state DB environments
        db_environments, resource_counts, db_available = _get_state_db_environments()

        # Build union of all environment names
        all_env_names = sorted(set(fs_environments) | set(db_environments))

        if not all_env_names:
            if output_format == "json":
                output_data(
                    {"environments": [], "state_db_available": db_available},
                    output_format,
                )
            else:
                console.warning(
                    "No environments found. Check that INFRAFOUNDRY_CONFIG_REPO is set correctly."
                )
            return

        # Build data structure with sync status
        env_data: list[dict[str, Any]] = []
        for env_name in all_env_names:
            in_fs = env_name in fs_environments
            in_db = env_name in db_environments
            sync_status = _compute_sync_status(in_fs, in_db)

            entry: dict[str, Any] = {
                "name": env_name,
                "in_filesystem": in_fs,
                "in_state_db": in_db,
                "sync_status": sync_status.value,
                "resource_count": resource_counts.get(env_name, 0),
                "description": "",
                "providers": [],
            }

            # Load details from filesystem if available
            if in_fs:
                try:
                    env_config = config_manager.load_environment(env_name)
                    entry["description"] = env_config.description or ""
                    entry["providers"] = env_config.providers
                except Exception:  # nosec B110 - graceful degradation for missing/corrupt config
                    pass

            env_data.append(entry)

        if output_format == "json":
            output_data(
                {
                    "environments": env_data,
                    "state_db_available": db_available,
                },
                output_format,
            )
        else:
            console.header("Available environments:")
            if not db_available:
                console.warning("State database unavailable - showing filesystem environments only")
            for env in env_data:
                status_label = env["sync_status"].upper().replace("_", "-")
                desc = env["description"] or "No description"
                console.list_item(f"{env['name']}: {desc} [{status_label}]")
                details: list[str] = []
                if env["providers"]:
                    details.append(f"Providers: {', '.join(env['providers'])}")
                if env["resource_count"] > 0:
                    details.append(f"Tracked resources: {env['resource_count']}")
                for detail in details:
                    console.info(f"    {detail}")

    except click.ClickException:
        raise
    except (EnvironmentNotFoundError, ConfigurationError) as exc:
        raise_cli_error("Failed to list environments", exc)
    except InfraFoundryError as exc:
        raise_cli_error("Failed to list environments", exc)
    except Exception as exc:
        raise_cli_error("Failed to list environments", exc)
