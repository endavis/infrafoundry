"""Detect infrastructure drift command."""

import sys

import click
from rich.console import Console

console = Console()


@click.command()
@click.option("--env", "-e", required=True, help="Environment name")
@click.pass_context
def drift(ctx: click.Context, env: str) -> None:
    """Detect infrastructure drift from declared configuration.

    Checks if actual infrastructure state matches the declared configuration
    by running terraform plan and identifying any unexpected changes.
    """
    from rich.panel import Panel
    from rich.table import Table

    # Import helper functions from main module
    from ..main import _get_orchestrator, _load_env_credentials

    # Load environment-specific credentials
    _load_env_credentials(env, ctx.obj.get("config_dir"))

    orchestrator = _get_orchestrator(ctx.obj.get("config_dir"))

    try:
        # Run drift detection
        results = orchestrator.detect_drift(env)

        # Display detailed results
        console.print("\n")
        console.print(Panel("[bold]Drift Detection Results[/bold]", style="cyan"))

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

                console.print(f"\n[yellow]Summary:[/yellow] {drift_info['summary']}")

        if not total_drift:
            console.print(
                "\n[bold green]✓ No drift detected - "
                "infrastructure matches configuration[/bold green]"
            )
        else:
            console.print("\n[bold yellow]⚠ Drift detected![/bold yellow]")
            console.print(
                "[dim]Run 'infra plan' to see detailed changes, "
                "or 'infra apply' to reconcile.[/dim]"
            )

    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        import traceback

        console.print(traceback.format_exc())
        sys.exit(1)
