"""Progress feedback utilities for CLI commands."""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

from rich.console import Console
from rich.live import Live
from rich.spinner import Spinner
from rich.text import Text

if TYPE_CHECKING:
    from collections.abc import Generator

# Global console instance
_console = Console()


class ProgressTracker:
    """Track progress through a multi-step operation.

    Provides a spinner with elapsed time and current status.
    """

    def __init__(
        self,
        console: Console | None = None,
        spinner_style: str = "dots",
    ) -> None:
        """Initialize progress tracker.

        Args:
            console: Rich console to use (defaults to global console)
            spinner_style: Style of spinner animation (default: dots)
        """
        self._console = console or _console
        self._spinner_style = spinner_style
        self._start_time: float | None = None
        self._current_status: str = ""
        self._live: Live | None = None

    def _format_elapsed(self) -> str:
        """Format elapsed time as human-readable string."""
        if self._start_time is None:
            return ""
        elapsed = time.time() - self._start_time
        if elapsed < 60:
            return f"{elapsed:.0f}s"
        minutes = int(elapsed // 60)
        seconds = int(elapsed % 60)
        return f"{minutes}m {seconds}s"

    def _render(self) -> Text:
        """Render the current progress display."""
        spinner = Spinner(self._spinner_style)
        text = Text()
        # Get spinner frame - render returns a Text object
        spinner_text = spinner.render(time.time())
        text.append_text(Text(str(spinner_text)))
        text.append(" ")
        text.append(self._current_status, style="cyan")
        elapsed = self._format_elapsed()
        if elapsed:
            text.append(f" ({elapsed})", style="dim")
        return text

    def start(self, status: str = "Working...") -> None:
        """Start the progress tracker.

        Args:
            status: Initial status message
        """
        self._start_time = time.time()
        self._current_status = status
        self._live = Live(
            self._render(),
            console=self._console,
            refresh_per_second=10,
            transient=True,
        )
        self._live.start()

    def update(self, status: str) -> None:
        """Update the current status message.

        Args:
            status: New status message
        """
        self._current_status = status
        if self._live:
            self._live.update(self._render())

    def stop(self, final_message: str | None = None) -> None:
        """Stop the progress tracker.

        Args:
            final_message: Optional message to print after stopping
        """
        if self._live:
            self._live.stop()
            self._live = None

        if final_message:
            elapsed = self._format_elapsed()
            if elapsed:
                self._console.print(f"{final_message} ({elapsed})")
            else:
                self._console.print(final_message)

        self._start_time = None


@contextmanager
def progress_spinner(
    status: str = "Working...",
    success_message: str | None = None,
    console: Console | None = None,
) -> Generator[ProgressTracker, None, None]:
    """Context manager for progress spinner with elapsed time.

    Args:
        status: Initial status message
        success_message: Message to show on successful completion
        console: Rich console to use

    Yields:
        ProgressTracker instance for updating status

    Example:
        >>> with progress_spinner("Planning infrastructure...") as progress:
        ...     progress.update("Processing proxmox provider...")
        ...     # do work
        ...     progress.update("Processing opnsense provider...")
        ...     # do more work
    """
    tracker = ProgressTracker(console=console)
    tracker.start(status)
    try:
        yield tracker
    finally:
        tracker.stop(success_message)


@contextmanager
def operation_status(
    operation: str,
    console: Console | None = None,
) -> Generator[ProgressTracker, None, None]:
    """Context manager for tracking a named operation.

    Automatically formats start/end messages.

    Args:
        operation: Name of the operation (e.g., "Planning", "Applying")
        console: Rich console to use

    Yields:
        ProgressTracker instance for updating status

    Example:
        >>> with operation_status("Planning") as progress:
        ...     progress.update("Generating Terraform configs...")
        ...     # do work
    """
    cons = console or _console
    tracker = ProgressTracker(console=cons)
    tracker.start(f"{operation}...")
    try:
        yield tracker
    except Exception:
        tracker.stop()
        raise
    else:
        tracker.stop()


def format_resource_count(current: int, total: int, action: str = "Processing") -> str:
    """Format a resource count status message.

    Args:
        current: Current resource number (1-indexed)
        total: Total number of resources
        action: Action being performed

    Returns:
        Formatted status string

    Example:
        >>> format_resource_count(3, 10, "Applying")
        'Applying resource 3/10...'
    """
    return f"{action} resource {current}/{total}..."


def format_provider_status(provider: str, action: str = "Processing") -> str:
    """Format a provider status message.

    Args:
        provider: Provider name
        action: Action being performed

    Returns:
        Formatted status string

    Example:
        >>> format_provider_status("proxmox", "Planning")
        'Planning proxmox...'
    """
    return f"{action} {provider}..."


class OperationTimer:
    """Simple timer for measuring operation duration."""

    def __init__(self) -> None:
        """Initialize the timer."""
        self._start_time: float | None = None
        self._end_time: float | None = None

    def start(self) -> None:
        """Start the timer."""
        self._start_time = time.time()
        self._end_time = None

    def stop(self) -> None:
        """Stop the timer."""
        self._end_time = time.time()

    @property
    def elapsed(self) -> float:
        """Get elapsed time in seconds."""
        if self._start_time is None:
            return 0.0
        end = self._end_time or time.time()
        return end - self._start_time

    @property
    def elapsed_str(self) -> str:
        """Get elapsed time as formatted string."""
        elapsed = self.elapsed
        if elapsed < 60:
            return f"{elapsed:.1f}s"
        minutes = int(elapsed // 60)
        seconds = int(elapsed % 60)
        return f"{minutes}m {seconds}s"

    def __enter__(self) -> OperationTimer:
        """Start timer on context entry."""
        self.start()
        return self

    def __exit__(self, *_args: Any) -> None:
        """Stop timer on context exit."""
        self.stop()
