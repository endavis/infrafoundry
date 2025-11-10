"""Show infrastructure status command."""

import sys

import click
from rich.console import Console

console = Console()


@click.command()
@click.option("--env", "-e", required=True, help="Environment name")
@click.pass_context
def status(ctx: click.Context, env: str) -> None:
    """Show infrastructure status."""
    try:
        # Import helper functions from main module
        from ..main import _get_orchestrator, _load_env_credentials

        # Load environment-specific credentials
        _load_env_credentials(env, ctx.obj.get("config_dir"))

        orchestrator = _get_orchestrator(ctx.obj.get("config_dir"))
        orchestrator.status(env)
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        sys.exit(1)
