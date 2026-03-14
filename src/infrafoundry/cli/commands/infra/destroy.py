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
@click.option(
    "--package",
    "-p",
    "package_name",
    help="Target a specific package by name (mutually exclusive with -r)",
)
@with_orchestrator("Destroy failed")
def destroy(
    _ctx: click.Context,
    orchestrator: Orchestrator,
    env: str,
    auto_approve: bool,
    resource: tuple[str, ...],
    package_name: str | None,
) -> None:
    """Destroy infrastructure."""
    if package_name and resource:
        raise click.UsageError("--package and --resource are mutually exclusive")

    resource_filter: list[str] | None = None
    if package_name:
        resource_filter = orchestrator.config_manager.resolve_package_filter(env, package_name)
    elif resource:
        resource_filter = list(resource)

    if not auto_approve:
        if package_name:
            resource_desc = f" (package: {package_name})"
        elif resource:
            resource_desc = f" (resources: {', '.join(resource)})"
        else:
            resource_desc = ""
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
            resource_filter=resource_filter,
        )
    console.success(f"Destroy complete! ({timer.elapsed_str})")
