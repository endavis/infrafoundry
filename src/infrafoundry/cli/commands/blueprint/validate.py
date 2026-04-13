"""Blueprint validation command using Jinja2 static analysis."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from infrafoundry.core.config.blueprint_resolver import BlueprintResolver
from infrafoundry.core.config.blueprint_validator import (
    BlueprintValidationResult,
    BlueprintValidator,
)
from infrafoundry.core.exceptions import InvalidConfigurationError


def _format_text(result: BlueprintValidationResult) -> str:
    """Format a validation result as human-readable text.

    Args:
        result: Validation result to format.

    Returns:
        Formatted text output.
    """
    lines: list[str] = []
    status = "FAIL" if result.has_errors else ("WARN" if result.has_warnings else "OK")
    bp_type = "multi-provider" if result.is_multi_provider else "single-provider"
    lines.append(f"Blueprint: {result.blueprint_name} ({bp_type}) [{status}]")

    for prov in result.providers:
        label = prov.provider
        lines.append(f"  Provider: {label}")
        lines.append(f"    Template variables: {len(prov.template_vars)}")
        lines.append(f"    Defaults defined:   {len(prov.defaults)}")

        if prov.errors:
            for err in prov.errors:
                lines.append(f"    ERROR: {err}")

        if prov.warnings:
            for warn in prov.warnings:
                lines.append(f"    WARNING: {warn}")

        if not prov.errors and not prov.warnings:
            lines.append("    No issues found.")

    return "\n".join(lines)


def _format_json(result: BlueprintValidationResult) -> str:
    """Format a validation result as JSON.

    Args:
        result: Validation result to format.

    Returns:
        JSON string.
    """
    data = {
        "blueprint_name": result.blueprint_name,
        "is_multi_provider": result.is_multi_provider,
        "has_errors": result.has_errors,
        "has_warnings": result.has_warnings,
        "providers": [
            {
                "provider": p.provider,
                "template_vars": sorted(p.template_vars),
                "defaults": sorted(p.defaults),
                "errors": p.errors,
                "warnings": p.warnings,
            }
            for p in result.providers
        ],
    }
    return json.dumps(data, indent=2)


def _validate_blueprint(
    resolver: BlueprintResolver, name: str, fmt: str
) -> BlueprintValidationResult:
    """Resolve and validate a single blueprint, printing output.

    Args:
        resolver: Blueprint resolver instance.
        name: Blueprint name.
        fmt: Output format (``text`` or ``json``).

    Returns:
        The validation result.

    Raises:
        click.ClickException: If the blueprint cannot be resolved.
    """
    try:
        resolved = resolver.resolve(name)
    except InvalidConfigurationError as e:
        raise click.ClickException(str(e)) from e

    validator = BlueprintValidator(resolved)
    result = validator.validate()

    if fmt == "json":
        click.echo(_format_json(result))
    else:
        click.echo(_format_text(result))

    return result


@click.command()
@click.option(
    "--blueprint",
    "-b",
    "blueprints",
    multiple=True,
    help="Blueprint name to validate (repeatable).",
)
@click.option(
    "--all",
    "validate_all",
    is_flag=True,
    default=False,
    help="Validate all available blueprints.",
)
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["text", "json"], case_sensitive=False),
    default="text",
    help="Output format.",
)
def validate(blueprints: tuple[str, ...], validate_all: bool, fmt: str) -> None:
    """Validate blueprint templates against their declared defaults.

    Uses Jinja2 static analysis to extract template variables and check
    them against the blueprint's defaults layers.  For multi-provider
    blueprints, also warns about asymmetric variable usage.

    Exit code 0 when clean or warnings-only; exit code 1 on errors.
    """
    if not blueprints and not validate_all:
        raise click.UsageError("Specify --blueprint/-b or --all.")

    # BlueprintResolver needs a base_dir (envs/) but we only need
    # the framework blueprints, so use a dummy path.
    resolver = BlueprintResolver(base_dir=Path("."))

    names: list[str]
    if validate_all:
        names = resolver.list_blueprints()
        if not names:
            click.echo("No blueprints found.")
            return
    else:
        names = list(blueprints)

    has_errors = False
    for i, name in enumerate(names):
        if i > 0 and fmt == "text":
            click.echo("")  # Blank line between blueprints
        result = _validate_blueprint(resolver, name, fmt)
        if result.has_errors:
            has_errors = True

    if has_errors:
        sys.exit(1)
