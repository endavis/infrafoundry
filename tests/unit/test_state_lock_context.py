"""Unit tests for the environment_lock context manager."""

from __future__ import annotations

import tempfile
import threading
import time
from datetime import UTC
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


def _as_utc(value):
    """Normalize a (possibly naive) datetime to UTC for comparison."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


class TestEnvironmentLockHeartbeat:
    """Tests for the background heartbeat that auto-extends the lock."""

    def test_heartbeat_extends_lock_during_hold(self, state_manager: StateManager) -> None:
        # ttl=3 => heartbeat interval == 1s. Sleep 2.5s so at least two
        # heartbeats fire and we can observe the expiration advance past
        # the initial value.
        with environment_lock(state_manager, "dev", ttl=3, locked_by="me@h:1"):
            initial = state_manager.get_lock("dev")
            assert initial is not None
            initial_expires = _as_utc(initial.expires_at)
            time.sleep(2.5)
            current = state_manager.get_lock("dev")
            assert current is not None
            current_expires = _as_utc(current.expires_at)
            assert current_expires > initial_expires
        assert state_manager.get_lock("dev") is None

    def test_heartbeat_stops_on_context_exit(self, state_manager: StateManager) -> None:
        calls: list[tuple[str, str]] = []
        original = state_manager.extend_lock

        def recording_extend(env_name, locked_by, new_expires_at):
            calls.append((env_name, locked_by))
            return original(env_name, locked_by, new_expires_at)

        state_manager.extend_lock = recording_extend  # type: ignore[method-assign]
        try:
            with environment_lock(state_manager, "dev", ttl=3, locked_by="me@h:1"):
                time.sleep(1.3)
            calls_after_exit = len(calls)
            # Give the daemon thread some extra time; if it's really
            # stopped, no further DB writes should occur.
            time.sleep(2.0)
            assert len(calls) == calls_after_exit
        finally:
            state_manager.extend_lock = original  # type: ignore[method-assign]

    def test_heartbeat_failure_emits_event(self, state_manager: StateManager) -> None:
        ev = RecordingEventManager()
        original = state_manager.extend_lock
        state_manager.extend_lock = (  # type: ignore[method-assign]
            lambda env_name, locked_by, new_expires_at: False
        )
        try:
            with environment_lock(
                state_manager,
                "dev",
                ttl=3,
                locked_by="me@h:1",
                event_manager=ev,  # type: ignore[arg-type]
            ):
                # Wait long enough for at least one heartbeat iteration.
                time.sleep(1.3)
                # Apply body continues uninterrupted — no exception raised.
                assert state_manager.get_lock("dev") is not None
        finally:
            state_manager.extend_lock = original  # type: ignore[method-assign]

        types = [e[0] for e in ev.events]
        assert EventType.LOCK_HEARTBEAT_FAILED in types

    def test_heartbeat_continues_after_transient_failure(self, state_manager: StateManager) -> None:
        ev = RecordingEventManager()
        original = state_manager.extend_lock
        call_count = {"n": 0}

        def flaky_extend(env_name, locked_by, new_expires_at):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return False  # transient failure
            return original(env_name, locked_by, new_expires_at)

        state_manager.extend_lock = flaky_extend  # type: ignore[method-assign]
        try:
            with environment_lock(
                state_manager,
                "dev",
                ttl=3,
                locked_by="me@h:1",
                event_manager=ev,  # type: ignore[arg-type]
            ):
                # Wait long enough for at least two heartbeat iterations
                # so we see both the failure and a subsequent success.
                time.sleep(2.3)
        finally:
            state_manager.extend_lock = original  # type: ignore[method-assign]

        # At least one failure event emitted, and at least two calls made.
        failure_events = [e for e in ev.events if e[0] == EventType.LOCK_HEARTBEAT_FAILED]
        assert len(failure_events) >= 1
        assert call_count["n"] >= 2
        # Lock was released cleanly.
        assert state_manager.get_lock("dev") is None

    def test_long_running_lock_does_not_self_evict(self, state_manager: StateManager) -> None:
        # ttl=2 => heartbeat every ~0.67s. Hold for 4s (> 2 * ttl) so
        # without a heartbeat the lock would expire mid-hold. With
        # heartbeat, it must remain continuously active.
        with environment_lock(state_manager, "dev", ttl=2, locked_by="me@h:1"):
            deadline = time.monotonic() + 4.0
            while time.monotonic() < deadline:
                lock = state_manager.get_lock("dev")
                assert lock is not None
                # Lock's expires_at must remain in the future throughout.
                from datetime import datetime

                now = datetime.now(UTC)
                expires = _as_utc(lock.expires_at)
                assert expires > now
                time.sleep(0.3)
        assert state_manager.get_lock("dev") is None
