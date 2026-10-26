"""Check blueprint requirements command."""

import sys

import click

from infrafoundry.core.orchestrator import Orchestrator

from ...decorators import with_orchestrator
from ...utils import console
from ._common import render_report, resolve_scope, scope_options


@click.command()
@scope_options
@with_orchestrator("Requirement check failed", load_credentials=False)
def check(
    _ctx: click.Context,
    orchestrator: Orchestrator,
    env: str,
    package_name: str | None,
    provider: tuple[str, ...],
) -> None:
    """Check that the blueprints in scope have their requirements installed.

    Runs the same check as the preflight in infra plan/apply/destroy. Exits 1
    when any requirement is unmet.

    Examples:

        foundry deps check --env prod

        foundry deps check --env prod --package ontap-cluster
    """
    package_filter, provider_filter = resolve_scope(package_name, provider)
    report = orchestrator.requirements_manager.check(env, package_filter, provider_filter)

    console.header(f"Blueprint requirements for {env}")
    render_report(report)
    if report.unmet:
        console.error(f"{len(report.unmet)} of {len(report.statuses)} requirement(s) unmet.")
        console.info(f"Install them with: foundry deps sync --env {env}")
        sys.exit(1)
    if report.statuses:
        console.success(f"All {len(report.statuses)} requirement(s) met.")
