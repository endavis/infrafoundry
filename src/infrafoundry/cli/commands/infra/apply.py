"""Apply infrastructure changes command."""

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
@click.option(
    "--parallel",
    is_flag=True,
    help="Apply providers in parallel (experimental)",
)
@click.option(
    "--max-workers",
    type=int,
    default=4,
    help="Maximum number of parallel workers (default: 4)",
)
@with_orchestrator("Apply failed")
def apply(
    _ctx: click.Context,
    orchestrator: Orchestrator,
    env: str,
    auto_approve: bool,
    resource: tuple[str, ...],
    parallel: bool,
    max_workers: int,
) -> None:
    """Apply infrastructure changes."""
    # If not auto-approve, ask for confirmation at InfraFoundry level
    if not auto_approve:
        resource_desc = f" (resources: {', '.join(resource)})" if resource else ""
        console.warning(f"About to apply infrastructure for environment: {env}{resource_desc}")
        console.warning("This will make real changes to your infrastructure.")

        if not click.confirm("Do you want to continue?", default=False):
            console.warning("Apply cancelled.")
            return

        # User confirmed, so pass auto_approve=True to Terraform
        auto_approve = True

    with OperationTimer() as timer:
        orchestrator.apply(
            env,
            auto_approve=auto_approve,
            resource_filter=list(resource) if resource else None,
            parallel=parallel,
            max_workers=max_workers,
        )
    console.success(f"Apply complete! ({timer.elapsed_str})")
