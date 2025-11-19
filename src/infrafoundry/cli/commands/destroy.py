"""Destroy infrastructure command."""

import click
from rich.console import Console

from ..utils import raise_cli_error

console = Console()


@click.command()
@click.option("--env", "-e", required=True, help="Environment name")
@click.option("--auto-approve", is_flag=True, help="Skip confirmation prompts")
@click.option(
    "--resource",
    "-r",
    multiple=True,
    help="Specific resource name(s) to target (can be used multiple times)",
)
@click.pass_context
def destroy(ctx: click.Context, env: str, auto_approve: bool, resource: tuple[str, ...]) -> None:
    """Destroy infrastructure."""
    try:
        # Import helper functions from main module
        from ..main import _get_orchestrator, _load_env_credentials

        # Load environment-specific credentials
        _load_env_credentials(env, ctx.obj.get("config_dir"))

        orchestrator = _get_orchestrator(ctx.obj.get("config_dir"))
        orchestrator.destroy(
            env, auto_approve=auto_approve, resource_filter=list(resource) if resource else None
        )
        console.print("\n[bold green]Destroy complete![/bold green]")
    except Exception as exc:
        raise_cli_error("Destroy failed", exc)
