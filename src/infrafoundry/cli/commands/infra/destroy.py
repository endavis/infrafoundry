"""Destroy infrastructure command."""

import click

from infrafoundry.core.orchestrator import Orchestrator

from ...decorators import with_orchestrator
from ...progress import OperationTimer
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

    if not auto_approve:
        resource_desc = f" (resources: {', '.join(resource)})" if resource else ""
        console.warning(f"About to DESTROY infrastructure for environment: {env}{resource_desc}")
        console.warning("This will permanently remove resources from your infrastructure.")

        if not click.confirm("Are you sure you want to destroy?", default=False):
            console.warning("Destroy cancelled.")
            return

        # User confirmed, so pass auto_approve=True to Terraform
        auto_approve = True

    with OperationTimer() as timer:
        orchestrator.destroy(
            env,
            auto_approve=auto_approve,
            resource_filter=list(resource) if resource else None,
        )
    console.success(f"Destroy complete! ({timer.elapsed_str})")
