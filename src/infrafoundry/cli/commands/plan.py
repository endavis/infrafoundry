"""Plan infrastructure changes command."""

import sys

import click
from rich.console import Console

console = Console()


@click.command()
@click.option("--env", "-e", required=True, help="Environment name (e.g., dev, prod)")
@click.option("--dry-run", is_flag=True, help="Show what would be done without doing it")
@click.option(
    "--resource",
    "-r",
    multiple=True,
    help="Specific resource name(s) to target (can be used multiple times)",
)
@click.option(
    "--enforce-policies",
    is_flag=True,
    help="Enforce policy checks (block on violations)",
)
@click.pass_context
def plan(
    ctx: click.Context,
    env: str,
    dry_run: bool,
    resource: tuple[str, ...],
    enforce_policies: bool,
) -> None:
    """Plan infrastructure changes."""
    try:
        # Import helper functions from main module
        from ..main import _get_orchestrator, _load_env_credentials

        # Load environment-specific credentials
        _load_env_credentials(env, ctx.obj.get("config_dir"))

        orchestrator = _get_orchestrator(ctx.obj.get("config_dir"))
        orchestrator.plan(
            env,
            dry_run=dry_run,
            resource_filter=list(resource) if resource else None,
            enforce_policies=enforce_policies,
        )

        if dry_run:
            console.print("\n[bold cyan]Dry run complete. No files generated.[/bold cyan]")
        else:
            console.print("\n[bold green]Plan generated successfully![/bold green]")
            console.print("Generated files are in: [cyan]generated/[/cyan]")

    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        sys.exit(1)
