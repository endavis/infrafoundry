"""Infra doctor command - Validate infrastructure against provider APIs."""

import contextlib
import sys
from typing import Any

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
from infrafoundry.core.provider import ResourceConfig

from ...decorators import with_orchestrator
from ...output import output_data
from ...utils import console
from ._firewall import CLUSTER_HELP, FIREWALL_HELP, expand_provider_filter
from ._secret_sources import (
    SecretSourceRow,
    SourceStatus,
    collect_secret_sources,
    print_secret_sources,
    secret_sources_json,
)

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
    "--firewall",
    "firewall",
    multiple=True,
    help=FIREWALL_HELP,
)
@click.option(
    "--cluster",
    "cluster",
    multiple=True,
    help=CLUSTER_HELP,
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    default=False,
    help="Show detailed validation output including passing checks",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format (default: text). json sends the text report to stderr.",
)
@with_orchestrator("Validation failed")
def doctor(
    _ctx: click.Context,
    orchestrator: Orchestrator,
    env: str,
    resource: tuple[str, ...],
    package_name: str | None,
    provider: tuple[str, ...],
    firewall: tuple[str, ...],
    cluster: tuple[str, ...],
    verbose: bool,
    output_format: str,
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

    With ``--package`` or ``--resource`` it also lists where each secret reference
    of the in-scope resources resolves from (package secrets.yaml, another provider's
    outputs, or the environment's secrets.yaml) and fails on any that does not. Values
    are never shown. ``--format json`` prints one JSON document on stdout and sends
    the text report to stderr.

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

        # Machine-readable result
        infra doctor --env test --package k3s-cluster --format json
    """
    if (provider or firewall or cluster) and (package_name or resource):
        raise click.UsageError("--package, --resource, and --provider are mutually exclusive")
    if package_name and resource:
        raise click.UsageError("--package and --resource are mutually exclusive")
    if package_name:
        resource_filter: list[str] | None = orchestrator.config_manager.resolve_package_filter(
            env, package_name
        )
    else:
        resource_filter = list(resource) if resource else None

    provider_filter = expand_provider_filter(
        orchestrator, env, provider, firewall, clusters=cluster
    )
    # Only pass the filter when set, so unfiltered calls keep their original signature.
    extra: dict[str, list[str]] = {"provider_filter": provider_filter} if provider_filter else {}

    as_json = output_format == "json"
    # JSON mode keeps stdout for the one document; the text report goes to stderr.
    text_out = contextlib.redirect_stdout(sys.stderr) if as_json else contextlib.nullcontext()
    with text_out:
        results = orchestrator.validate(
            env_name=env,
            resource_filter=resource_filter,
            verbose=verbose,
            **extra,
        )

        has_errors = any(r["errors"] > 0 for r in results.values())
        if _jumphost_preflight(orchestrator, env, resource_filter, provider_filter):
            has_errors = True
        secret_rows: list[SecretSourceRow] | None = None
        if resource_filter is not None:
            scope = (
                f"package {package_name}" if package_name else f"resource(s) {', '.join(resource)}"
            )
            secret_rows = _secret_sources(orchestrator, env, resource_filter, scope)
            if any(r.status is SourceStatus.UNRESOLVED for r in secret_rows):
                has_errors = True
    if as_json:
        data: dict[str, Any] = {
            "environment": env,
            "passed": not has_errors,
            "providers": {
                name: {"errors": r["errors"], "warnings": r["warnings"]}
                for name, r in results.items()
            },
            "secret_sources": (
                secret_sources_json(secret_rows, scope) if secret_rows is not None else None
            ),
        }
        output_data(data, "json")
    if has_errors:
        sys.exit(1)
    sys.exit(0)


def _secret_sources(
    orchestrator: Orchestrator,
    env: str,
    resource_filter: list[str],
    scope: str,
) -> list[SecretSourceRow]:
    """Collect and print the secret sources of the in-scope resources."""
    config_manager = orchestrator.config_manager
    wanted = set(resource_filter)
    resources: list[ResourceConfig] = [
        r for r in config_manager.get_all_resources_all_providers(env) if r.name in wanted
    ]
    rows = collect_secret_sources(
        resources, env, lambda: config_manager.load_environment(env).secrets
    )
    print_secret_sources(rows, scope)
    return rows


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
