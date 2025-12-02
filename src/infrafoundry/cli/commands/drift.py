"""Detect infrastructure drift command."""

import click
from rich.table import Table

from infrafoundry.core.orchestrator import Orchestrator

from ..decorators import with_orchestrator
from ..utils import console


@click.command()
@click.option("--env", "-e", required=True, help="Environment name")
@with_orchestrator("Drift command failed")
def drift(_ctx: click.Context, orchestrator: Orchestrator, env: str) -> None:
    """Detect infrastructure drift from declared configuration.

    Checks if actual infrastructure state matches the declared configuration
    by running terraform plan and identifying any unexpected changes.
    """
    # Run drift detection
    results = orchestrator.detect_drift(env)

    # Display detailed results
    console.info("")
    console.header("Drift Detection Results")

    total_drift = False
    for provider_name, drift_info in results.items():
        if drift_info.get("has_changes"):
            total_drift = True

            table = Table(title=f"{provider_name.title()} Drift")
            table.add_column("Change Type", style="cyan")
            table.add_column("Count", style="yellow")

            if drift_info.get("to_add", 0) > 0:
                table.add_row("To Add", str(drift_info["to_add"]))
            if drift_info.get("to_change", 0) > 0:
                table.add_row("To Change", str(drift_info["to_change"]))
            if drift_info.get("to_destroy", 0) > 0:
                table.add_row("To Destroy", str(drift_info["to_destroy"]))

            console.print(table)

            console.warning(f"Summary: {drift_info['summary']}")

    if not total_drift:
        console.success("No drift detected - infrastructure matches configuration")
    else:
        console.warning("Drift detected!")
        console.status("Run 'infra plan' to see detailed changes, or 'infra apply' to reconcile.")
