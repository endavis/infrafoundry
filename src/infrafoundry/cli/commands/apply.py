"""Apply infrastructure changes command."""

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
@click.option(
    "--parallel",
    is_flag=True,
    help="Apply providers in parallel (experimental)",
)
@click.option(
    "--max-workers",
    type=int,
    default=4,
    help="Maximum number of parallel workers (default: 4)",
)
@click.pass_context
def apply(
    ctx: click.Context,
    env: str,
    auto_approve: bool,
    resource: tuple[str, ...],
    parallel: bool,
    max_workers: int,
) -> None:
    """Apply infrastructure changes."""
    try:
        # Import helper functions from main module
        from ..main import _get_orchestrator, _load_env_credentials

        # Load environment-specific credentials
        _load_env_credentials(env, ctx.obj.get("config_dir"))

        orchestrator = _get_orchestrator(ctx.obj.get("config_dir"))

        # If not auto-approve, ask for confirmation at InfraFoundry level
        if not auto_approve:
            resource_desc = f" (resources: {', '.join(resource)})" if resource else ""
            console.print(
                f"\n[yellow]About to apply infrastructure for environment: "
                f"{env}{resource_desc}[/yellow]"
            )
            console.print("[yellow]This will make real changes to your infrastructure.[/yellow]")

            if not click.confirm("Do you want to continue?", default=False):
                console.print("[yellow]Apply cancelled.[/yellow]")
                return

            # User confirmed, so pass auto_approve=True to Terraform
            auto_approve = True

        orchestrator.apply(
            env,
            auto_approve=auto_approve,
            resource_filter=list(resource) if resource else None,
            parallel=parallel,
            max_workers=max_workers,
        )
        console.print("\n[bold green]Apply complete![/bold green]")
    except Exception as exc:
        raise_cli_error("Apply failed", exc)
