"""Back up the configuration of unmanaged network devices (read-only)."""

from __future__ import annotations

import click

from infrafoundry.collectors.runner import collect_environment
from infrafoundry.core.orchestrator import Orchestrator

from ...decorators import with_orchestrator
from ...utils import console


@click.command()
@click.option("--env", "-e", required=True, help="Environment name (e.g., dev, prod)")
@click.option(
    "--device",
    "-d",
    "device",
    multiple=True,
    help="Collect only this device (can be used multiple times)",
)
@with_orchestrator("Collect failed", load_credentials=False)
def collect(
    _ctx: click.Context, orchestrator: Orchestrator, env: str, device: tuple[str, ...]
) -> None:
    """Collect device configs into the config repo (never writes to a device)."""
    report = collect_environment(orchestrator.config_manager, env, tuple(device))
    for result in report.results:
        if result.error:
            continue
        changes = [c for c in result.changes if c.status != "unchanged"]
        if not changes:
            console.info(f"{result.name}: no changes")
        for change in changes:
            console.info(f"{change.status}: {result.name}/{change.path.name}")
    if not report.changed and not report.failed:
        console.info("No changes.")
    for result in report.failed:
        console.error(f"{result.name}: {result.error}")
    if report.failed:
        raise click.ClickException(f"{len(report.failed)} device(s) failed")
