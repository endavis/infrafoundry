"""Unit tests for CLI utilities."""

from unittest.mock import Mock

import pytest

from infrafoundry.cli.utils import InfraFoundryConsole


class TestInfraFoundryConsole:
    """Tests for InfraFoundryConsole wrapper."""

    @pytest.fixture
    def mock_rich_console(self):
        """Create a mock Rich console."""
        return Mock()

    @pytest.fixture
    def console(self, mock_rich_console):
        """Create InfraFoundryConsole with mocked Rich console."""
        return InfraFoundryConsole(rich_console=mock_rich_console)

    def test_header_prints_with_bold_cyan(self, console, mock_rich_console):
        """Test header() prints with bold cyan formatting."""
        console.header("Test Header")
        mock_rich_console.print.assert_called_once_with("[bold cyan]Test Header")

    def test_success_prints_with_checkmark(self, console, mock_rich_console):
        """Test success() prints with green checkmark."""
        console.success("Operation completed")
        mock_rich_console.print.assert_called_once_with("[green]✓ Operation completed")

    def test_error_prints_with_x_mark(self, console, mock_rich_console):
        """Test error() prints with red X mark."""
        console.error("Something failed")
        mock_rich_console.print.assert_called_once_with("[red]✗ Something failed")

    def test_warning_prints_with_warning_symbol(self, console, mock_rich_console):
        """Test warning() prints with yellow warning symbol."""
        console.warning("This is a warning")
        mock_rich_console.print.assert_called_once_with("[yellow]⚠ This is a warning")

    def test_info_prints_plain_message(self, console, mock_rich_console):
        """Test info() prints message without formatting."""
        console.info("Information message")
        mock_rich_console.print.assert_called_once_with("Information message")

    def test_status_prints_with_dim(self, console, mock_rich_console):
        """Test status() prints with dim formatting."""
        console.status("Loading...")
        mock_rich_console.print.assert_called_once_with("[dim]Loading...[/dim]")

    def test_print_forwards_to_rich_console(self, console, mock_rich_console):
        """Test print() forwards calls to Rich console."""
        console.print("Test message", style="bold", end="")
        mock_rich_console.print.assert_called_once_with("Test message", style="bold", end="")

    def test_print_exception_forwards_to_rich_console(self, console, mock_rich_console):
        """Test print_exception() forwards to Rich console."""
        console.print_exception(show_locals=True)
        mock_rich_console.print_exception.assert_called_once_with(show_locals=True)

    def test_default_console_uses_rich_console(self):
        """Test InfraFoundryConsole creates Rich console if none provided."""
        console = InfraFoundryConsole()
        # Should not raise an error and should have a console
        assert console._console is not None
        # Test it can actually print (won't raise)
        console.info("Test")

    def test_multiple_args_to_print(self, console, mock_rich_console):
        """Test print() can handle multiple arguments."""
        console.print("Message 1", "Message 2", sep=" | ")
        mock_rich_console.print.assert_called_once_with("Message 1", "Message 2", sep=" | ")

    def test_empty_messages(self, console, mock_rich_console):
        """Test methods handle empty strings."""
        console.header("")
        console.success("")
        console.error("")
        console.warning("")
        console.info("")
        console.status("")

        assert mock_rich_console.print.call_count == 6

    def test_messages_with_special_characters(self, console, mock_rich_console):
        """Test methods handle messages with special characters."""
        special_msg = "Test: [bold]already formatted[/bold] & <html>"
        console.info(special_msg)
        mock_rich_console.print.assert_called_once_with(special_msg)

    def test_multiline_messages(self, console, mock_rich_console):
        """Test methods handle multiline messages."""
        multiline = "Line 1\nLine 2\nLine 3"
        console.success(multiline)
        mock_rich_console.print.assert_called_once_with(f"[green]✓ {multiline}")
