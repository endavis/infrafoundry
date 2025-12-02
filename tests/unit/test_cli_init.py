"""Unit tests for the 'init' CLI command."""

from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from infrafoundry.cli.main import main


@pytest.fixture
def cli_runner():
    """Fixture for invoking CLI commands."""
    return CliRunner()


@pytest.fixture
def mock_state_manager():
    """Mock StateManager for testing."""
    from infrafoundry.core.state import StateManager

    mock = Mock(spec=StateManager)
    return mock


@pytest.mark.skip(
    reason="Click routing conflict with 'secrets init' - covered by integration tests"
)
def test_init_basic(cli_runner, mock_state_manager, monkeypatch):
    """Test basic init command."""
    with cli_runner.isolated_filesystem():
        # Clear the config repo env var to avoid interference with secrets init
        monkeypatch.delenv("INFRAFOUNDRY_CONFIG_REPO", raising=False)

        with patch("infrafoundry.core.state.StateManager", return_value=mock_state_manager):
            result = cli_runner.invoke(main, ["init"])

            assert result.exit_code == 0
            assert "Initializing InfraFoundry state database" in result.output
            assert "State database initialized successfully!" in result.output
            mock_state_manager.initialize.assert_called_once()


@pytest.mark.skip(
    reason="Click routing conflict with 'secrets init' - covered by integration tests"
)
def test_init_with_sqlite(cli_runner, mock_state_manager, monkeypatch):
    """Test init command with SQLite backend."""
    with cli_runner.isolated_filesystem():
        # Clear the config repo env var to avoid interference with secrets init
        monkeypatch.delenv("INFRAFOUNDRY_CONFIG_REPO", raising=False)
        monkeypatch.setenv("INFRAFOUNDRY_STATE_BACKEND", "sqlite")
        monkeypatch.delenv("INFRAFOUNDRY_STATE_CONNECTION", raising=False)

        with patch("infrafoundry.core.state.StateManager", return_value=mock_state_manager):
            result = cli_runner.invoke(main, ["init"])

            assert result.exit_code == 0
            assert "Using SQLite database at:" in result.output
            assert "Database location:" in result.output


@pytest.mark.skip(
    reason="Click routing conflict with 'secrets init' - covered by integration tests"
)
def test_init_with_custom_connection_string(cli_runner, mock_state_manager, monkeypatch):
    """Test init command with custom connection string."""
    with cli_runner.isolated_filesystem():
        # Clear the config repo env var to avoid interference with secrets init
        monkeypatch.delenv("INFRAFOUNDRY_CONFIG_REPO", raising=False)
        monkeypatch.setenv("INFRAFOUNDRY_STATE_CONNECTION", "postgresql://localhost/test")

        with patch("infrafoundry.core.state.StateManager", return_value=mock_state_manager):
            result = cli_runner.invoke(main, ["init"])

            assert result.exit_code == 0
            assert "State database initialized successfully!" in result.output


@pytest.mark.skip(
    reason="Click routing conflict with 'secrets init' - covered by integration tests"
)
def test_init_state_manager_failure(cli_runner, mock_state_manager, monkeypatch):
    """Test init command when StateManager.initialize raises an error."""
    from infrafoundry.core.exceptions import StateError

    with cli_runner.isolated_filesystem():
        # Clear the config repo env var to avoid interference with secrets init
        monkeypatch.delenv("INFRAFOUNDRY_CONFIG_REPO", raising=False)
        mock_state_manager.initialize.side_effect = StateError("Database connection failed")

        with patch("infrafoundry.core.state.StateManager", return_value=mock_state_manager):
            result = cli_runner.invoke(main, ["init"])

            assert result.exit_code != 0
            assert "Init command failed" in result.output
