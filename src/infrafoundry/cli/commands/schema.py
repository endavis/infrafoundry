"""Schema export commands for IDE autocomplete support."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click
from pydantic import BaseModel, Field

from infrafoundry.core.config import BackendConfig, EnvironmentConfig
from infrafoundry.core.hooks.models import HooksConfig
from infrafoundry.core.provider import ResourceConfig

from ..utils import console

# Schema output directory (relative to config repo)
DEFAULT_SCHEMA_DIR = ".schemas"


class ResourceFileSchema(BaseModel):
    """Schema for resource-centric config files (resources/*.yaml)."""

    resources: list[ResourceConfig] = Field(
        ...,
        description="List of infrastructure resources",
    )


# Map of schema names to their models
SCHEMA_MODELS: dict[str, type[BaseModel]] = {
    "settings": EnvironmentConfig,
    "resources": ResourceFileSchema,
    "backend": BackendConfig,
    "hooks": HooksConfig,
    "resource": ResourceConfig,
}


def _generate_schema(model: type[BaseModel], title: str | None = None) -> dict[str, Any]:
    """Generate JSON Schema from a Pydantic model.

    Args:
        model: Pydantic model class
        title: Optional title override

    Returns:
        JSON Schema dict
    """
    schema = model.model_json_schema()
    if title:
        schema["title"] = title
    return schema


def _write_schema(schema: dict[str, Any], output_path: Path) -> None:
    """Write schema to file.

    Args:
        schema: JSON Schema dict
        output_path: Path to write to
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(schema, f, indent=2)
        f.write("\n")


@click.group()
def schema() -> None:
    """Export JSON schemas for IDE autocomplete.

    Generate JSON Schema files from InfraFoundry's configuration models
    to enable autocomplete and validation in your IDE.

    Examples:

        # Export all schemas to .schemas/
        foundry schema export

        # Export to custom directory
        foundry schema export --output ./schemas

        # List available schemas
        foundry schema list

        # Show a specific schema
        foundry schema show settings
    """
    pass


@schema.command(name="export")
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    default=DEFAULT_SCHEMA_DIR,
    help=f"Output directory for schemas (default: {DEFAULT_SCHEMA_DIR})",
)
@click.pass_context
def schema_export(ctx: click.Context, output: Path) -> None:
    """Export all JSON schemas for IDE autocomplete.

    Generates schema files that can be used with VS Code, IntelliJ,
    and other editors to provide autocomplete for YAML configuration files.
    """
    # If config_dir is set, put schemas relative to it
    config_dir = ctx.obj.get("config_dir") if ctx.obj else None
    output_dir = config_dir / output if config_dir else Path(output)

    console.header(f"Exporting schemas to {output_dir}")

    exported = []
    for name, model in SCHEMA_MODELS.items():
        schema_data = _generate_schema(model)
        output_path = output_dir / f"{name}.schema.json"
        _write_schema(schema_data, output_path)
        exported.append((name, output_path))
        console.info(f"  {name}.schema.json")

    console.success(f"Exported {len(exported)} schemas")
    console.info("")
    console.info("To enable in VS Code, add to .vscode/settings.json:")
    console.info("")
    console.print('  "yaml.schemas": {')
    console.print(f'    "{output_dir}/settings.schema.json": "**/envs/*/settings.yaml",')
    console.print(f'    "{output_dir}/resources.schema.json": "**/envs/*/resources/*.yaml"')
    console.print("  }")


@schema.command(name="list")
def schema_list() -> None:
    """List available schemas."""
    console.header("Available schemas:")
    for name, model in SCHEMA_MODELS.items():
        doc = model.__doc__ or "No description"
        # Get first line of docstring
        description = doc.split("\n")[0].strip()
        console.info(f"  {name}: {description}")


@schema.command(name="show")
@click.argument("name", type=click.Choice(list(SCHEMA_MODELS.keys())))
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["json", "yaml"]),
    default="json",
    help="Output format (default: json)",
)
def schema_show(name: str, output_format: str) -> None:
    """Show a specific schema.

    NAME is the schema to display (settings, resources, backend, hooks, resource).
    """
    model = SCHEMA_MODELS[name]
    schema_data = _generate_schema(model)

    if output_format == "yaml":
        import yaml

        click.echo(yaml.safe_dump(schema_data, default_flow_style=False, sort_keys=False))
    else:
        click.echo(json.dumps(schema_data, indent=2))
