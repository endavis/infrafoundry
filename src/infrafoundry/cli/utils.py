"""CLI utilities shared across commands."""

from __future__ import annotations

import os

import click
from rich.console import Console

console = Console()


def raise_cli_error(action: str, exc: Exception) -> None:
    """Raise a Click-friendly error while optionally printing stack traces."""
    if os.getenv("INFRAFOUNDRY_LOG_LEVEL") == "DEBUG":
        console.print_exception(show_locals=False)
    raise click.ClickException(f"{action}: {exc}") from exc
