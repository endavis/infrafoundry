"""List resources in an environment command."""

import click
from rich.console import Console

from infrafoundry.core.config import ConfigManager

from ..utils import raise_cli_error

console = Console()


@click.command(name="list")
@click.option("--env", "-e", required=True, help="Environment name")
@click.option("--provider", "-p", help="Filter by provider (e.g., proxmox, opnsense)")
@click.option("--type", "-t", help="Filter by resource type (e.g., vms, firewall_rules)")
@click.pass_context
def list_resources(ctx: click.Context, env: str, provider: str | None, type: str | None) -> None:
    """List all resources in an environment."""
    try:
        config_repo = ctx.obj.get("config_dir")
        if config_repo:
            config_manager = ConfigManager(base_dir=config_repo / "envs")
        else:
            config_manager = ConfigManager()

        # Get all resources from all providers (handles both formats)
        all_resources = config_manager.get_all_resources_all_providers(env)

        # Apply filters
        if provider:
            all_resources = [r for r in all_resources if r.provider == provider]
        if type:
            all_resources = [r for r in all_resources if r.type == type]

        if not all_resources:
            if type and provider:
                console.print(
                    f"[yellow]No resources found with provider '{provider}' "
                    f"and type '{type}'[/yellow]"
                )
            elif type:
                console.print(f"[yellow]No resources found with type '{type}'[/yellow]")
            elif provider:
                console.print(f"[yellow]No resources found with provider '{provider}'[/yellow]")
            else:
                console.print("[yellow]No resources found[/yellow]")
            return

        console.print(f"[bold cyan]Resources in {env}:[/bold cyan]\n")

        # Sort all resources by name
        all_resources.sort(key=lambda r: r.name)

        # Display each resource on a single line
        for resource in all_resources:
            console.print(
                f"  • {resource.name:<40} [bold]{resource.provider:<12}[/bold] "
                f"[dim]({resource.type})[/dim]"
            )

        console.print(f"\n[dim]Total: {len(all_resources)} resources[/dim]")

    except Exception as exc:
        raise_cli_error("Failed to list resources", exc)
