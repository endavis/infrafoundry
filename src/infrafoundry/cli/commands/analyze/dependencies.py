"""Visualize resource dependencies for an environment."""

import click

from infrafoundry.core.orchestrator import Orchestrator

from ...decorators import with_orchestrator
from ...utils import console


@click.command(name="dependencies")
@click.option("--env", "-e", required=True, help="Environment name")
@click.option(
    "--resource",
    "-r",
    help="Specific resource to analyze (provider:name). If omitted, full graph is shown.",
)
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["list", "mermaid"], case_sensitive=False),
    default="list",
    show_default=True,
    help="Output format",
)
@with_orchestrator("Dependency analysis failed")
def dependencies(
    _ctx: click.Context,
    orchestrator: Orchestrator,
    env: str,
    resource: str | None,
    fmt: str,
) -> None:
    """Show dependency graph or impact analysis."""
    graph = orchestrator.build_dependency_graph(env)

    if resource:
        dependents = sorted(graph.get_all_dependents(resource))
        dependencies = sorted(graph.get_all_dependencies(resource))

        console.header(f"Dependency analysis for {resource}")
        if dependencies:
            console.info("Depends on:")
            for dep in dependencies:
                console.info(f"  • {dep}")
        else:
            console.info("Depends on: none")

        if dependents:
            console.info("Required by:")
            for dep in dependents:
                console.info(f"  • {dep}")
        else:
            console.info("Required by: none")
        return

    if fmt == "mermaid":
        console.print(graph.export_to_mermaid())
        return

    console.header(f"Dependencies for {env}")
    batches = graph.get_execution_batches()
    for idx, batch in enumerate(batches, start=1):
        console.info(f"Batch {idx}:")
        for res in batch:
            console.info(f"  • {res}")
