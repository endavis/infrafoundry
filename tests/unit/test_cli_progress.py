"""Unit tests for CLI progress utilities."""

import time
from unittest.mock import patch

from rich.console import Console

from infrafoundry.cli.progress import (
    OperationTimer,
    ProgressTracker,
    format_provider_status,
    format_resource_count,
    operation_status,
    progress_spinner,
)


class TestOperationTimer:
    """Tests for the OperationTimer class."""

    def test_timer_basic_usage(self):
        """Test basic timer start/stop functionality."""
        timer = OperationTimer()
        timer.start()
        time.sleep(0.1)
        timer.stop()

        assert timer.elapsed >= 0.1
        assert timer.elapsed < 0.5

    def test_timer_context_manager(self):
        """Test timer as context manager."""
        with OperationTimer() as timer:
            time.sleep(0.1)

        assert timer.elapsed >= 0.1
        assert timer.elapsed < 0.5

    def test_timer_elapsed_str_seconds(self):
        """Test elapsed time string formatting for seconds."""
        timer = OperationTimer()
        timer.start()
        time.sleep(0.1)
        timer.stop()

        elapsed_str = timer.elapsed_str
        assert "s" in elapsed_str
        # Should not have minutes for < 60 seconds
        assert "m" not in elapsed_str

    def test_timer_elapsed_str_minutes(self):
        """Test elapsed time string formatting for minutes."""
        timer = OperationTimer()
        timer._start_time = time.time() - 125  # 2m 5s ago
        timer._end_time = time.time()

        elapsed_str = timer.elapsed_str
        assert "2m" in elapsed_str
        assert "5s" in elapsed_str

    def test_timer_not_started(self):
        """Test elapsed time when timer not started."""
        timer = OperationTimer()
        assert timer.elapsed == 0.0
        assert timer.elapsed_str == "0.0s"


class TestProgressTracker:
    """Tests for the ProgressTracker class."""

    def test_tracker_creation(self):
        """Test progress tracker can be created."""
        tracker = ProgressTracker()
        assert tracker._current_status == ""
        assert tracker._start_time is None

    def test_tracker_with_custom_console(self):
        """Test progress tracker with custom console."""
        console = Console(force_terminal=True)
        tracker = ProgressTracker(console=console)
        assert tracker._console is console

    def test_tracker_format_elapsed_not_started(self):
        """Test elapsed formatting when not started."""
        tracker = ProgressTracker()
        assert tracker._format_elapsed() == ""

    def test_tracker_format_elapsed_seconds(self):
        """Test elapsed formatting for seconds."""
        tracker = ProgressTracker()
        tracker._start_time = time.time() - 30
        elapsed = tracker._format_elapsed()
        assert "30s" in elapsed

    def test_tracker_format_elapsed_minutes(self):
        """Test elapsed formatting for minutes."""
        tracker = ProgressTracker()
        tracker._start_time = time.time() - 90  # 1m 30s
        elapsed = tracker._format_elapsed()
        assert "1m" in elapsed
        assert "30s" in elapsed


class TestProgressSpinner:
    """Tests for the progress_spinner context manager."""

    def test_spinner_context_manager(self):
        """Test spinner as context manager."""
        console = Console(force_terminal=True, force_interactive=False)

        with (
            patch.object(ProgressTracker, "start") as mock_start,
            patch.object(ProgressTracker, "stop") as mock_stop,
        ):
            with progress_spinner("Testing...", console=console) as tracker:
                assert tracker is not None

            mock_start.assert_called_once_with("Testing...")
            mock_stop.assert_called_once()

    def test_spinner_with_success_message(self):
        """Test spinner with success message."""
        console = Console(force_terminal=True, force_interactive=False)

        with (
            patch.object(ProgressTracker, "start"),
            patch.object(ProgressTracker, "stop") as mock_stop,
        ):
            with progress_spinner("Testing...", success_message="Done!", console=console):
                pass

            mock_stop.assert_called_once_with("Done!")


class TestOperationStatus:
    """Tests for the operation_status context manager."""

    def test_operation_status_basic(self):
        """Test operation_status context manager."""
        console = Console(force_terminal=True, force_interactive=False)

        with (
            patch.object(ProgressTracker, "start") as mock_start,
            patch.object(ProgressTracker, "stop") as mock_stop,
        ):
            with operation_status("Planning", console=console) as tracker:
                assert tracker is not None

            mock_start.assert_called_once_with("Planning...")
            mock_stop.assert_called_once()

    def test_operation_status_handles_exception(self):
        """Test operation_status handles exceptions."""
        console = Console(force_terminal=True, force_interactive=False)

        with (
            patch.object(ProgressTracker, "start"),
            patch.object(ProgressTracker, "stop") as mock_stop,
        ):
            try:
                with operation_status("Testing", console=console):
                    raise ValueError("Test error")
            except ValueError:
                pass

            mock_stop.assert_called_once()


class TestFormatHelpers:
    """Tests for format helper functions."""

    def test_format_resource_count(self):
        """Test resource count formatting."""
        result = format_resource_count(3, 10, "Applying")
        assert result == "Applying resource 3/10..."

    def test_format_resource_count_default_action(self):
        """Test resource count with default action."""
        result = format_resource_count(1, 5)
        assert result == "Processing resource 1/5..."

    def test_format_provider_status(self):
        """Test provider status formatting."""
        result = format_provider_status("proxmox", "Planning")
        assert result == "Planning proxmox..."

    def test_format_provider_status_default_action(self):
        """Test provider status with default action."""
        result = format_provider_status("kubernetes")
        assert result == "Processing kubernetes..."
