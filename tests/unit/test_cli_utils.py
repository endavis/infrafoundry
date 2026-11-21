"""Unit tests for CLI utilities."""

from io import StringIO
from unittest.mock import Mock

import click
import pytest
from rich.console import Console as RichConsole

from infrafoundry.cli.utils import InfraFoundryConsole, raise_cli_error


class TestInfraFoundryConsole:
    """Tests for InfraFoundryConsole wrapper."""

    @pytest.fixture
    def mock_rich_console(self) -> Mock:
        """Create a mock Rich console."""
        return Mock()

    @pytest.fixture
    def console(self, mock_rich_console: Mock) -> InfraFoundryConsole:
        """Create InfraFoundryConsole with mocked Rich console."""
        return InfraFoundryConsole(rich_console=mock_rich_console)

    def test_header_prints_with_bold_cyan(
        self, console: InfraFoundryConsole, mock_rich_console: Mock
    ) -> None:
        """Test header() prints with bold cyan formatting."""
        console.header("Test Header")
        mock_rich_console.print.assert_called_once_with("[bold cyan]Test Header")

    def test_success_prints_with_checkmark(
        self, console: InfraFoundryConsole, mock_rich_console: Mock
    ) -> None:
        """Test success() prints with green checkmark."""
        console.success("Operation completed")
        mock_rich_console.print.assert_called_once_with("[green]✓ Operation completed")

    def test_error_prints_with_x_mark(
        self, console: InfraFoundryConsole, mock_rich_console: Mock
    ) -> None:
        """Test error() prints with red X mark."""
        console.error("Something failed")
        mock_rich_console.print.assert_called_once_with("[red]✗ Something failed")

    def test_warning_prints_with_warning_symbol(
        self, console: InfraFoundryConsole, mock_rich_console: Mock
    ) -> None:
        """Test warning() prints with yellow warning symbol."""
        console.warning("This is a warning")
        mock_rich_console.print.assert_called_once_with("[yellow]⚠ This is a warning")

    def test_info_prints_plain_message(
        self, console: InfraFoundryConsole, mock_rich_console: Mock
    ) -> None:
        """Test info() prints message without formatting."""
        console.info("Information message")
        mock_rich_console.print.assert_called_once_with("Information message")

    def test_status_prints_with_dim(
        self, console: InfraFoundryConsole, mock_rich_console: Mock
    ) -> None:
        """Test status() prints with dim formatting."""
        console.status("Loading...")
        mock_rich_console.print.assert_called_once_with("[dim]Loading...[/dim]")

    def test_print_forwards_to_rich_console(
        self, console: InfraFoundryConsole, mock_rich_console: Mock
    ) -> None:
        """Test print() forwards calls to Rich console."""
        console.print("Test message", style="bold", end="")
        mock_rich_console.print.assert_called_once_with("Test message", style="bold", end="")

    def test_print_exception_forwards_to_rich_console(
        self, console: InfraFoundryConsole, mock_rich_console: Mock
    ) -> None:
        """Test print_exception() forwards to Rich console."""
        console.print_exception(show_locals=True)
        mock_rich_console.print_exception.assert_called_once_with(show_locals=True)

    def test_default_console_uses_rich_console(self) -> None:
        """Test InfraFoundryConsole creates Rich console if none provided."""
        console = InfraFoundryConsole()
        # Should not raise an error and should have a console
        assert console._console is not None
        # Test it can actually print (won't raise)
        console.info("Test")

    def test_multiple_args_to_print(
        self, console: InfraFoundryConsole, mock_rich_console: Mock
    ) -> None:
        """Test print() can handle multiple arguments."""
        console.print("Message 1", "Message 2", sep=" | ")
        mock_rich_console.print.assert_called_once_with("Message 1", "Message 2", sep=" | ")

    def test_empty_messages(self, console: InfraFoundryConsole, mock_rich_console: Mock) -> None:
        """Test methods handle empty strings."""
        console.header("")
        console.success("")
        console.error("")
        console.warning("")
        console.info("")
        console.status("")

        assert mock_rich_console.print.call_count == 6

    def test_messages_with_special_characters(
        self, console: InfraFoundryConsole, mock_rich_console: Mock
    ) -> None:
        """Test methods handle messages with special characters."""
        special_msg = "Test: [bold]already formatted[/bold] & <html>"
        console.info(special_msg)
        mock_rich_console.print.assert_called_once_with(special_msg)

    def test_multiline_messages(
        self, console: InfraFoundryConsole, mock_rich_console: Mock
    ) -> None:
        """Test methods handle multiline messages."""
        multiline = "Line 1\nLine 2\nLine 3"
        console.success(multiline)
        mock_rich_console.print.assert_called_once_with(f"[green]✓ {multiline}")


BRACKETED = "actor cannot set scopes: [auth_keys devices:core] (403)"


def _real_console() -> tuple[InfraFoundryConsole, StringIO]:
    """Create an InfraFoundryConsole over a real Rich console writing to a buffer."""
    buffer = StringIO()
    rich_console = RichConsole(file=buffer, force_terminal=False, width=200)
    return InfraFoundryConsole(rich_console=rich_console), buffer


class TestMarkupEscaping:
    """Bracketed message text must not be consumed as Rich markup."""

    @pytest.mark.parametrize(
        "method", ["header", "success", "error", "warning", "list_item", "status"]
    )
    def test_helpers_print_bracketed_text_intact(self, method: str) -> None:
        """Each escaping helper keeps `[...]` text in the rendered output."""
        console, buffer = _real_console()
        getattr(console, method)(BRACKETED)
        assert BRACKETED in buffer.getvalue()

    def test_raise_cli_error_prints_bracketed_message_verbatim(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """raise_cli_error prints `[...]` text from the exception message intact."""
        console, buffer = _real_console()
        monkeypatch.setattr("infrafoundry.cli.utils.console", console)

        with pytest.raises(click.ClickException):
            raise_cli_error("apply", Exception(BRACKETED), use_error_codes=True)

        assert "[auth_keys devices:core]" in buffer.getvalue()
        assert BRACKETED in buffer.getvalue()
