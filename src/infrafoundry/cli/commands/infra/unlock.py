"""Release (or list) deployment locks for an environment."""

from __future__ import annotations

from datetime import UTC, datetime

import click
from rich.table import Table

from infrafoundry.core.orchestrator import Orchestrator

from ...decorators import with_orchestrator
from ...utils import console


@click.command()
@click.option("--env", "-e", help="Environment name to unlock (required unless --list).")
@click.option("--force", is_flag=True, help="Release even if the lock is still active.")
@click.option("--yes", is_flag=True, help="Skip the confirmation prompt for --force.")
@click.option("--list", "list_locks", is_flag=True, help="List all current locks.")
@with_orchestrator("Unlock failed", require_env=False, load_credentials=False)
def unlock(
    _ctx: click.Context,
    orchestrator: Orchestrator,
    env: str | None,
    force: bool,
    yes: bool,
    list_locks: bool,
) -> None:
    """Release or inspect deployment locks."""
    state_manager = orchestrator.state_manager

    if list_locks:
        locks = state_manager.list_locks()
        if not locks:
            console.info("No deployment locks are currently held.")
            return
        table = Table(title="Deployment Locks")
        table.add_column("Environment", style="cyan")
        table.add_column("Locked By", style="green")
        table.add_column("Acquired", style="dim")
        table.add_column("Expires", style="dim")
        table.add_column("Status", style="magenta")
        now = datetime.now(UTC)
        for lock in locks:
            acquired = lock.acquired_at
            if acquired.tzinfo is None:
                acquired = acquired.replace(tzinfo=UTC)
            expires = lock.expires_at
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=UTC)
            status = "expired" if expires <= now else "active"
            table.add_row(
                lock.environment,
                lock.locked_by,
                acquired.strftime("%Y-%m-%d %H:%M:%S %Z"),
                expires.strftime("%Y-%m-%d %H:%M:%S %Z"),
                status,
            )
        console.print(table)
        return

    if not env:
        raise click.UsageError("--env is required unless --list is given.")

    current = state_manager.get_lock(env)
    if current is None:
        console.info(f"No lock held on environment '{env}'.")
        return

    expires = current.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    now = datetime.now(UTC)
    is_expired = expires <= now

    if force:
        if not yes and not click.confirm(
            f"Force-release lock on '{env}' held by {current.locked_by}?",
            default=False,
        ):
            console.warning("Unlock cancelled.")
            return
        released = state_manager.release_lock(env, force=True)
        if released:
            console.success(f"Lock on '{env}' released.")
        else:
            console.warning(f"No lock found on '{env}'.")
        return

    if is_expired:
        released = state_manager.release_lock(env, force=True)
        if released:
            console.success(f"Expired lock on '{env}' released.")
        else:
            console.warning(f"No lock found on '{env}'.")
        return

    # Active lock, no --force: refuse.
    raise click.ClickException(
        f"Environment '{env}' is locked by {current.locked_by} "
        f"(expires {current.expires_at}). Re-run with --force to release anyway."
    )
