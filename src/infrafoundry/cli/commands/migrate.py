"""Migrate existing infrastructure to InfraFoundry configuration."""

from pathlib import Path

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
@click.pass_context
def migrate(
    ctx: click.Context,
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

            # Determine output path
            if not output:
                config_dir = ctx.obj.get("config_dir", ".")
                component_name = component.replace("/", "-")
                output = str(
                    Path(config_dir)
                    / "envs"
                    / env
                    / "resources"
                    / f"migrated-{component_name}.yaml"
                )

            # Execute migration based on component
            if component.lower() == "kea/dhcp":
                console.print("[cyan]Migrating Kea DHCP configuration from OPNsense...[/cyan]")
                yaml_content = provider_instance.migrate_kea_dhcp(env)

                if dry_run:
                    console.print(
                        "\n[bold yellow]Dry-run mode - "
                        "configuration would be written to:[/bold yellow]"
                    )
                    console.print(f"[yellow]{output}[/yellow]\n")
                    console.print("[bold cyan]Generated configuration:[/bold cyan]")
                    console.print(yaml_content)
                else:
                    # Write to file
                    output_path = Path(output)
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    output_path.write_text(yaml_content)
                    console.print(f"[green]✓ Configuration written to: {output}[/green]")

            elif component.lower() == "isc-to-kea":
                console.print(
                    "[cyan]Migrating ISC DHCP to Kea DHCP configuration from OPNsense...[/cyan]"
                )

                # Convert tuple to list or None
                interfaces_list = list(interfaces) if interfaces else None

                if interfaces_list:
                    console.print(f"[dim]Targeting interfaces: {', '.join(interfaces_list)}[/dim]")
                else:
                    console.print("[dim]Migrating all interfaces with ISC DHCP enabled[/dim]")

                yaml_content = provider_instance.migrate_isc_to_kea(env, interfaces_list)

                if dry_run:
                    console.print(
                        "\n[bold yellow]Dry-run mode - "
                        "configuration would be written to:[/bold yellow]"
                    )
                    console.print(f"[yellow]{output}[/yellow]\n")
                    console.print("[bold cyan]Generated configuration:[/bold cyan]")
                    console.print(yaml_content)
                else:
                    # Write to file
                    output_path = Path(output)
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    output_path.write_text(yaml_content)
                    console.print(f"[green]✓ Configuration written to: {output}[/green]")

            console.print("\n[bold green]Migration complete![/bold green]")

        else:
            raise click.ClickException(f"Unsupported provider: {provider}")

    except Exception as exc:
        raise_cli_error("Migration failed", exc)
