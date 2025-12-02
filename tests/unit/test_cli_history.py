"""Unit tests for the 'history' CLI command."""

from datetime import datetime
from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from infrafoundry.cli.main import main
from infrafoundry.core.orchestrator import Orchestrator
from infrafoundry.core.state import DeploymentStatus


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
def sample_deployments():
    """Sample deployment history."""
    deployment1 = Mock()
    deployment1.id = 1
    deployment1.environment = "test"
    deployment1.command = "apply"
    deployment1.status = DeploymentStatus.COMPLETED
    deployment1.dry_run = False
    deployment1.started_at = datetime(2025, 1, 1, 10, 0, 0)
    deployment1.user = "alice"

    deployment2 = Mock()
    deployment2.id = 2
    deployment2.environment = "prod"
    deployment2.command = "plan"
    deployment2.status = DeploymentStatus.COMPLETED
    deployment2.dry_run = True
    deployment2.started_at = datetime(2025, 1, 2, 11, 0, 0)
    deployment2.user = "bob"

    return [deployment1, deployment2]


def test_history_basic(cli_runner, mock_orchestrator, sample_deployments):
    """Test basic history command."""
    mock_orchestrator.state_manager.get_deployment_history.return_value = sample_deployments

    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(main, ["history"])

        assert result.exit_code == 0
        assert "Deployment History" in result.output
        assert "test" in result.output
        assert "prod" in result.output
        assert "apply" in result.output
        assert "plan" in result.output
        mock_orchestrator.state_manager.get_deployment_history.assert_called_once_with(
            environment=None,
            command=None,
            status=None,
            limit=50,
            exclude_dry_run=False,
        )


def test_history_filter_by_env(cli_runner, mock_orchestrator, sample_deployments):
    """Test history command with environment filter."""
    mock_orchestrator.state_manager.get_deployment_history.return_value = [sample_deployments[0]]

    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(main, ["history", "--env", "test"])

        assert result.exit_code == 0
        mock_orchestrator.state_manager.get_deployment_history.assert_called_once_with(
            environment="test",
            command=None,
            status=None,
            limit=50,
            exclude_dry_run=False,
        )


def test_history_filter_by_command(cli_runner, mock_orchestrator, sample_deployments):
    """Test history command with command filter."""
    mock_orchestrator.state_manager.get_deployment_history.return_value = [sample_deployments[0]]

    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(main, ["history", "--command", "apply"])

        assert result.exit_code == 0
        mock_orchestrator.state_manager.get_deployment_history.assert_called_once_with(
            environment=None,
            command="apply",
            status=None,
            limit=50,
            exclude_dry_run=False,
        )


def test_history_filter_by_status(cli_runner, mock_orchestrator, sample_deployments):
    """Test history command with status filter."""
    mock_orchestrator.state_manager.get_deployment_history.return_value = sample_deployments

    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(main, ["history", "--status", "completed"])

        assert result.exit_code == 0
        call_args = mock_orchestrator.state_manager.get_deployment_history.call_args[1]
        assert call_args["status"] == DeploymentStatus.COMPLETED


def test_history_with_limit(cli_runner, mock_orchestrator, sample_deployments):
    """Test history command with limit."""
    mock_orchestrator.state_manager.get_deployment_history.return_value = sample_deployments

    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(main, ["history", "--limit", "10"])

        assert result.exit_code == 0
        mock_orchestrator.state_manager.get_deployment_history.assert_called_once_with(
            environment=None,
            command=None,
            status=None,
            limit=10,
            exclude_dry_run=False,
        )


def test_history_exclude_dry_runs(cli_runner, mock_orchestrator, sample_deployments):
    """Test history command excluding dry runs."""
    mock_orchestrator.state_manager.get_deployment_history.return_value = [sample_deployments[0]]

    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(main, ["history", "--exclude-dry-runs"])

        assert result.exit_code == 0
        mock_orchestrator.state_manager.get_deployment_history.assert_called_once_with(
            environment=None,
            command=None,
            status=None,
            limit=50,
            exclude_dry_run=True,
        )


def test_history_no_deployments(cli_runner, mock_orchestrator):
    """Test history command when no deployments are found."""
    mock_orchestrator.state_manager.get_deployment_history.return_value = []

    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(main, ["history"])

        assert result.exit_code == 0
        assert "No deployment history found" in result.output
        assert "Run 'infra init'" in result.output
