"""Clear stale planned rows that shadow deployed resources."""

from __future__ import annotations

import click
from rich.table import Table

from infrafoundry.core.audit.models import AuditStatus
from infrafoundry.core.events.types import EventType
from infrafoundry.core.orchestrator import Orchestrator

from ...decorators import with_orchestrator
from ...utils import console
from .state import active_lock_holder


@click.command("reconcile")
@click.option("--env", "-e", required=True, help="Environment whose state rows are reconciled.")
@click.option("--dry-run", is_flag=True, help="List the affected resources without writing.")
@click.option("--yes", is_flag=True, help="Skip the confirmation prompt.")
@with_orchestrator("State reconcile failed", require_env=True, load_credentials=False)
def reconcile(
    _ctx: click.Context,
    orchestrator: Orchestrator,
    env: str,
    dry_run: bool,
    yes: bool,
) -> None:
    """Restore deployed resources that a stale planned row hides.

    For each resource whose newest non-planned row is active but that has newer
    planned rows, appends a fresh active row. Nothing is deleted.
    """
    state_manager = orchestrator.state_manager

    holder = active_lock_holder(orchestrator, env)
    if holder is not None:
        raise click.ClickException(
            f"Environment '{env}' is locked by {holder[0]} (expires {holder[1]}). "
            f"Use 'foundry infra unlock --env {env}' first."
        )

    candidates, _ = state_manager.reconcile_planned(env, dry_run=True)
    if not candidates:
        console.info(f"Nothing to reconcile: no stale planned rows in environment '{env}'.")
        return

    table = Table(title=f"Stale planned rows in '{env}'")
    table.add_column("Provider", style="cyan")
    table.add_column("Type")
    table.add_column("Name")
    table.add_column("Stale planned rows", justify="right")
    for cand in candidates:
        table.add_row(cand.provider, cand.resource_type, cand.name, str(cand.stale_planned))
    console.print(table)
    console.info("An active row is appended for each; planned rows are kept.")

    if dry_run:
        console.info("Dry run: nothing was written.")
        return

    if not yes and not click.confirm(
        f"Append an active row for {len(candidates)} resource(s) in environment '{env}'?",
        default=False,
    ):
        console.warning("Reconcile cancelled.")
        return

    done, deployment_id = state_manager.reconcile_planned(env)
    console.success(f"Reconciled {len(done)} resource(s) in environment '{env}'.")

    orchestrator.audit_logger.log(
        event_type=EventType.STATE_RECONCILED,
        action="state_reconciled",
        status=AuditStatus.SUCCESS,
        environment=env,
        command="state reconcile",
        message=f"Reconciled {len(done)} resources in environment '{env}'",
        changes_summary={
            "resources": len(done),
            "stale_planned": sum(c.stale_planned for c in done),
        },
        request_metadata={
            "deployment_id": deployment_id,
            "names": [f"{c.provider}/{c.resource_type}/{c.name}" for c in done],
        },
    )
