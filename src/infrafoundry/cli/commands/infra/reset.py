"""Reset infrastructure components command."""

import click

from infrafoundry.core.orchestrator import Orchestrator

from ...decorators import with_orchestrator
from ...utils import console


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
@with_orchestrator("Reset command failed")
def reset(
    _ctx: click.Context,
    orchestrator: Orchestrator,
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
    if provider.lower() != "opnsense":
        raise click.ClickException(f"Unsupported provider: {provider}")

    from infrafoundry.providers.opnsense import OPNsenseProvider

    provider_instance = orchestrator.providers.get("opnsense")

    if not provider_instance or not isinstance(provider_instance, OPNsenseProvider):
        raise click.ClickException("OPNsense provider not found")

    provider_instance._current_environment = env

    if not auto_approve:
        component_desc = component.upper()
        console.warning(
            f"This will completely remove all {component_desc} configuration from OPNsense."
        )
        console.warning("All subnets, reservations, and settings will be deleted.")
        if not click.confirm("\nDo you want to continue?", default=False):
            console.warning("Reset cancelled.")
            return

    component_lower = component.lower()
    if component_lower in ["kea/dhcpv4", "kea/dhcp"]:
        console.info("Resetting Kea DHCPv4 configuration...")
        provider_instance.reset_kea_dhcpv4(env)
        console.success("Kea DHCPv4 reset complete")

    if component_lower in ["kea/dhcpv6", "kea/dhcp"]:
        console.info("Resetting Kea DHCPv6 configuration...")
        provider_instance.reset_kea_dhcpv6(env)
        console.success("Kea DHCPv6 reset complete")

    console.success("Reset complete!")
    console.info("You can now run 'infra apply' to apply fresh configuration.")
