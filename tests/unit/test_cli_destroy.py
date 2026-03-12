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


def test_destroy_confirms_then_auto_approves(cli_runner, mock_orchestrator):
    """Test that confirming at CLI level passes auto_approve=True to orchestrator."""
    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(main, ["infra", "destroy", "--env", "test"], input="y\n")

        assert result.exit_code == 0
        assert "Destroy complete!" in result.output
        call_args = mock_orchestrator.destroy.call_args
        assert call_args[0] == ("test",)
        assert call_args[1]["auto_approve"] is True
        assert call_args[1]["resource_filter"] is None
        assert "confirm_callback" not in call_args[1]


def test_destroy_cancelled(cli_runner, mock_orchestrator):
    """Test that declining confirmation cancels destroy."""
    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(main, ["infra", "destroy", "--env", "test"], input="n\n")

        assert result.exit_code == 0
        assert "Destroy cancelled." in result.output
        mock_orchestrator.destroy.assert_not_called()


def test_destroy_with_auto_approve(cli_runner, mock_orchestrator):
    """Test destroy command with auto-approve flag skips confirmation."""
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


def test_destroy_shows_resource_names_in_prompt(cli_runner, mock_orchestrator):
    """Test that resource names are shown in the confirmation prompt."""
    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(
            main,
            ["infra", "destroy", "--env", "test", "-r", "vm-01", "-r", "vm-02"],
            input="y\n",
        )

        assert result.exit_code == 0
        assert "vm-01" in result.output
        assert "vm-02" in result.output


def test_destroy_orchestrator_failure(cli_runner, mock_orchestrator):
    """Test destroy command when orchestrator.destroy raises an error."""
    mock_orchestrator.destroy.side_effect = Exception("Destroy failed")

    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(main, ["infra", "destroy", "--env", "test", "--auto-approve"])

        assert result.exit_code == 1
        assert "Destroy failed" in result.output
