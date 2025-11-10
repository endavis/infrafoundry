"""Analyze impact of resource changes command."""

import sys

import click
from rich.console import Console
from rich.panel import Panel

console = Console()


@click.command()
@click.option("--env", "-e", required=True, help="Environment name")
@click.option("--resource", "-r", required=True, help="Resource name to analyze")
def impact(env: str, resource: str) -> None:
    """Analyze the impact of changes to a resource.

    Shows what other resources depend on the specified resource and the risk level
    of making changes to it.
    """
    # Import helper function from main module
    from ..main import _get_orchestrator

    orchestrator = _get_orchestrator()

    try:
        # Build dependency graph for the environment
        console.print(f"[dim]Analyzing dependencies for {resource} in {env}...[/dim]\n")
        graph = orchestrator.build_dependency_graph(env)

        # Get impact analysis
        analysis = graph.get_impact_analysis(f"proxmox:{resource}")

        if not analysis or "error" in analysis:
            console.print(
                f"[yellow]Resource '{resource}' not found in environment '{env}'[/yellow]"
            )
            console.print("\n[dim]Available resources:[/dim]")
            for node_name in graph.nodes.keys():
                console.print(f"  - {node_name}")
            return

        # Display results
        console.print(
            Panel(
                f"[bold]Impact Analysis for: {resource}[/bold]",
                style="cyan",
            )
        )

        console.print("\n[bold]Risk Level:[/bold] ", end="")
        risk_color = {
            "LOW": "green",
            "MEDIUM": "yellow",
            "HIGH": "orange1",
            "CRITICAL": "red",
        }.get(analysis["risk_level"], "white")
        console.print(f"[{risk_color}]{analysis['risk_level']}[/{risk_color}]")

        console.print(f"[bold]Direct Dependents:[/bold] {analysis['direct_dependents']}")
        console.print(f"[bold]Total Affected:[/bold] {analysis['total_dependents']}")

        if analysis.get("dependent_resources"):
            console.print("\n[bold]Dependent Resources:[/bold]")
            for dep in analysis["dependent_resources"]:
                console.print(f"  ↳ {dep}")

        console.print("\n[bold]Impact:[/bold]")
        if analysis["total_dependents"] == 0:
            console.print("  [green]✓ No other resources depend on this[/green]")
            console.print("  [green]  Safe to modify or delete[/green]")
        elif analysis["risk_level"] == "LOW":
            console.print(
                f"  [green]✓ {analysis['direct_dependents']} resource(s) depend on this[/green]"
            )
            console.print("  [green]  Low risk - safe to change[/green]")
        elif analysis["risk_level"] == "MEDIUM":
            console.print(
                f"  [yellow]⚠ {analysis['total_dependents']} resource(s) may be affected[/yellow]"
            )
            console.print("  [yellow]  Medium risk - review dependencies before changes[/yellow]")
        elif analysis["risk_level"] == "HIGH":
            console.print(
                f"  [red]⚠ {analysis['total_dependents']} resource(s) will be affected[/red]"
            )
            console.print("  [red]  High risk - plan changes carefully[/red]")
        else:  # CRITICAL
            console.print(
                f"  [bold red]⛔ {analysis['total_dependents']} resource(s) "
                "will be affected[/bold red]"
            )
            console.print(
                "  [bold red]  Critical risk - changes may cause widespread impact[/bold red]"
            )

    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
