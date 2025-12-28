"""Export existing Proxmox resources to InfraFoundry YAML."""

from __future__ import annotations

from pathlib import Path

import click

from infrafoundry.core.config import ConfigManager
from infrafoundry.providers.proxmox.exporter import ProxmoxConfigExporter

from ...utils import console, raise_cli_error


@click.command(name="export-proxmox")
@click.option("--env", "-e", required=True, help="Environment name to use for credentials")
@click.option(
    "--output",
    "-o",
    type=click.Path(dir_okay=True, file_okay=False, path_type=Path),
    required=True,
    help="Output directory for exported YAML",
)
@click.option("--node", help="Optional node filter")
@click.option(
    "--resource-type",
    type=click.Choice(["vm", "network", "storage"], case_sensitive=False),
    help="Optional resource type filter",
)
@click.pass_context
def export_proxmox(
    ctx: click.Context,
    env: str,
    output: Path,
    node: str | None,
    resource_type: str | None,
) -> None:
    """Export Proxmox configuration to InfraFoundry YAML."""
    try:
        config_repo = ctx.obj.get("config_dir")
        config_manager = ConfigManager(base_dir=config_repo / "envs" if config_repo else None)
        env_config = config_manager.load_environment(env).model_dump()

        exporter = ProxmoxConfigExporter(env_config)  # type: ignore[arg-type]
        result = exporter.export(node_filter=node, resource_filter=resource_type)

        output.mkdir(parents=True, exist_ok=True)
        for filename, content in result.items():
            (output / filename).write_text(content)

        console.success(f"Exported {len(result)} files to {output}")
    except click.ClickException:
        raise
    except Exception as exc:
        raise_cli_error("Failed to export Proxmox configuration", exc)
