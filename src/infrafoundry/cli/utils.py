"""CLI utilities shared across commands."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

import click
from rich.console import Console as RichConsole

from infrafoundry.core.exceptions import InfraFoundryError

from .errors import format_error, get_error_code, get_error_info
from .output import BULLET

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

    def list_item(self, message: str, indent: int = 2) -> None:
        """Print a list item with standard bullet.

        Args:
            message: Item text
            indent: Number of spaces before bullet (default: 2)
        """
        self._console.print(f"{' ' * indent}{BULLET} {message}")

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


def raise_cli_error(action: str, exc: Exception, *, use_error_codes: bool = True) -> None:
    """Raise a Click-friendly error while optionally printing stack traces.

    Args:
        action: Action being performed when error occurred
        exc: Exception that was raised
        use_error_codes: Whether to use the error catalog (default: True)

    Raises:
        click.ClickException: User-friendly error with context
    """
    is_debug = os.getenv("INFRAFOUNDRY_LOG_LEVEL") == "DEBUG"

    if is_debug:
        console.print_exception(show_locals=False)

    if use_error_codes:
        # Use error catalog for structured error messages
        error_msg = format_error(exc, action, verbose=is_debug)
        # Print the formatted error (which includes suggestions)
        console.print("[bold red]Error:[/bold red]")
        for line in error_msg.split("\n"):
            if line.startswith("[IF-"):
                # Error code line
                console.print(f"[bold red]{line}[/bold red]")
            elif line.strip().startswith("- "):
                # Suggestion bullet
                console.print(f"[yellow]{line}[/yellow]")
            elif "Suggestions:" in line:
                console.print(f"[bold]{line}[/bold]")
            elif "See:" in line:
                console.print(f"[cyan]{line}[/cyan]")
            elif "Run with --debug" in line:
                console.print(f"[dim]{line}[/dim]")
            else:
                console.print(line)
        # Raise with just the code and title for the CLI exit message
        code = get_error_code(exc)
        info = get_error_info(code)
        title = info.title if info else "Error"
        raise click.ClickException(f"[{code}] {title}") from exc
    else:
        # Legacy format without error codes
        if isinstance(exc, InfraFoundryError) and exc.context:
            context_str = ", ".join(f"{k}={v}" for k, v in exc.context.items())
            error_msg = f"{action}: {exc.message} ({context_str})"
        else:
            error_msg = f"{action}: {exc}"
        raise click.ClickException(error_msg) from exc
