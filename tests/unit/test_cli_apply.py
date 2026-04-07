"""Unit tests for the 'apply' CLI command."""

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


def test_apply_with_confirmation(cli_runner, mock_orchestrator):
    """Test apply command with user confirmation."""
    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        # User confirms
        result = cli_runner.invoke(main, ["infra", "apply", "--env", "test"], input="y\n")

        assert result.exit_code == 0
        assert "About to apply infrastructure for environment: test" in result.output
        assert "Apply complete!" in result.output
        mock_orchestrator.apply.assert_called_once_with(
            "test",
            auto_approve=True,  # Becomes True after confirmation
            resource_filter=None,
            parallel=False,
            max_workers=4,
            package_filter=None,
            lock_timeout=0,
            lock_ttl=3600,
        )


def test_apply_user_cancels(cli_runner, mock_orchestrator):
    """Test apply command when user cancels confirmation."""
    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        # User cancels
        result = cli_runner.invoke(main, ["infra", "apply", "--env", "test"], input="n\n")

        assert result.exit_code == 0
        assert "Apply cancelled." in result.output
        mock_orchestrator.apply.assert_not_called()


def test_apply_with_auto_approve(cli_runner, mock_orchestrator):
    """Test apply command with auto-approve flag."""
    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(main, ["infra", "apply", "--env", "test", "--auto-approve"])

        assert result.exit_code == 0
        assert "Apply complete!" in result.output
        mock_orchestrator.apply.assert_called_once_with(
            "test",
            auto_approve=True,
            resource_filter=None,
            parallel=False,
            max_workers=4,
            package_filter=None,
            lock_timeout=0,
            lock_ttl=3600,
        )


def test_apply_with_resource_filter(cli_runner, mock_orchestrator):
    """Test apply command with resource filter."""
    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(
            main,
            ["infra", "apply", "--env", "test", "--auto-approve", "-r", "vm-01", "-r", "vm-02"],
        )

        assert result.exit_code == 0
        mock_orchestrator.apply.assert_called_once_with(
            "test",
            auto_approve=True,
            resource_filter=["vm-01", "vm-02"],
            parallel=False,
            max_workers=4,
            package_filter=None,
            lock_timeout=0,
            lock_ttl=3600,
        )


def test_apply_with_parallel(cli_runner, mock_orchestrator):
    """Test apply command with parallel execution."""
    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(
            main,
            [
                "infra",
                "apply",
                "--env",
                "test",
                "--auto-approve",
                "--parallel",
                "--max-workers",
                "8",
            ],
        )

        assert result.exit_code == 0
        mock_orchestrator.apply.assert_called_once_with(
            "test",
            auto_approve=True,
            resource_filter=None,
            parallel=True,
            max_workers=8,
            package_filter=None,
            lock_timeout=0,
            lock_ttl=3600,
        )


def test_apply_orchestrator_failure(cli_runner, mock_orchestrator):
    """Test apply command when orchestrator.apply raises an error."""
    mock_orchestrator.apply.side_effect = Exception("Apply failed")

    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(main, ["infra", "apply", "--env", "test", "--auto-approve"])

        assert result.exit_code == 1
        assert "Apply failed" in result.output
