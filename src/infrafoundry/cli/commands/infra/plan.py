"""Plan infrastructure changes command."""

import click

from infrafoundry.core.orchestrator import Orchestrator

from ...decorators import with_orchestrator
from ...utils import console


@click.command()
@click.option("--env", "-e", required=True, help="Environment name (e.g., dev, prod)")
@click.option("--dry-run", is_flag=True, help="Show what would be done without doing it")
@click.option(
    "--resource",
    "-r",
    multiple=True,
    help="Specific resource name(s) to target (can be used multiple times)",
)
@click.option(
    "--enforce-policies",
    is_flag=True,
    help="Enforce policy checks (block on violations)",
)
@with_orchestrator("Plan failed")
def plan(
    _ctx: click.Context,
    orchestrator: Orchestrator,
    env: str,
    dry_run: bool,
    resource: tuple[str, ...],
    enforce_policies: bool,
) -> None:
    """Plan infrastructure changes."""
    orchestrator.plan(
        env,
        dry_run=dry_run,
        resource_filter=list(resource) if resource else None,
        enforce_policies=enforce_policies,
    )

    if dry_run:
        console.info("Dry run complete. No files generated.")
    else:
        console.success("Plan generated successfully!")
        console.info("Generated files are in: generated/")
