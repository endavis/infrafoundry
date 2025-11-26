"""CLI utilities shared across commands."""

from __future__ import annotations

import os

import click
from rich.console import Console

from infrafoundry.core.exceptions import InfraFoundryError

console = Console()


def raise_cli_error(action: str, exc: Exception) -> None:
    """Raise a Click-friendly error while optionally printing stack traces.

    Args:
        action: Action being performed when error occurred
        exc: Exception that was raised

    Raises:
        click.ClickException: User-friendly error with context
    """
    if os.getenv("INFRAFOUNDRY_LOG_LEVEL") == "DEBUG":
        console.print_exception(show_locals=False)

    # Format InfraFoundry errors with context if available
    if isinstance(exc, InfraFoundryError) and exc.context:
        context_str = ", ".join(f"{k}={v}" for k, v in exc.context.items())
        error_msg = f"{action}: {exc.message} ({context_str})"
    else:
        error_msg = f"{action}: {exc}"

    raise click.ClickException(error_msg) from exc
