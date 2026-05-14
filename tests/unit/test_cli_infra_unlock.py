"""Unit tests for the 'infra unlock' CLI command."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from infrafoundry.cli.main import main
from infrafoundry.core.orchestrator import Orchestrator


@pytest.fixture
def cli_runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def mock_orchestrator():
    mock = Mock(spec=Orchestrator)
    mock.state_manager = Mock()
    return mock


def _make_lock(
    environment: str = "dev",
    locked_by: str = "alice@host:1",
    expires_delta: timedelta = timedelta(hours=1),
):
    lock = Mock()
    lock.environment = environment
    lock.locked_by = locked_by
    lock.acquired_at = datetime.now(UTC)
    lock.expires_at = datetime.now(UTC) + expires_delta
    return lock


def test_unlock_active_lock_refused(cli_runner, mock_orchestrator):
    mock_orchestrator.state_manager.get_lock.return_value = _make_lock()

    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(main, ["infra", "unlock", "--env", "dev"])

    assert result.exit_code != 0
    assert "locked by alice@host:1" in result.output
    mock_orchestrator.state_manager.release_lock.assert_not_called()


def test_unlock_force_releases_active_lock(cli_runner, mock_orchestrator):
    mock_orchestrator.state_manager.get_lock.return_value = _make_lock()
    mock_orchestrator.state_manager.release_lock.return_value = True

    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(main, ["infra", "unlock", "--env", "dev", "--force", "--yes"])

    assert result.exit_code == 0, result.output
    mock_orchestrator.state_manager.release_lock.assert_called_once_with("dev", force=True)


def test_unlock_expired_lock_succeeds_without_force(cli_runner, mock_orchestrator):
    expired = _make_lock(expires_delta=timedelta(hours=-1))
    mock_orchestrator.state_manager.get_lock.return_value = expired
    mock_orchestrator.state_manager.release_lock.return_value = True

    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(main, ["infra", "unlock", "--env", "dev"])

    assert result.exit_code == 0, result.output
    assert "Expired lock" in result.output
    mock_orchestrator.state_manager.release_lock.assert_called_once_with("dev", force=True)


def test_unlock_list_shows_all_locks(cli_runner, mock_orchestrator):
    mock_orchestrator.state_manager.list_locks.return_value = [
        _make_lock(environment="dev"),
        _make_lock(environment="prod", expires_delta=timedelta(hours=-1)),
    ]

    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        # Wider terminal so rich does not squeeze the auto-sized columns and we
        # can assert on the full rendered output.
        result = cli_runner.invoke(main, ["infra", "unlock", "--list"], env={"COLUMNS": "200"})

    assert result.exit_code == 0, result.output
    assert "dev" in result.output
    assert "prod" in result.output
    assert "active" in result.output
    assert "expired" in result.output
    # Timestamps must render with full HH:MM:SS UTC, not be truncated to a date.
    # We assert the date and time-with-UTC fragments separately because Rich's
    # table renderer wraps the timestamp across two cell rows when the column
    # auto-sizes narrower than the timestamp width — e.g. under pytest-xdist
    # workers where COLUMNS=200 isn't honored by Rich's terminal-size probe.
    # In the wrapped case the rendered output looks like:
    #
    #     │ 2026-05-14        │ ...
    #     │ 02:24:11 UTC      │ ...
    #
    # so the date and time are separated by table border characters (│) and
    # other-row padding, not just whitespace — a single contiguous regex can't
    # bridge that without binding the test to Rich's internal rendering.
    #
    # The second assertion is load-bearing for the regression we care about:
    # a bare str(datetime) (e.g. "2026-05-14 02:24:11.123456+00:00") emits
    # "+00:00" instead of literal "UTC", so the time-with-UTC pattern fails.
    assert re.search(r"\d{4}-\d{2}-\d{2}", result.output)
    assert re.search(r"\d{2}:\d{2}:\d{2}\s+UTC", result.output)


def test_unlock_nonexistent_env_reports_no_lock(cli_runner, mock_orchestrator):
    mock_orchestrator.state_manager.get_lock.return_value = None

    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(main, ["infra", "unlock", "--env", "dev"])

    assert result.exit_code == 0, result.output
    assert "No lock held" in result.output
    mock_orchestrator.state_manager.release_lock.assert_not_called()


def test_unlock_without_env_or_list_errors(cli_runner, mock_orchestrator):
    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(main, ["infra", "unlock"])

    assert result.exit_code != 0
    assert "--env" in result.output
