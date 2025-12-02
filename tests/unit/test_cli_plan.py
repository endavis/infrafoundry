"""Unit tests for the 'plan' CLI command."""

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


def test_plan_basic(cli_runner, mock_orchestrator):
    """Test basic plan command."""
    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(main, ["plan", "--env", "test"])

        assert result.exit_code == 0
        assert "Plan generated successfully!" in result.output
        assert "Generated files are in: generated/" in result.output
        mock_orchestrator.plan.assert_called_once_with(
            "test",
            dry_run=False,
            resource_filter=None,
            enforce_policies=False,
        )


def test_plan_with_dry_run(cli_runner, mock_orchestrator):
    """Test plan command with dry-run flag."""
    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(main, ["plan", "--env", "test", "--dry-run"])

        assert result.exit_code == 0
        assert "Dry run complete. No files generated." in result.output
        mock_orchestrator.plan.assert_called_once_with(
            "test",
            dry_run=True,
            resource_filter=None,
            enforce_policies=False,
        )


def test_plan_with_resource_filter(cli_runner, mock_orchestrator):
    """Test plan command with resource filter."""
    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(
            main,
            ["plan", "--env", "test", "-r", "vm-01", "-r", "vm-02"],
        )

        assert result.exit_code == 0
        mock_orchestrator.plan.assert_called_once_with(
            "test",
            dry_run=False,
            resource_filter=["vm-01", "vm-02"],
            enforce_policies=False,
        )


def test_plan_with_enforce_policies(cli_runner, mock_orchestrator):
    """Test plan command with enforce policies flag."""
    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(
            main,
            ["plan", "--env", "test", "--enforce-policies"],
        )

        assert result.exit_code == 0
        mock_orchestrator.plan.assert_called_once_with(
            "test",
            dry_run=False,
            resource_filter=None,
            enforce_policies=True,
        )


def test_plan_orchestrator_failure(cli_runner, mock_orchestrator):
    """Test plan command when orchestrator.plan raises an error."""
    mock_orchestrator.plan.side_effect = Exception("Plan failed")

    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(main, ["plan", "--env", "test"])

        assert result.exit_code == 1
        assert "Plan failed" in result.output
