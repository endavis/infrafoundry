"""Plan infrastructure changes command."""

import click

from infrafoundry.core.orchestrator import Orchestrator

from ...decorators import with_orchestrator
from ...progress import OperationTimer
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
    "--package",
    "-p",
    "package_name",
    help="Target a specific package by name (mutually exclusive with -r)",
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
    package_name: str | None,
    enforce_policies: bool,
) -> None:
    """Plan infrastructure changes."""
    if package_name and resource:
        raise click.UsageError("--package and --resource are mutually exclusive")

    resource_filter: list[str] | None = None
    if package_name:
        resource_filter = orchestrator.config_manager.resolve_package_filter(env, package_name)
    elif resource:
        resource_filter = list(resource)

    with OperationTimer() as timer:
        orchestrator.plan(
            env,
            dry_run=dry_run,
            resource_filter=resource_filter,
            enforce_policies=enforce_policies,
        )

    if dry_run:
        console.info(f"Dry run complete. No files generated. ({timer.elapsed_str})")
    else:
        console.success(f"Plan generated successfully! ({timer.elapsed_str})")
        console.info("Generated files are in: generated/")
