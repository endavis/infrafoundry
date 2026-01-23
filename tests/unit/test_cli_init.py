"""Unit tests for the 'state init' CLI command."""

from unittest.mock import Mock, patch

from click.testing import CliRunner

from infrafoundry.cli.main import main


def test_init_basic(monkeypatch):
    """Test basic state init command."""
    runner = CliRunner()
    mock_state_manager = Mock()

    with runner.isolated_filesystem():
        monkeypatch.delenv("INFRAFOUNDRY_CONFIG_REPO", raising=False)

        with patch(
            "infrafoundry.core.state.StateManager",
            return_value=mock_state_manager,
        ):
            result = runner.invoke(main, ["state", "init"])

            assert result.exit_code == 0, result.output
            assert "Initializing InfraFoundry state database" in result.output
            assert "State database initialized successfully!" in result.output
            mock_state_manager.initialize.assert_called_once()


def test_init_with_sqlite(monkeypatch):
    """Test state init command with SQLite backend."""
    runner = CliRunner()
    mock_state_manager = Mock()

    with runner.isolated_filesystem():
        monkeypatch.delenv("INFRAFOUNDRY_CONFIG_REPO", raising=False)
        monkeypatch.setenv("INFRAFOUNDRY_STATE_BACKEND", "sqlite")
        monkeypatch.delenv("INFRAFOUNDRY_STATE_CONNECTION", raising=False)

        with patch(
            "infrafoundry.core.state.StateManager",
            return_value=mock_state_manager,
        ):
            result = runner.invoke(main, ["state", "init"])

            assert result.exit_code == 0, result.output
            assert "Using SQLite database at:" in result.output
            assert "Database location:" in result.output


def test_init_with_custom_connection_string(monkeypatch):
    """Test state init command with custom connection string."""
    runner = CliRunner()
    mock_state_manager = Mock()

    with runner.isolated_filesystem():
        monkeypatch.delenv("INFRAFOUNDRY_CONFIG_REPO", raising=False)
        monkeypatch.setenv("INFRAFOUNDRY_STATE_CONNECTION", "postgresql://localhost/test")

        with patch(
            "infrafoundry.core.state.StateManager",
            return_value=mock_state_manager,
        ):
            result = runner.invoke(main, ["state", "init"])

            assert result.exit_code == 0, result.output
            assert "State database initialized successfully!" in result.output


def test_init_state_manager_failure(monkeypatch):
    """Test state init command when StateManager.initialize raises an error."""
    from infrafoundry.core.exceptions import StateError

    runner = CliRunner()
    mock_state_manager = Mock()

    with runner.isolated_filesystem():
        monkeypatch.delenv("INFRAFOUNDRY_CONFIG_REPO", raising=False)
        mock_state_manager.initialize.side_effect = StateError("Database connection failed")

        with patch(
            "infrafoundry.core.state.StateManager",
            return_value=mock_state_manager,
        ):
            result = runner.invoke(main, ["state", "init"])

            assert result.exit_code != 0
            assert "Init command failed" in result.output
