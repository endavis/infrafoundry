"""Unit tests for the 'drift' CLI command."""

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


def test_drift_no_drift_detected(cli_runner, mock_orchestrator):
    """Test drift detect command when no drift is detected."""
    mock_orchestrator.detect_drift.return_value = {
        "proxmox": {"has_changes": False},
        "opnsense": {"has_changes": False},
    }

    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(main, ["drift", "detect", "--env", "test"])

        assert result.exit_code == 0
        assert "No drift detected" in result.output
        mock_orchestrator.detect_drift.assert_called_once_with("test")


def test_drift_detected(cli_runner, mock_orchestrator):
    """Test drift detect command when drift is detected."""
    mock_orchestrator.detect_drift.return_value = {
        "proxmox": {
            "has_changes": True,
            "to_add": 2,
            "to_change": 1,
            "to_destroy": 0,
            "summary": "3 resources to change",
        },
        "opnsense": {"has_changes": False},
    }

    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(main, ["drift", "detect", "--env", "test"])

        assert result.exit_code == 0
        assert "Drift detected!" in result.output
        assert "Run 'infra plan' to see detailed changes" in result.output


def test_drift_orchestrator_failure(cli_runner, mock_orchestrator):
    """Test drift detect command when orchestrator.detect_drift raises an error."""
    mock_orchestrator.detect_drift.side_effect = Exception("Drift detection failed")

    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(main, ["drift", "detect", "--env", "test"])

        assert result.exit_code == 1
        assert "Drift detection failed" in result.output
