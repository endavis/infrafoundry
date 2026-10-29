"""Remove a stale environment's rows from the state database."""

from __future__ import annotations

import datetime
from pathlib import Path

import click
from rich.table import Table

from infrafoundry.core.audit.models import AuditStatus
from infrafoundry.core.events.types import EventType
from infrafoundry.core.orchestrator import Orchestrator

from ...decorators import with_orchestrator
from ...utils import console
from .state import copy_state_db, sqlite_db_path


def _active_lock_holder(orchestrator: Orchestrator, env: str) -> tuple[str, object] | None:
    """Return (holder, expires_at) when ``env`` has an unexpired deployment lock."""
    lock = orchestrator.state_manager.get_lock(env)
    if lock is None:
        return None
    expires = lock.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=datetime.UTC)
    if expires <= datetime.datetime.now(datetime.UTC):
        return None
    return lock.locked_by, lock.expires_at


@click.command("prune")
@click.option("--env", "-e", required=True, help="Environment whose state rows are removed.")
@click.option("--dry-run", is_flag=True, help="Show the row counts without deleting anything.")
@click.option(
    "--force",
    is_flag=True,
    help="Prune even if the environment still exists in the config repo.",
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
    default=".",
    help="Directory for the pre-prune backup. Defaults to the current directory.",
)
@with_orchestrator("State prune failed", require_env=True, load_credentials=False)
def prune(
    _ctx: click.Context,
    orchestrator: Orchestrator,
    env: str,
    dry_run: bool,
    force: bool,
    yes: bool,
    no_backup: bool,
    backup_dir: str,
) -> None:
    """Delete one environment's rows from the state database.

    Removes resources, dependencies, deployments, deployment events and locks.
    The audit trail is kept. On SQLite a backup is taken first.
    """
    state_manager = orchestrator.state_manager

    in_config = env in orchestrator.config_manager.list_environments()
    if in_config and not force:
        raise click.ClickException(
            f"Environment '{env}' still exists in the config repo. "
            "Re-run with --force if it was renamed."
        )

    db_path = sqlite_db_path(orchestrator)
    if not dry_run and not no_backup and db_path is None:
        raise click.ClickException(
            "The state backend is not SQLite, so no file backup can be taken. "
            "Back it up with pg_dump, then re-run with --no-backup."
        )

    holder = _active_lock_holder(orchestrator, env)
    if holder is not None:
        raise click.ClickException(
            f"Environment '{env}' is locked by {holder[0]} (expires {holder[1]}). "
            f"Use 'foundry infra unlock --env {env}' first."
        )

    counts = state_manager.prune_environment(env, dry_run=True)
    total = sum(counts.values())
    if total == 0:
        console.info(f"Nothing to prune: no state rows for environment '{env}'.")
        return

    table = Table(title=f"State rows for '{env}'")
    table.add_column("Table", style="cyan")
    table.add_column("Rows", justify="right")
    for name, count in counts.items():
        table.add_row(name, str(count))
    table.add_row("total", str(total), style="bold")
    console.print(table)
    console.info("The audit trail (audit_entries) is kept.")

    if dry_run:
        console.info("Dry run: nothing was deleted.")
        return

    if not yes and not click.confirm(
        f"Delete {total} state row(s) for environment '{env}'?", default=False
    ):
        console.warning("Prune cancelled.")
        return

    backup_path: Path | None = None
    if not no_backup and db_path is not None:
        if not db_path.exists():
            raise click.ClickException("InfraFoundry state database file not found.")
        try:
            out = Path(backup_dir).resolve()
            out.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = copy_state_db(db_path, out, timestamp)
        except OSError as exc:
            raise click.ClickException(f"Backup failed, nothing was deleted: {exc}") from exc
        console.success(f"State database backed up to: {backup_path}")

    deleted = state_manager.prune_environment(env)
    console.success(f"Pruned {sum(deleted.values())} state row(s) for environment '{env}'.")

    orchestrator.audit_logger.log(
        event_type=EventType.STATE_PRUNED,
        action="state_pruned",
        status=AuditStatus.SUCCESS,
        environment=env,
        command="state prune",
        message=f"Pruned {sum(deleted.values())} state rows for environment '{env}'",
        changes_summary=dict(deleted),
        request_metadata={
            "backup_path": str(backup_path) if backup_path else None,
            "force": force,
            "backend": state_manager.engine.url.drivername,
        },
    )
