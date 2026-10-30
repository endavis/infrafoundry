"""Rename an environment in the state database and its generated directory."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import click
from rich.table import Table

from infrafoundry.core.audit.models import AuditStatus
from infrafoundry.core.events.types import EventType
from infrafoundry.core.orchestrator import Orchestrator

from ...decorators import with_orchestrator
from ...utils import console
from .state import active_lock_holder, backup_state_db, copy_state_db, sqlite_db_path


@click.command("rename-env")
@click.option("--env", "-e", required=True, help="Current environment name in the state database.")
@click.option("--to-env", required=True, help="New environment name.")
@click.option("--dry-run", is_flag=True, help="Show what would change without changing anything.")
@click.option(
    "--force",
    is_flag=True,
    help="Skip the check that the config repo already uses the new name.",
)
@click.option("--yes", is_flag=True, help="Skip the confirmation prompt.")
@click.option(
    "--no-backup",
    is_flag=True,
    help="Do not back up the state database first (required for non-SQLite backends).",
)
@click.option(
    "--backup-dir",
    type=click.Path(file_okay=False, dir_okay=True, writable=True),
    default=None,
    help=(
        "Directory for the pre-rename backup. Defaults to a 'backups' directory "
        "next to the state database. Existing backups are never overwritten."
    ),
)
@click.option(
    "--no-move-generated",
    is_flag=True,
    help="Rename the state only; leave the generated/<env> directory alone.",
)
@with_orchestrator("State rename-env failed", require_env=True, load_credentials=False)
def rename_env(
    _ctx: click.Context,
    orchestrator: Orchestrator,
    env: str,
    to_env: str,
    dry_run: bool,
    force: bool,
    yes: bool,
    no_backup: bool,
    backup_dir: str | None,
    no_move_generated: bool,
) -> None:
    """Rename an environment in the state database (and its generated directory).

    Renames resources, deployments, locks and the environment recorded in rollback
    snapshots. The audit trail is kept under the old name. On SQLite a backup is taken
    first. Rename the config repo directory first.
    """
    state_manager = orchestrator.state_manager

    if env == to_env:
        raise click.ClickException(f"--env and --to-env are the same ('{env}'). Nothing to rename.")

    if any(state_manager.count_environment_rows(to_env).values()):
        raise click.ClickException(
            f"Environment '{to_env}' already has state rows. Nothing was changed."
        )
    counts = state_manager.count_environment_rows(env)
    if not any(counts.values()):
        raise click.ClickException(f"Environment '{env}' has no state rows. Nothing to rename.")

    config_envs = orchestrator.config_manager.list_environments()
    if not force:
        if to_env not in config_envs:
            raise click.ClickException(
                f"Environment '{to_env}' does not exist in the config repo. Rename the config "
                "directory and its settings.yaml name: first, or re-run with --force."
            )
        if env in config_envs:
            raise click.ClickException(
                f"Environment '{env}' still exists in the config repo. "
                "Rename its directory first, or re-run with --force."
            )

    holder = active_lock_holder(orchestrator, env)
    if holder is not None:
        raise click.ClickException(
            f"Environment '{env}' is locked by {holder[0]} (expires {holder[1]}). "
            f"Use 'foundry infra unlock --env {env}' first."
        )

    db_path = sqlite_db_path(orchestrator)
    if not dry_run and not no_backup and db_path is None:
        raise click.ClickException(
            "The state backend is not SQLite, so no file backup can be taken. "
            "Back it up with pg_dump, then re-run with --no-backup."
        )

    generated_root = Path(os.getenv("INFRAFOUNDRY_OUTPUT_DIR", "generated"))
    old_dir = generated_root / env
    new_dir = generated_root / to_env
    if not no_move_generated:
        if new_dir.exists():
            raise click.ClickException(
                f"Generated directory '{new_dir}' already exists. "
                "Move it aside or use --no-move-generated."
            )
        if not old_dir.exists():
            raise click.ClickException(
                f"Generated directory '{old_dir}' not found. "
                "Use --no-move-generated to rename the state only."
            )

    total = sum(counts.values())
    table = Table(title=f"State rows renamed '{env}' -> '{to_env}'")
    table.add_column("Table", style="cyan")
    table.add_column("Rows", justify="right")
    for name, count in counts.items():
        table.add_row(name, str(count))
    table.add_row("total", str(total), style="bold")
    console.print(table)
    console.info("The audit trail (audit_entries) keeps the old name.")
    if no_move_generated:
        console.info("The generated directory is not moved.")
    else:
        console.info(f"Generated directory: {old_dir} -> {new_dir}")

    if dry_run:
        console.info("Dry run: nothing was changed.")
        return

    if not yes and not click.confirm(
        f"Rename environment '{env}' to '{to_env}' ({total} state row(s))?", default=False
    ):
        console.warning("Rename cancelled.")
        return

    backup_path: Path | None = None
    if not no_backup and db_path is not None:
        backup_path = backup_state_db(
            db_path, backup_dir, copier=copy_state_db, unchanged="renamed"
        )

    renamed = state_manager.rename_environment(env, to_env)
    console.success(f"Renamed {sum(renamed.values())} state row(s) '{env}' -> '{to_env}'.")

    moved = False
    move_error: str | None = None
    if not no_move_generated:
        try:
            shutil.move(str(old_dir), str(new_dir))
            moved = True
            console.success(f"Moved {old_dir} -> {new_dir}")
        except OSError as exc:
            move_error = str(exc)

    orchestrator.audit_logger.log(
        event_type=EventType.STATE_ENV_RENAMED,
        action="state_env_renamed",
        status=AuditStatus.FAILED if move_error else AuditStatus.SUCCESS,
        environment=to_env,
        command="state rename-env",
        message=(
            f"Renamed environment '{env}' to '{to_env}' ({sum(renamed.values())} state rows)"
            + (f"; generated directory move failed: {move_error}" if move_error else "")
        ),
        changes_summary=dict(renamed),
        request_metadata={
            "old_environment": env,
            "new_environment": to_env,
            "backup_path": str(backup_path) if backup_path else None,
            "generated_moved": moved,
            "force": force,
            "backend": state_manager.engine.url.drivername,
        },
    )

    if move_error:
        raise click.ClickException(
            f"The state database is already renamed to '{to_env}', but moving the generated "
            f"directory failed: {move_error}. "
            f"Backup: {backup_path if backup_path else 'none'}. "
            f"Finish with: mv '{old_dir}' '{new_dir}'"
        )
