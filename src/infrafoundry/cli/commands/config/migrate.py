"""Migrate existing infrastructure to InfraFoundry configuration."""

from pathlib import Path
from typing import Any

import click

from infrafoundry.core.extractors import (
    get_extractor,
    list_extractor_providers,
    list_extractor_resource_types,
)
from infrafoundry.core.orchestrator import Orchestrator

from ...decorators import with_orchestrator
from ...utils import console


@click.command()
@click.option("--env", "-e", required=True, help="Environment name")
@click.option(
    "--provider",
    "-p",
    required=True,
    help="Provider name (validated against the registered extractors)",
)
@click.option(
    "--component",
    "-c",
    required=True,
    help="Component to migrate (validated against the registered extractors)",
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
    and generates InfraFoundry YAML configuration files. The set of valid
    ``--provider`` and ``--component`` values is determined at runtime
    from the extractor registry — any component a provider registers
    becomes immediately reachable via this command.

    Examples:
        # Migrate existing Kea DHCP configuration
        foundry config migrate --env prod --provider opnsense --component kea_dhcp

        # Migrate VLANs (direct-API)
        foundry config migrate --env prod --provider opnsense --component vlans

        # Migrate ISC DHCP to Kea DHCP format
        foundry config migrate --env prod --provider opnsense --component isc_to_kea
        foundry config migrate --env prod --provider opnsense --component isc_to_kea -i lan -i wan

        # Dry-run mode
        foundry config migrate --env prod --provider opnsense --component isc_to_kea --dry-run
    """
    # Force the registry to populate by instantiating the requested provider.
    # ``orchestrator.providers`` is keyed by lowercase provider name; pulling
    # it triggers ``OPNsenseProvider.__init__`` (which calls
    # ``_register_extractors``) for any provider the orchestrator knows about.
    provider_lower = provider.lower()
    component_lower = component.lower()

    provider_instance = orchestrator.providers.get(provider_lower)

    registered_providers = list_extractor_providers()
    if provider_lower not in registered_providers:
        registered_str = ", ".join(registered_providers) or "<none>"
        raise click.ClickException(
            f"Unsupported provider {provider!r}. Registered providers: {registered_str}."
        )

    if provider_instance is None:
        raise click.ClickException(
            f"{provider} provider not found in this environment "
            f"(no providers loaded for env {env!r})."
        )

    registered_components = list_extractor_resource_types(provider_lower)
    if component_lower not in registered_components:
        registered_str = ", ".join(registered_components) or "<none>"
        raise click.ClickException(
            f"Unsupported component {component!r} for provider {provider_lower!r}. "
            f"Registered components: {registered_str}."
        )

    # ``provider_instance`` carries the live ``_current_environment`` used
    # by some component managers; setting it here mirrors the prior behavior.
    provider_instance._current_environment = env

    if not output:
        config_dir = (ctx.obj or {}).get("config_dir", ".")
        output_path = (
            Path(config_dir) / "envs" / env / "resources" / f"migrated-{component_lower}.yaml"
        )
    else:
        output_path = Path(output)

    console.info(f"Migrating {component_lower} configuration from {provider_lower}...")

    kwargs: dict[str, Any] = {}
    if interfaces:
        interfaces_list = list(interfaces)
        kwargs["interfaces"] = interfaces_list
        console.info(f"Targeting interfaces: {', '.join(interfaces_list)}")

    extractor = get_extractor(provider_lower, component_lower)
    yaml_content = extractor.extract(env, **kwargs)

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
