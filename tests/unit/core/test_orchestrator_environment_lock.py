"""``Orchestrator.environment_lock`` holds the deployment lock for a command (#1655)."""

from __future__ import annotations

import tempfile
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from infrafoundry.core.exceptions import LockAcquisitionError
from infrafoundry.core.orchestrator import Orchestrator
from infrafoundry.core.state import StateManager

pytestmark = pytest.mark.unit


@pytest.fixture
def state_manager() -> Iterator[StateManager]:
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = StateManager(connection_string=f"sqlite:///{Path(tmpdir) / 'lock.db'}")
        manager.initialize()
        yield manager


def test_environment_lock_acquires_and_releases(state_manager: StateManager) -> None:
    orchestrator = Orchestrator(MagicMock(), state_manager=state_manager)
    with orchestrator.environment_lock("dev"):
        assert state_manager.get_lock("dev") is not None
    assert state_manager.get_lock("dev") is None


def test_environment_lock_releases_when_the_body_raises(state_manager: StateManager) -> None:
    orchestrator = Orchestrator(MagicMock(), state_manager=state_manager)
    with pytest.raises(RuntimeError), orchestrator.environment_lock("dev"):
        raise RuntimeError("boom")
    assert state_manager.get_lock("dev") is None


def test_environment_lock_fails_fast_when_held(state_manager: StateManager) -> None:
    orchestrator = Orchestrator(MagicMock(), state_manager=state_manager)
    with (
        orchestrator.environment_lock("dev"),
        pytest.raises(LockAcquisitionError),
        orchestrator.environment_lock("dev"),
    ):
        pass
