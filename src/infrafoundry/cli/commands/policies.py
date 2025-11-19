"""List infrastructure policies command."""

import click
from rich.console import Console
from rich.table import Table

from ..utils import raise_cli_error

console = Console()


@click.command()
@click.option("--env", "-e", help="Show policies for specific environment")
@click.pass_context
def policies(ctx: click.Context, env: str | None) -> None:
    """List available infrastructure policies."""
    try:
        # Import helper function from main module
        from ..main import _get_orchestrator

        orchestrator = _get_orchestrator(ctx.obj.get("config_dir"))

        if env:
            policies_list = orchestrator.policy_engine.get_policies_for_environment(env)
            console.print(f"\n[bold]Policies for {env}:[/bold]")
        else:
            policies_list = orchestrator.policy_engine.policies
            console.print("\n[bold]All Policies:[/bold]")

        if not policies_list:
            console.print("[yellow]No policies found.[/yellow]")
            console.print("[dim]Create policy files in the 'policies' directory.[/dim]")
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
            level_color = {
                "error": "red",
                "warning": "yellow",
                "info": "blue",
            }.get(policy.level.value, "white")

            table.add_row(
                policy.name,
                policy.type.value,
                f"[{level_color}]{policy.level.value}[/{level_color}]",
                "✓" if policy.enabled else "✗",
                ", ".join(policy.environments) if policy.environments else "all",
                policy.description,
            )

        console.print(table)
        console.print(f"\n[dim]Total: {len(policies_list)} policy/policies[/dim]")

    except Exception as exc:
        raise_cli_error("Policy listing failed", exc)
