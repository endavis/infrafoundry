"""Unit tests for the 'validate' CLI command."""

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


def test_validate_success(cli_runner, mock_orchestrator):
    """Test validate command with no errors."""
    mock_orchestrator.validate.return_value = {
        "proxmox": {"errors": 0, "warnings": 0},
        "opnsense": {"errors": 0, "warnings": 0},
    }

    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(main, ["validate", "--env", "test"])

        assert result.exit_code == 0
        mock_orchestrator.validate.assert_called_once_with(
            env_name="test",
            resource_filter=None,
            verbose=False,
        )


def test_validate_with_errors(cli_runner, mock_orchestrator):
    """Test validate command with validation errors."""
    mock_orchestrator.validate.return_value = {
        "proxmox": {"errors": 2, "warnings": 1},
        "opnsense": {"errors": 0, "warnings": 0},
    }

    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(main, ["validate", "--env", "test"])

        assert result.exit_code == 1


def test_validate_with_resource_filter(cli_runner, mock_orchestrator):
    """Test validate command with resource filter."""
    mock_orchestrator.validate.return_value = {
        "proxmox": {"errors": 0, "warnings": 0},
    }

    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(
            main,
            ["validate", "--env", "test", "-r", "vm-01", "-r", "vm-02"],
        )

        assert result.exit_code == 0
        mock_orchestrator.validate.assert_called_once_with(
            env_name="test",
            resource_filter=["vm-01", "vm-02"],
            verbose=False,
        )


def test_validate_verbose(cli_runner, mock_orchestrator):
    """Test validate command with verbose flag."""
    mock_orchestrator.validate.return_value = {
        "proxmox": {"errors": 0, "warnings": 0},
    }

    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(main, ["validate", "--env", "test", "--verbose"])

        assert result.exit_code == 0
        mock_orchestrator.validate.assert_called_once_with(
            env_name="test",
            resource_filter=None,
            verbose=True,
        )


def test_validate_orchestrator_failure(cli_runner, mock_orchestrator):
    """Test validate command when orchestrator.validate raises an error."""
    mock_orchestrator.validate.side_effect = Exception("Validation failed")

    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(main, ["validate", "--env", "test"])

        assert result.exit_code == 1
        assert "Validation failed" in result.output
