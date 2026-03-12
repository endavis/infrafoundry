"""Output formatting utilities for CLI commands.

This module provides standardized output formatting across all CLI commands,
including consistent bullet styles, JSON/YAML output, and format options.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from enum import StrEnum
from functools import wraps
from typing import Any, TypeVar

import click
import yaml

# Standardized bullet character for all list output
BULLET = "•"

# Type variable for decorated functions
F = TypeVar("F", bound=Callable[..., Any])


class OutputFormat(StrEnum):
    """Output format options for CLI commands."""

    TEXT = "text"
    JSON = "json"
    YAML = "yaml"
    TABLE = "table"  # Alias for text with Rich tables


def format_json(data: Any, *, indent: int = 2) -> str:
    """Format data as JSON string.

    Args:
        data: Data to serialize
        indent: Indentation level (default: 2)

    Returns:
        JSON formatted string
    """
    return json.dumps(data, indent=indent, default=str)


def format_yaml(data: Any) -> str:
    """Format data as YAML string.

    Args:
        data: Data to serialize

    Returns:
        YAML formatted string
    """
    return yaml.safe_dump(data, default_flow_style=False, sort_keys=False)


def output_data(data: Any, output_format: OutputFormat | str) -> None:
    """Output data in the specified format.

    For JSON/YAML formats, prints to stdout directly (machine-readable).
    This bypasses Rich console formatting for clean output.

    Args:
        data: Data to output
        output_format: Output format (text, json, yaml)
    """
    if isinstance(output_format, str):
        output_format = OutputFormat(output_format)

    if output_format == OutputFormat.JSON:
        click.echo(format_json(data))
    elif output_format == OutputFormat.YAML:
        click.echo(format_yaml(data))
    else:
        # For text/table format, caller should handle display
        raise ValueError(f"Use appropriate display method for format: {output_format}")


def format_list_item(text: str, indent: int = 2) -> str:
    """Format a list item with standard bullet.

    Args:
        text: Item text
        indent: Number of spaces before bullet (default: 2)

    Returns:
        Formatted list item string
    """
    return f"{' ' * indent}{BULLET} {text}"


def format_list(
    items: Sequence[str],
    *,
    indent: int = 2,
) -> list[str]:
    """Format a list of items with standard bullets.

    Args:
        items: List of item strings
        indent: Number of spaces before bullet (default: 2)

    Returns:
        List of formatted item strings
    """
    return [format_list_item(item, indent=indent) for item in items]


def add_format_option(
    formats: Sequence[str] | None = None,
    default: str = "text",
) -> Callable[[F], F]:
    """Decorator to add --format option to a command.

    Args:
        formats: Allowed formats (default: ["text", "json"])
        default: Default format (default: "text")

    Returns:
        Click option decorator
    """
    if formats is None:
        formats = ["text", "json"]

    def decorator(f: F) -> F:
        return click.option(
            "--format",
            "output_format",
            type=click.Choice(list(formats)),
            default=default,
            help=f"Output format (default: {default})",
        )(f)

    return decorator


def with_format_output(
    formats: Sequence[str] | None = None,
    default: str = "text",
) -> Callable[[Callable[..., dict[str, Any] | None]], Callable[..., None]]:
    """Decorator combining format option and automatic output handling.

    The decorated function should return a dict for JSON/YAML output,
    or None if it handles text output itself.

    Args:
        formats: Allowed formats (default: ["text", "json"])
        default: Default format (default: "text")

    Returns:
        Combined decorator
    """
    if formats is None:
        formats = ["text", "json"]

    def decorator(
        f: Callable[..., dict[str, Any] | None],
    ) -> Callable[..., None]:
        @click.option(
            "--format",
            "output_format",
            type=click.Choice(list(formats)),
            default=default,
            help=f"Output format (default: {default})",
        )
        @wraps(f)
        def wrapper(*args: Any, output_format: str, **kwargs: Any) -> None:
            result = f(*args, output_format=output_format, **kwargs)
            if result is not None and output_format in ("json", "yaml"):
                output_data(result, output_format)

        return wrapper

    return decorator
