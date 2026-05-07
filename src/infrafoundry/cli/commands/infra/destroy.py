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
    help="Target a specific package by name (mutually exclusive with -r and -P)",
)
@click.option(
    "--provider",
    "-P",
    "provider",
    multiple=True,
    help=(
        "Limit operation to specific provider(s) (can be used multiple times). "
        "Mutually exclusive with --package and --resource. Cross-provider "
        "dependencies pointing at filtered-out providers are silently skipped "
        "for this run."
    ),
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
@with_orchestrator("Destroy failed")
def destroy(
    _ctx: click.Context,
    orchestrator: Orchestrator,
    env: str,
    auto_approve: bool,
    resource: tuple[str, ...],
    package_name: str | None,
    provider: tuple[str, ...],
    lock_timeout: int,
    lock_ttl: int,
) -> None:
    """Destroy infrastructure."""
    if sum(bool(x) for x in (package_name, resource, provider)) > 1:
        raise click.UsageError("--package, --resource, and --provider are mutually exclusive")

    resource_filter: list[str] | None = None
    if package_name:
        resource_filter = orchestrator.config_manager.resolve_package_filter(env, package_name)
    elif resource:
        resource_filter = list(resource)

    provider_filter: list[str] | None = list(provider) if provider else None

    if not auto_approve:
        if package_name:
            resource_desc = f" (package: {package_name})"
        elif resource:
            resource_desc = f" (resources: {', '.join(resource)})"
        elif provider:
            resource_desc = f" (providers: {', '.join(provider)})"
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
            package_filter=package_name,
            lock_timeout=lock_timeout,
            lock_ttl=lock_ttl,
            provider_filter=provider_filter,
        )
    console.success(f"Destroy complete! ({timer.elapsed_str})")
