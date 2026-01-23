"""Unit tests for the 'state' CLI commands."""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from infrafoundry.cli.main import main
from infrafoundry.core.orchestrator import Orchestrator
from infrafoundry.core.state import StateManager


@pytest.fixture
def cli_runner():
    """Fixture for invoking CLI commands."""
    return CliRunner()


@pytest.fixture
def mock_orchestrator(tmp_path):
    """Mock orchestrator with a mock state manager."""
    mock_state_manager = Mock(spec=StateManager)
    # Explicitly mock engine and engine.url
    mock_state_manager.engine = Mock()
    mock_state_manager.engine.url = Mock()
    mock_state_manager.engine.url.drivername = "sqlite"
    mock_state_manager.engine.url.database = str(tmp_path / ".infrafoundry" / "state.db")

    # Ensure the mock state db path exists for testing copy operations
    (tmp_path / ".infrafoundry").mkdir(exist_ok=True)
    (tmp_path / ".infrafoundry" / "state.db").touch()

    mock_orchestrator = Mock(spec=Orchestrator)
    mock_orchestrator.state_manager = mock_state_manager
    return mock_orchestrator


def test_state_backup_basic(cli_runner, mock_orchestrator, tmp_path):
    """Test basic state backup without generated directory."""
    # Patch the _get_orchestrator function to return our mock orchestrator
    with (
        patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator),
        patch("shutil.copy2") as mock_copy2,
    ):
        result = cli_runner.invoke(main, ["state", "backup", "-o", str(tmp_path)])

        assert result.exit_code == 0
        assert "State database backed up to:" in result.output
        mock_copy2.assert_called_once()
        # Compare Path objects directly or their string representations
        assert Path(mock_orchestrator.state_manager.engine.url.database) == Path(
            mock_copy2.call_args[0][0]
        )
        assert tmp_path.joinpath("infrafoundry_state_").stem in str(mock_copy2.call_args[0][1])


def test_state_backup_with_generated(cli_runner, mock_orchestrator, tmp_path):
    """Test state backup including generated directory."""
    with cli_runner.isolated_filesystem() as td:
        cwd = Path(td)
        # Create a mock generated directory in the current working directory (isolated)
        (cwd / "generated").mkdir()
        (cwd / "generated" / "file.txt").touch()

        with (
            patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator),
            patch("shutil.copy2") as mock_copy2,
            patch("shutil.make_archive") as mock_make_archive,
        ):
            # Use tmp_path for output to keep it separate, or use cwd
            result = cli_runner.invoke(main, ["state", "backup", "-o", str(tmp_path), "-g"])

            assert result.exit_code == 0
            assert "State database backed up to:" in result.output
            assert "'generated/' directory archived to:" in result.output
            mock_copy2.assert_called_once()
            mock_make_archive.assert_called_once()
            # Check root_dir and base_dir arguments for make_archive
            # Path.cwd() inside the command will match cwd here
            assert str(cwd) == mock_make_archive.call_args[1]["root_dir"]
            assert mock_make_archive.call_args[1]["base_dir"] == "generated"


def test_state_backup_state_db_not_found(cli_runner, mock_orchestrator, tmp_path):
    """Test state backup when state.db file does not exist."""
    # Remove the mocked state.db file
    (tmp_path / ".infrafoundry" / "state.db").unlink()

    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(main, ["state", "backup", "-o", str(tmp_path)])

        assert result.exit_code == 0
        assert "InfraFoundry state database file not found." in result.output


def test_state_backup_output_dir_creation(cli_runner, mock_orchestrator, tmp_path):
    """Test state backup creates output directory if it doesn't exist."""
    non_existent_dir = tmp_path / "non_existent_backup_dir"
    assert not non_existent_dir.exists()

    with (
        patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator),
        patch("shutil.copy2"),
    ):
        result = cli_runner.invoke(main, ["state", "backup", "-o", str(non_existent_dir)])

        assert result.exit_code == 0
        assert non_existent_dir.is_dir()  # Assert directory was created


def test_state_backup_failure(cli_runner, mock_orchestrator, tmp_path):
    """Test state backup handles copy failure gracefully."""
    with (
        patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator),
        patch("shutil.copy2", side_effect=OSError("Permission denied")),
    ):
        result = cli_runner.invoke(main, ["state", "backup", "-o", str(tmp_path)])

        assert result.exit_code == 1  # Expect failure
        assert "State backup failed: Permission denied" in result.output


def test_state_backup_non_sqlite(cli_runner, mock_orchestrator, tmp_path):
    """Test state backup with non-SQLite database (e.g., PostgreSQL)."""
    mock_orchestrator.state_manager.engine.url.drivername = "postgresql"

    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(main, ["state", "backup", "-o", str(tmp_path)])

        assert result.exit_code == 0
        assert (
            "InfraFoundry state is not a local SQLite database. Skipping file backup."
            in result.output
        )
        assert "State backup failed" not in result.output  # Should not fail
