"""Destroy infrastructure command."""

import click

from infrafoundry.core.orchestrator import Orchestrator

from ...decorators import with_orchestrator
from ...utils import console


@click.command()
@click.option("--env", "-e", required=True, help="Environment name")
@click.option("--auto-approve", is_flag=True, help="Skip confirmation prompts")
@click.option(
    "--resource",
    "-r",
    multiple=True,
    help="Specific resource name(s) to target (can be used multiple times)",
)
@with_orchestrator("Destroy failed")
def destroy(
    _ctx: click.Context,
    orchestrator: Orchestrator,
    env: str,
    auto_approve: bool,
    resource: tuple[str, ...],
) -> None:
    """Destroy infrastructure."""

    def confirm_callback() -> bool:
        return click.confirm("Are you sure you want to destroy?")

    orchestrator.destroy(
        env,
        auto_approve=auto_approve,
        resource_filter=list(resource) if resource else None,
        confirm_callback=confirm_callback,
    )
    console.success("Destroy complete!")
