"""Infra doctor command - Validate infrastructure against provider APIs."""

import sys

import click

from infrafoundry.core.jumphost_preflight import (
    JumphostReport,
    Status,
    check_jumphost,
    deployment_state,
    jumphosts_to_check,
    output_checks,
    targets_by_jumphost,
)
from infrafoundry.core.orchestrator import Orchestrator

from ...decorators import with_orchestrator
from ...utils import console

_STATUS_STYLE = {
    Status.OK: "green",
    Status.WARN: "yellow",
    Status.FAIL: "red",
    Status.SKIP: "dim",
}


@click.command("doctor")
@click.option("--env", "-e", required=True, help="Environment name")
@click.option(
    "--resource",
    "-r",
    multiple=True,
    help="Resource name to validate (can be specified multiple times)",
)
@click.option(
    "--package",
    "-p",
    "package_name",
    help="Validate a specific package by name (mutually exclusive with -r and -P)",
)
@click.option(
    "--provider",
    "-P",
    "provider",
    multiple=True,
    help=(
        "Limit validation to specific provider(s) (can be used multiple times). "
        "Mutually exclusive with --package and --resource."
    ),
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    default=False,
    help="Show detailed validation output including passing checks",
)
@with_orchestrator("Validation failed")
def doctor(
    _ctx: click.Context,
    orchestrator: Orchestrator,
    env: str,
    resource: tuple[str, ...],
    package_name: str | None,
    provider: tuple[str, ...],
    verbose: bool,
) -> None:
    """Validate infrastructure configuration against provider APIs.

    Performs comprehensive pre-flight validation checks:

    \b
    - API connectivity to all providers
    - Nodes/hosts exist and are online
    - Storage pools exist and are active
    - Network bridges are configured
    - Templates/images exist for cloning
    - VMIDs/resource IDs are available
    - No MAC address conflicts
    - Referenced resources exist

    For packages that set ``jumphost``, it also checks the jumphost: SSH
    access, a loaded ssh-agent holding the package's public key, the tools
    the scripts need, a writable /tmp, each VM the scripts will reach (SSH
    if deployed; a route and a free IP if not), and that each ``outputs:``
    destination can be written locally.

    This helps catch configuration errors before attempting deployment.

    Examples:

        # Validate entire environment
        infra doctor --env test

        # Validate specific resources
        infra doctor --env test --resource vm-01 --resource vm-02

        # Validate one package, including its jumphost
        infra doctor --env prod --package k3s-cluster

        # Validate only one provider (repeat -P for more)
        infra doctor --env test --provider opnsense

        # Show detailed output with all passing checks
        infra doctor --env test --verbose
    """
    if provider and (package_name or resource):
        raise click.UsageError("--package, --resource, and --provider are mutually exclusive")
    if package_name and resource:
        raise click.UsageError("--package and --resource are mutually exclusive")
    if package_name:
        resource_filter: list[str] | None = orchestrator.config_manager.resolve_package_filter(
            env, package_name
        )
    else:
        resource_filter = list(resource) if resource else None

    provider_filter: list[str] | None = list(provider) if provider else None
    # Only pass the filter when set, so unfiltered calls keep their original signature.
    extra: dict[str, list[str]] = {"provider_filter": provider_filter} if provider_filter else {}

    results = orchestrator.validate(
        env_name=env,
        resource_filter=resource_filter,
        verbose=verbose,
        **extra,
    )

    has_errors = any(r["errors"] > 0 for r in results.values())
    if _jumphost_preflight(orchestrator, env, resource_filter, provider_filter):
        has_errors = True
    if has_errors:
        sys.exit(1)
    sys.exit(0)


def _jumphost_preflight(
    orchestrator: Orchestrator,
    env: str,
    resource_filter: list[str] | None,
    provider_filter: list[str] | None = None,
) -> bool:
    """Check every jumphost the in-scope packages use; return whether any check failed."""
    config_manager = orchestrator.config_manager
    all_resources = config_manager.get_all_resources_all_providers(env)
    handlers = [h for hs in config_manager.get_package_events().values() for h in hs]
    resources = all_resources
    if resource_filter is not None:
        wanted = set(resource_filter)
        resources = [r for r in all_resources if r.name in wanted]
    if provider_filter is not None:
        selected = set(provider_filter)
        resources = [r for r in resources if r.provider in selected]

    targets = targets_by_jumphost(
        resources, all_resources, deployment_state(orchestrator.state_manager, env)
    )
    outputs = output_checks(handlers, resources)
    failed = False
    for jumphost, keys in jumphosts_to_check(resources).items():
        report = check_jumphost(jumphost, keys, targets.get(jumphost, []))
        report.checks.extend(outputs.get(jumphost, []))
        _print_report(report)
        failed = failed or report.failed
    return failed


def _print_report(report: JumphostReport) -> None:
    console.print(f"\n[bold]Jumphost preflight ({report.jumphost}):[/bold]")
    for check in report.checks:
        style = _STATUS_STYLE[check.status]
        detail = f": {check.detail}" if check.detail else ""
        console.print(
            f"  [{style}]\\[{check.status.value}][/{style}] {check.name}{detail}",
            highlight=False,
        )
    counts = {s: sum(c.status is s for c in report.checks) for s in Status}
    summary = ", ".join(f"{n} {s.value}" for s, n in counts.items() if n)
    console.print(f"Jumphost preflight: {summary}")
