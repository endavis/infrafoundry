"""Analyze impact of resource changes command."""

import click

from infrafoundry.core.orchestrator import Orchestrator

from ...decorators import with_orchestrator
from ...output import BULLET
from ...utils import console


@click.command()
@click.option("--env", "-e", required=True, help="Environment name")
@click.option("--resource", "-r", required=True, help="Resource name to analyze")
@with_orchestrator("Impact analysis failed", load_credentials=False)
def impact(_ctx: click.Context, orchestrator: Orchestrator, env: str, resource: str) -> None:
    """Analyze the impact of changes to a resource.

    Shows what other resources depend on the specified resource and the risk level
    of making changes to it.
    """
    # Build dependency graph for the environment
    console.status(f"Analyzing dependencies for {resource} in {env}...")
    graph = orchestrator.build_dependency_graph(env)

    # Get impact analysis
    analysis = graph.get_impact_analysis(f"proxmox:{resource}")

    if not analysis or "error" in analysis:
        console.warning(f"Resource '{resource}' not found in environment '{env}'")
        console.info("\nAvailable resources:")
        for node_name in graph.nodes:
            console.info(f"  {BULLET} {node_name}")
        return

    # Display results
    console.header(f"Impact Analysis for: {resource}")

    console.print("\nRisk Level: ", end="")
    risk_level = analysis["risk_level"]
    if risk_level == "LOW":
        console.success(risk_level)
    elif risk_level == "MEDIUM":
        console.warning(risk_level)
    else:  # HIGH or CRITICAL
        console.error(risk_level)

    console.info(f"Direct Dependents: {analysis['direct_dependents']}")
    console.info(f"Total Affected: {analysis['total_dependents']}")

    if analysis.get("dependent_resources"):
        console.info("\nDependent Resources:")
        for dep in analysis["dependent_resources"]:
            console.info(f"  ↳ {dep}")

    console.info("\nImpact:")
    if analysis["total_dependents"] == 0:
        console.success("No other resources depend on this")
        console.success("Safe to modify or delete")
    elif analysis["risk_level"] == "LOW":
        console.success(f"{analysis['direct_dependents']} resource(s) depend on this")
        console.success("Low risk - safe to change")
    elif analysis["risk_level"] == "MEDIUM":
        console.warning(f"{analysis['total_dependents']} resource(s) may be affected")
        console.warning("Medium risk - review dependencies before changes")
    elif analysis["risk_level"] == "HIGH":
        console.error(f"{analysis['total_dependents']} resource(s) will be affected")
        console.error("High risk - plan changes carefully")
    else:  # CRITICAL
        console.error(f"{analysis['total_dependents']} resource(s) will be affected")
        console.error("Critical risk - changes may cause widespread impact")
