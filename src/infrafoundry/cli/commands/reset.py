"""Reset infrastructure components command."""

import click
from rich.console import Console

from ..utils import raise_cli_error

console = Console()


@click.command()
@click.option("--env", "-e", required=True, help="Environment name")
@click.option(
    "--provider",
    "-p",
    required=True,
    type=click.Choice(["opnsense"], case_sensitive=False),
    help="Provider name",
)
@click.option(
    "--component",
    "-c",
    required=True,
    type=click.Choice(["kea/dhcpv4", "kea/dhcpv6", "kea/dhcp"], case_sensitive=False),
    help="Component to reset (kea/dhcp resets both v4 and v6)",
)
@click.option("--auto-approve", is_flag=True, help="Skip confirmation prompts")
@click.pass_context
def reset(
    ctx: click.Context,
    env: str,
    provider: str,
    component: str,
    auto_approve: bool,
) -> None:
    """Reset (wipe) infrastructure components.

    This command completely removes the specified component configuration
    from the provider, allowing a clean reapply.

    Examples:
        infra reset --env prod --provider opnsense --component kea/dhcpv4
        infra reset --env prod --provider opnsense --component kea/dhcp --auto-approve
    """
    try:
        # Import helper functions from main module
        from ..main import _get_orchestrator, _load_env_credentials

        # Load environment-specific credentials
        _load_env_credentials(env, ctx.obj.get("config_dir"))

        orchestrator = _get_orchestrator(ctx.obj.get("config_dir"))

        # Get the provider instance
        if provider.lower() == "opnsense":
            from infrafoundry.providers.opnsense import OPNsenseProvider

            # Get provider from orchestrator (providers is a dict)
            provider_instance = orchestrator.providers.get("opnsense")

            if not provider_instance or not isinstance(provider_instance, OPNsenseProvider):
                raise click.ClickException("OPNsense provider not found")

            # Set the current environment on the provider
            provider_instance._current_environment = env

            # Confirm action
            if not auto_approve:
                component_desc = component.upper()
                console.print(
                    f"\n[bold yellow]Warning:[/bold yellow] This will completely "
                    f"remove all {component_desc} configuration from OPNsense."
                )
                console.print(
                    "[yellow]All subnets, reservations, and settings will be deleted.[/yellow]"
                )
                if not click.confirm("\nDo you want to continue?", default=False):
                    console.print("[yellow]Reset cancelled.[/yellow]")
                    return

            # Execute reset based on component
            if component.lower() in ["kea/dhcpv4", "kea/dhcp"]:
                console.print("[cyan]Resetting Kea DHCPv4 configuration...[/cyan]")
                provider_instance.reset_kea_dhcpv4(env)
                console.print("[green]✓ Kea DHCPv4 reset complete[/green]")

            if component.lower() in ["kea/dhcpv6", "kea/dhcp"]:
                console.print("[cyan]Resetting Kea DHCPv6 configuration...[/cyan]")
                provider_instance.reset_kea_dhcpv6(env)
                console.print("[green]✓ Kea DHCPv6 reset complete[/green]")

            console.print("\n[bold green]Reset complete![/bold green]")
            console.print(
                "\n[cyan]You can now run 'infra apply' to apply fresh configuration.[/cyan]"
            )

        else:
            raise click.ClickException(f"Unsupported provider: {provider}")

    except Exception as exc:
        raise_cli_error("Reset command failed", exc)
