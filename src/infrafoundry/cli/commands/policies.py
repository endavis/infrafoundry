"""List infrastructure policies command."""

import click
from rich.table import Table

from infrafoundry.core.orchestrator import Orchestrator

from ..decorators import with_orchestrator
from ..utils import console


@click.command()
@click.option("--env", "-e", help="Show policies for specific environment")
@with_orchestrator("Policy listing failed", require_env=False, load_credentials=False)
def policies(_ctx: click.Context, orchestrator: Orchestrator, env: str | None) -> None:
    """List available infrastructure policies."""
    if env:
        policies_list = orchestrator.policy_engine.get_policies_for_environment(env)
        console.header(f"Policies for {env}")
    else:
        policies_list = orchestrator.policy_engine.policies
        console.header("All Policies")

    if not policies_list:
        console.warning("No policies found.")
        console.info("Create policy files in the 'policies' directory.")
        return

    # Display policies in a table
    table = Table(show_header=True)
    table.add_column("Name", style="cyan")
    table.add_column("Type", style="blue")
    table.add_column("Level", style="yellow")
    table.add_column("Enabled", style="green")
    table.add_column("Environments", style="magenta")
    table.add_column("Description", style="dim")

    for policy in policies_list:
        table.add_row(
            policy.name,
            policy.type.value,
            policy.level.value,
            "✓" if policy.enabled else "✗",
            ", ".join(policy.environments) if policy.environments else "all",
            policy.description,
        )

    console.print(table)
    console.info(f"Total: {len(policies_list)} policy/policies")
