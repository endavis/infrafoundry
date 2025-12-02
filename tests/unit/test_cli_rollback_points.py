"""Unit tests for the 'rollback-points' CLI command."""

from datetime import datetime
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
    mock.state_manager = Mock()
    return mock


@pytest.fixture
def sample_rollback_points():
    """Sample rollback point data."""
    deployment1 = Mock()
    deployment1.id = 1
    deployment1.completed_at = datetime(2025, 1, 1, 10, 0, 0)
    deployment1.user = "alice"
    deployment1.rollback_data = {"resources": ["vm-01", "vm-02"]}
    deployment1.commit_sha = "abc123"

    deployment2 = Mock()
    deployment2.id = 2
    deployment2.completed_at = datetime(2025, 1, 2, 11, 0, 0)
    deployment2.user = "bob"
    deployment2.rollback_data = {"resources": ["vm-03"]}
    deployment2.commit_sha = None

    return [deployment1, deployment2]


def test_rollback_points_list(cli_runner, mock_orchestrator, sample_rollback_points):
    """Test rollback-points command lists available rollback points."""
    mock_orchestrator.state_manager.get_rollback_points.return_value = sample_rollback_points

    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(main, ["rollback-points", "--env", "test"])

        assert result.exit_code == 0
        assert "Rollback Points for test" in result.output
        assert "alice" in result.output
        assert "bob" in result.output
        assert "2" in result.output  # resource count
        assert "1" in result.output  # resource count
        mock_orchestrator.state_manager.get_rollback_points.assert_called_once_with(
            "test", limit=10
        )


def test_rollback_points_with_limit(cli_runner, mock_orchestrator, sample_rollback_points):
    """Test rollback-points command with custom limit."""
    mock_orchestrator.state_manager.get_rollback_points.return_value = sample_rollback_points

    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(main, ["rollback-points", "--env", "test", "--limit", "5"])

        assert result.exit_code == 0
        mock_orchestrator.state_manager.get_rollback_points.assert_called_once_with("test", limit=5)


def test_rollback_points_no_points_found(cli_runner, mock_orchestrator):
    """Test rollback-points command when no rollback points are found."""
    mock_orchestrator.state_manager.get_rollback_points.return_value = []

    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(main, ["rollback-points", "--env", "test"])

        assert result.exit_code == 0
        assert "No rollback points found for test" in result.output
        assert "Rollback points are created from successful apply operations" in result.output


def test_rollback_points_orchestrator_failure(cli_runner, mock_orchestrator):
    """Test rollback-points command when state_manager.get_rollback_points raises an error."""
    mock_orchestrator.state_manager.get_rollback_points.side_effect = Exception("Database error")

    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(main, ["rollback-points", "--env", "test"])

        assert result.exit_code == 1
        assert "Failed to list rollback points" in result.output
