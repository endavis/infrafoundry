"""Rollback infrastructure to previous deployment command."""

import click

from infrafoundry.core.orchestrator import Orchestrator

from ..decorators import with_orchestrator


@click.command()
@click.option("--deployment-id", "-d", required=True, type=int, help="Deployment ID to rollback to")
@click.option(
    "--auto-approve",
    is_flag=True,
    help="Skip confirmation prompt and apply immediately",
)
@with_orchestrator("Rollback command failed", require_env=False, load_credentials=False)
def rollback(
    _ctx: click.Context, orchestrator: Orchestrator, deployment_id: int, auto_approve: bool
) -> None:
    """Rollback infrastructure to a previous deployment state."""

    def confirm_callback() -> bool:
        return click.confirm("Are you sure you want to rollback?")

    orchestrator.rollback(
        deployment_id=deployment_id,
        auto_approve=auto_approve,
        confirm_callback=confirm_callback,
    )
