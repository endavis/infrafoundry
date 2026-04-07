"""Unit tests for the environment_lock context manager."""

from __future__ import annotations

import tempfile
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from infrafoundry.core.events.types import EventType
from infrafoundry.core.exceptions import LockAcquisitionError
from infrafoundry.core.state import StateManager
from infrafoundry.core.state.lock_context import environment_lock


@pytest.fixture
def temp_db():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield f"sqlite:///{Path(tmpdir) / 'lock_ctx.db'}"


@pytest.fixture
def state_manager(temp_db):
    manager = StateManager(connection_string=temp_db)
    manager.initialize()
    return manager


class RecordingEventManager:
    """Minimal stub with an ``emit_event`` method matching EventManager."""

    def __init__(self) -> None:
        self.events: list[tuple[EventType, str, dict[str, Any]]] = []

    def emit_event(self, event_type: EventType, env_name: str, payload: dict[str, Any]) -> None:
        self.events.append((event_type, env_name, payload))


class TestEnvironmentLock:
    def test_context_acquires_and_releases(self, state_manager: StateManager) -> None:
        with environment_lock(state_manager, "dev", ttl=60, locked_by="me@h:1"):
            assert state_manager.get_lock("dev") is not None
        assert state_manager.get_lock("dev") is None

    def test_context_releases_on_exception(self, state_manager: StateManager) -> None:
        with (
            pytest.raises(RuntimeError, match="boom"),
            environment_lock(state_manager, "dev", ttl=60, locked_by="me@h:1"),
        ):
            raise RuntimeError("boom")
        assert state_manager.get_lock("dev") is None

    def test_context_timeout_polls_and_raises(self, state_manager: StateManager) -> None:
        # Pre-seed a lock held by another owner.
        state_manager.acquire_lock("dev", ttl_seconds=60, locked_by="holder@h:9")
        start = time.monotonic()
        with (
            pytest.raises(LockAcquisitionError),
            environment_lock(
                state_manager,
                "dev",
                ttl=60,
                locked_by="me@h:1",
                timeout=1,
                poll_interval=0.2,
            ),
        ):
            pytest.fail("should not enter body")
        elapsed = time.monotonic() - start
        # Should have waited at least ~1 second before timing out.
        assert elapsed >= 0.9

    def test_context_timeout_succeeds_on_release(self, state_manager: StateManager) -> None:
        state_manager.acquire_lock("dev", ttl_seconds=60, locked_by="holder@h:9")

        def release_soon() -> None:
            time.sleep(0.4)
            state_manager.release_lock("dev", force=True)

        t = threading.Thread(target=release_soon)
        t.start()
        try:
            with environment_lock(
                state_manager,
                "dev",
                ttl=60,
                locked_by="me@h:1",
                timeout=5,
                poll_interval=0.1,
            ):
                assert state_manager.get_lock("dev").locked_by == "me@h:1"
        finally:
            t.join()
        assert state_manager.get_lock("dev") is None

    def test_skip_lock_env_var(
        self, state_manager: StateManager, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("INFRAFOUNDRY_SKIP_LOCK", "1")
        # Even with an active lock pre-held, skip should bypass it entirely.
        state_manager.acquire_lock("dev", ttl_seconds=60, locked_by="other@h:2")
        with environment_lock(state_manager, "dev", ttl=60, locked_by="me@h:1"):
            # The existing lock is untouched.
            lock = state_manager.get_lock("dev")
            assert lock is not None
            assert lock.locked_by == "other@h:2"
        # Still there after.
        assert state_manager.get_lock("dev") is not None

    def test_lock_events_emitted(self, state_manager: StateManager) -> None:
        ev = RecordingEventManager()
        with environment_lock(
            state_manager,
            "dev",
            ttl=60,
            locked_by="me@h:1",
            event_manager=ev,  # type: ignore[arg-type]
        ):
            pass
        types = [e[0] for e in ev.events]
        assert EventType.LOCK_ACQUIRED in types
        assert EventType.LOCK_RELEASED in types

    def test_lock_timeout_event_emitted(self, state_manager: StateManager) -> None:
        state_manager.acquire_lock("dev", ttl_seconds=60, locked_by="holder@h:9")
        ev = RecordingEventManager()
        with (
            pytest.raises(LockAcquisitionError),
            environment_lock(
                state_manager,
                "dev",
                ttl=60,
                locked_by="me@h:1",
                timeout=1,
                poll_interval=0.2,
                event_manager=ev,  # type: ignore[arg-type]
            ),
        ):
            pass
        types = [e[0] for e in ev.events]
        assert EventType.LOCK_TIMEOUT in types
