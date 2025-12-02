"""Unit tests for the 'status' CLI command."""

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


def test_status_basic(cli_runner, mock_orchestrator):
    """Test basic status command."""
    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(main, ["status", "--env", "test"])

        assert result.exit_code == 0
        mock_orchestrator.status.assert_called_once_with("test")


def test_status_orchestrator_failure(cli_runner, mock_orchestrator):
    """Test status command when orchestrator.status raises an error."""
    mock_orchestrator.status.side_effect = Exception("Status check failed")

    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(main, ["status", "--env", "test"])

        assert result.exit_code == 1
        assert "Status failed" in result.output
