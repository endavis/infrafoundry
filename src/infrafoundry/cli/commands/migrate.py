"""Migrate existing infrastructure to InfraFoundry configuration."""

from pathlib import Path

import click

from infrafoundry.core.orchestrator import Orchestrator

from ..decorators import with_orchestrator
from ..utils import console


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
    type=click.Choice(["kea/dhcp", "isc-to-kea"], case_sensitive=False),
    help="Component to migrate",
)
@click.option(
    "--interfaces",
    "-i",
    multiple=True,
    help="Specific interfaces to migrate (can be specified multiple times)",
)
@click.option(
    "--output",
    "-o",
    help="Output file path (default: envs/{env}/resources/migrated-{component}.yaml)",
)
@click.option("--dry-run", is_flag=True, help="Show what would be generated without writing files")
@with_orchestrator("Migration failed")
def migrate(
    ctx: click.Context,
    orchestrator: Orchestrator,
    env: str,
    provider: str,
    component: str,
    output: str | None,
    dry_run: bool,
    interfaces: tuple[str, ...],
) -> None:
    """Migrate existing infrastructure to InfraFoundry configuration.

    This command reads the current configuration from the provider's API
    and generates InfraFoundry YAML configuration files.

    Examples:
        # Migrate existing Kea DHCP configuration
        infra migrate --env prod --provider opnsense --component kea/dhcp

        # Migrate ISC DHCP to Kea DHCP format
        infra migrate --env prod --provider opnsense --component isc-to-kea
        infra migrate --env prod --provider opnsense --component isc-to-kea -i lan -i wan

        # Dry-run mode
        infra migrate --env prod --provider opnsense --component isc-to-kea --dry-run
    """
    provider_lower = provider.lower()
    if provider_lower != "opnsense":
        raise click.ClickException(f"Unsupported provider: {provider}")

    from infrafoundry.providers.opnsense import OPNsenseProvider

    provider_instance = orchestrator.providers.get("opnsense")
    if not provider_instance or not isinstance(provider_instance, OPNsenseProvider):
        raise click.ClickException("OPNsense provider not found")

    provider_instance._current_environment = env

    if not output:
        config_dir = (ctx.obj or {}).get("config_dir", ".")
        component_name = component.replace("/", "-")
        output_path = (
            Path(config_dir) / "envs" / env / "resources" / f"migrated-{component_name}.yaml"
        )
    else:
        output_path = Path(output)

    component_lower = component.lower()
    if component_lower == "kea/dhcp":
        console.info("Migrating Kea DHCP configuration from OPNsense...")
        yaml_content = provider_instance.migrate_kea_dhcp(env)
    elif component_lower == "isc-to-kea":
        console.info("Migrating ISC DHCP to Kea DHCP configuration from OPNsense...")
        interfaces_list = list(interfaces) if interfaces else None

        if interfaces_list:
            console.info(f"Targeting interfaces: {', '.join(interfaces_list)}")
        else:
            console.info("Migrating all interfaces with ISC DHCP enabled")

        yaml_content = provider_instance.migrate_isc_to_kea(env, interfaces_list)
    else:
        raise click.ClickException(f"Unsupported component: {component}")

    if dry_run:
        console.warning("Dry-run mode - configuration would be written to:")
        console.info(f"{output_path}\n")
        console.info("Generated configuration:")
        console.print(yaml_content)
    else:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(yaml_content)
        console.success(f"Configuration written to: {output_path}")

    console.success("Migration complete!")
