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
    "--package",
    "-p",
    "package_name",
    help="Target a specific package by name (mutually exclusive with -r)",
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
@click.option(
    "--lock-timeout",
    type=int,
    default=0,
    help="Seconds to wait for the environment lock before failing (0 = fail fast).",
)
@click.option(
    "--lock-ttl",
    type=int,
    default=600,
    help=(
        "Lock TTL in seconds. The lock is auto-extended while the process "
        "runs; this only governs stale-lock recovery after a crash "
        "(default: 600)."
    ),
)
@click.option(
    "--add-only",
    is_flag=True,
    help=(
        "Suppress deletes for live resources not in YAML. Useful for partial "
        "migrations where the YAML doesn't yet describe everything on the box. "
        "Currently honored by OPNsense direct-API resources only; other "
        "runners accept and ignore."
    ),
)
@with_orchestrator("Apply failed")
def apply(
    _ctx: click.Context,
    orchestrator: Orchestrator,
    env: str,
    auto_approve: bool,
    resource: tuple[str, ...],
    package_name: str | None,
    parallel: bool,
    max_workers: int,
    lock_timeout: int,
    lock_ttl: int,
    add_only: bool,
) -> None:
    """Apply infrastructure changes."""
    if package_name and resource:
        raise click.UsageError("--package and --resource are mutually exclusive")

    resource_filter: list[str] | None = None
    if package_name:
        resource_filter = orchestrator.config_manager.resolve_package_filter(env, package_name)
    elif resource:
        resource_filter = list(resource)

    # If not auto-approve, ask for confirmation at InfraFoundry level
    if not auto_approve:
        if package_name:
            resource_desc = f" (package: {package_name})"
        elif resource:
            resource_desc = f" (resources: {', '.join(resource)})"
        else:
            resource_desc = ""
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
            resource_filter=resource_filter,
            parallel=parallel,
            max_workers=max_workers,
            package_filter=package_name,
            lock_timeout=lock_timeout,
            lock_ttl=lock_ttl,
            add_only=add_only,
        )
    console.success(f"Apply complete! ({timer.elapsed_str})")
