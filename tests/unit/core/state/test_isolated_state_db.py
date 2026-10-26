"""The test suite never touches the developer's state database (#1110).

``tests/conftest.py`` points ``INFRAFOUNDRY_STATE_HOME`` at a fresh directory for
every test. These tests check that a default ``StateManager`` lands there and
that the shell's state settings do not reach the tests.
"""

from __future__ import annotations

import os
from pathlib import Path

from infrafoundry.core.state import StateManager


def _default_database() -> Path:
    manager = StateManager()
    try:
        database = manager.engine.url.database
        assert database is not None
        return Path(database)
    finally:
        manager.cleanup()


def test_default_state_db_is_under_the_test_state_home() -> None:
    database = _default_database()

    assert database.parent == Path(os.environ["INFRAFOUNDRY_STATE_HOME"])
    assert Path.home() / ".infrafoundry" not in database.parents


def test_state_connection_settings_from_the_shell_are_cleared() -> None:
    assert "INFRAFOUNDRY_STATE_BACKEND" not in os.environ
    assert "INFRAFOUNDRY_STATE_CONNECTION" not in os.environ
