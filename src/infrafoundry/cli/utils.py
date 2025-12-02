"""CLI utilities shared across commands."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

import click
from rich.console import Console as RichConsole

from infrafoundry.core.exceptions import InfraFoundryError

if TYPE_CHECKING:
    from rich.console import Console


class InfraFoundryConsole:
    """Semantic console wrapper for standardized output."""

    def __init__(self, rich_console: Console | None = None) -> None:
        self._console = rich_console or RichConsole()

    def header(self, message: str) -> None:
        """Print a section header."""
        self._console.print(f"[bold cyan]{message}")

    def success(self, message: str) -> None:
        """Print a success message."""
        self._console.print(f"[green]✓ {message}")

    def error(self, message: str) -> None:
        """Print an error message."""
        self._console.print(f"[red]✗ {message}")

    def warning(self, message: str) -> None:
        """Print a warning message."""
        self._console.print(f"[yellow]⚠ {message}")

    def info(self, message: str) -> None:
        """Print an info message."""
        self._console.print(message)

    def status(self, message: str) -> None:
        """Print a status update."""
        self._console.print(f"[dim]{message}[/dim]")

    def print(self, *args: Any, **kwargs: Any) -> None:
        """Forward generic print to rich console."""
        self._console.print(*args, **kwargs)

    def print_exception(self, *args: Any, **kwargs: Any) -> None:
        """Forward print_exception to rich console."""
        self._console.print_exception(*args, **kwargs)


# Global instance
console = InfraFoundryConsole()


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
