"""Graph command to visualize infrastructure dependencies."""

import click
from rich.console import Console
from rich.syntax import Syntax

from infrafoundry.core.orchestrator import Orchestrator

from ..decorators import with_orchestrator

console = Console()


@click.command()
@click.option("--env", "-e", required=True, help="Environment name")
@click.option(
    "--format",
    "-f",
    type=click.Choice(["mermaid"]),
    default="mermaid",
    help="Output format (currently only mermaid supported)",
)
@with_orchestrator("Graph generation failed")
def graph(
    _ctx: click.Context,
    orchestrator: Orchestrator,
    env: str,
    format: str,
) -> None:
    """Visualize infrastructure dependencies."""
    dependency_graph = orchestrator.build_dependency_graph(env)

    if format == "mermaid":
        output = dependency_graph.export_to_mermaid()
        console.print(Syntax(output, "mermaid", theme="monokai", word_wrap=True))
    else:
        console.print(f"[red]Unsupported format: {format}[/red]")
