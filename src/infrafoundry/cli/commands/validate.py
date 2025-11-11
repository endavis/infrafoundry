"""Validate infrastructure configuration command."""

import sys

import click
from rich.console import Console

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
@click.pass_context
def validate(ctx: click.Context, env: str, resource: tuple[str, ...], verbose: bool) -> None:
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
    try:
        # Import helper functions from main module
        from ..main import _get_orchestrator, _load_env_credentials

        # Load environment-specific credentials
        _load_env_credentials(env, ctx.obj.get("config_dir"))

        orchestrator = _get_orchestrator(ctx.obj.get("config_dir"))

        # Convert tuple to list for orchestrator
        resource_filter = list(resource) if resource else None

        # Run validation using orchestrator
        results = orchestrator.validate(
            env_name=env, resource_filter=resource_filter, verbose=verbose
        )

        # Determine exit code based on results
        has_errors = any(r["errors"] > 0 for r in results.values())

        if has_errors:
            sys.exit(1)
        else:
            sys.exit(0)

    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        if verbose:
            import traceback

            console.print(traceback.format_exc())
        sys.exit(1)
