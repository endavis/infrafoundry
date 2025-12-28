"""Unit tests for the 'rollback' CLI command."""

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


def test_rollback_with_auto_approve(cli_runner, mock_orchestrator):
    """Test rollback command with auto-approve."""
    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(
            main, ["infra", "rollback", "to", "--deployment-id", "123", "--auto-approve"]
        )

        assert result.exit_code == 0
        # Verify confirm_callback is passed
        call_args = mock_orchestrator.rollback.call_args
        assert call_args[1]["deployment_id"] == 123
        assert call_args[1]["auto_approve"] is True
        assert callable(call_args[1]["confirm_callback"])


def test_rollback_basic(cli_runner, mock_orchestrator):
    """Test basic rollback command (orchestrator handles confirmation)."""
    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(main, ["infra", "rollback", "to", "--deployment-id", "123"])

        assert result.exit_code == 0
        call_args = mock_orchestrator.rollback.call_args
        assert call_args[1]["deployment_id"] == 123
        assert call_args[1]["auto_approve"] is False
        assert callable(call_args[1]["confirm_callback"])


def test_rollback_orchestrator_failure(cli_runner, mock_orchestrator):
    """Test rollback command when orchestrator.rollback raises an error."""
    mock_orchestrator.rollback.side_effect = Exception("Rollback failed")

    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(
            main, ["infra", "rollback", "to", "--deployment-id", "123", "--auto-approve"]
        )

        assert result.exit_code == 1
        assert "Rollback command failed" in result.output
