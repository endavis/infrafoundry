"""Unit tests for the 'destroy' CLI command."""

from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from infrafoundry.cli.main import main
from infrafoundry.core.orchestrator import Orchestrator


@pytest.fixture
def cli_runner():
    """Fixture for invoking CLI commands."""
    return CliRunner()


@pytest.fixture
def mock_orchestrator():
    """Mock orchestrator for testing."""
    mock = Mock(spec=Orchestrator)
    return mock


def test_destroy_basic(cli_runner, mock_orchestrator):
    """Test basic destroy command (orchestrator handles confirmation)."""
    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(main, ["infra", "destroy", "--env", "test"])

        assert result.exit_code == 0
        assert "Destroy complete!" in result.output
        # Verify confirm_callback is passed
        call_args = mock_orchestrator.destroy.call_args
        assert call_args[0] == ("test",)
        assert call_args[1]["auto_approve"] is False
        assert call_args[1]["resource_filter"] is None
        assert callable(call_args[1]["confirm_callback"])


def test_destroy_with_auto_approve(cli_runner, mock_orchestrator):
    """Test destroy command with auto-approve flag."""
    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(main, ["infra", "destroy", "--env", "test", "--auto-approve"])

        assert result.exit_code == 0
        assert "Destroy complete!" in result.output
        call_args = mock_orchestrator.destroy.call_args
        assert call_args[1]["auto_approve"] is True


def test_destroy_with_resource_filter(cli_runner, mock_orchestrator):
    """Test destroy command with resource filter."""
    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(
            main,
            ["infra", "destroy", "--env", "test", "--auto-approve", "-r", "vm-01", "-r", "vm-02"],
        )

        assert result.exit_code == 0
        call_args = mock_orchestrator.destroy.call_args
        assert call_args[1]["resource_filter"] == ["vm-01", "vm-02"]


def test_destroy_orchestrator_failure(cli_runner, mock_orchestrator):
    """Test destroy command when orchestrator.destroy raises an error."""
    mock_orchestrator.destroy.side_effect = Exception("Destroy failed")

    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(main, ["infra", "destroy", "--env", "test", "--auto-approve"])

        assert result.exit_code == 1
        assert "Destroy failed" in result.output
