"""Install blueprint requirements command."""

import click
from rich.markup import escape

from infrafoundry.core.orchestrator import Orchestrator

from ...decorators import with_orchestrator
from ...utils import console
from ._common import render_report, resolve_scope, scope_options


@click.command()
@scope_options
@click.option("--dry-run", is_flag=True, help="Print the install commands without running them")
@with_orchestrator("Requirement sync failed", load_credentials=False)
def sync(
    _ctx: click.Context,
    orchestrator: Orchestrator,
    env: str,
    package_name: str | None,
    provider: tuple[str, ...],
    dry_run: bool,
) -> None:
    """Install the unmet requirements of the blueprints in scope.

    Python packages are installed with `uv pip install` into the interpreter
    running foundry; Ansible collections with `ansible-galaxy collection
    install --upgrade`. Re-run this after `uv sync`, which removes packages
    that are not in uv.lock unless run with --inexact.

    Examples:

        foundry deps sync --env prod

        foundry deps sync --env prod --package ontap-cluster --dry-run
    """
    package_filter, provider_filter = resolve_scope(package_name, provider)
    result = orchestrator.requirements_manager.sync(
        env, package_filter, provider_filter, dry_run=dry_run
    )

    if not result.steps:
        render_report(result.report)
        if result.report.statuses:
            console.success("All requirements already met; nothing to install.")
        return

    if result.dry_run:
        console.header(f"Would run for {env}")
        for step in result.steps:
            console.list_item(escape(step.display()))
        return

    console.header(f"Installed for {env}")
    for step in result.steps:
        console.list_item(escape(step.display()))
    render_report(result.report)
    console.success("All requirements met.")
