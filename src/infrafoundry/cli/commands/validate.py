"""Validate infrastructure configuration command."""

import sys

import click
from rich.console import Console

from ..decorators import with_orchestrator

console = Console()


@click.command()
@click.option("--env", "-e", required=True, help="Environment name")
@click.option(
    "--resource",
    "-r",
    multiple=True,
    help="Resource name to validate (can be specified multiple times)",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    default=False,
    help="Show detailed validation output including passing checks",
)
@with_orchestrator("Validation failed")
def validate(
    _ctx: click.Context,
    orchestrator,
    env: str,
    resource: tuple[str, ...],
    verbose: bool,
) -> None:
    """Validate infrastructure configuration against provider APIs.

    Performs comprehensive pre-flight validation checks:

    \b
    - API connectivity to all providers
    - Nodes/hosts exist and are online
    - Storage pools exist and are active
    - Network bridges are configured
    - Templates/images exist for cloning
    - VMIDs/resource IDs are available
    - No MAC address conflicts
    - Referenced resources exist

    This helps catch configuration errors before attempting deployment.

    Examples:

        # Validate entire environment
        infra validate --env test

        # Validate specific resources
        infra validate --env test --resource vm-01 --resource vm-02

        # Show detailed output with all passing checks
        infra validate --env test --verbose
    """
    resource_filter = list(resource) if resource else None

    results = orchestrator.validate(
        env_name=env,
        resource_filter=resource_filter,
        verbose=verbose,
    )

    has_errors = any(r["errors"] > 0 for r in results.values())
    if has_errors:
        sys.exit(1)
    sys.exit(0)
