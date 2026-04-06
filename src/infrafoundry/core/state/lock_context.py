"""Context manager for acquiring and releasing deployment locks.

Provides :func:`environment_lock`, the public entrypoint used by
:class:`Orchestrator` to wrap ``apply`` and ``destroy`` in an exclusive
per-environment lock backed by :class:`LockRepository`.
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING

from infrafoundry.core.events.types import EventType
from infrafoundry.core.exceptions import LockAcquisitionError

if TYPE_CHECKING:
    from infrafoundry.core.events import EventManager
    from infrafoundry.core.state.models import DeploymentLock
    from infrafoundry.core.state.state_manager import StateManager


logger = logging.getLogger(__name__)

SKIP_LOCK_ENV = "INFRAFOUNDRY_SKIP_LOCK"


@contextmanager
def environment_lock(
    state_manager: StateManager,
    env_name: str,
    ttl: int,
    locked_by: str,
    deployment_id: int | None = None,
    timeout: int = 0,
    poll_interval: float = 2.0,
    event_manager: EventManager | None = None,
) -> Iterator[None]:
    """Acquire an exclusive lock on ``env_name`` for the duration of the block.

    If ``timeout`` is 0 (default), acquisition fails fast: any existing
    active lock immediately raises :class:`LockAcquisitionError`. If ``timeout``
    is positive, the call polls at ``poll_interval`` seconds until it either
    acquires the lock or the timeout elapses (in which case it emits a
    ``LOCK_TIMEOUT`` event and re-raises).

    The lock is always released in the ``finally`` block, even when the wrapped
    body raises. ``force=True`` is used on release so the release always
    succeeds regardless of TTL takeover semantics.

    Set the ``INFRAFOUNDRY_SKIP_LOCK`` environment variable to any truthy value
    to bypass locking entirely (with a loud warning). This is an emergency
    escape hatch - do not set it in normal operation.

    Args:
        state_manager: Active :class:`StateManager` whose ``locks`` repository
            backs this call.
        env_name: Environment name to lock.
        ttl: Lock TTL in seconds (how long the lock is valid if the holder
            crashes before release).
        locked_by: Identifier for the lock holder (``user@host:pid``).
        deployment_id: Optional deployment ID to associate with the lock row.
        timeout: Max seconds to wait when the lock is held. ``0`` means
            fail fast.
        poll_interval: Poll interval in seconds when waiting.
        event_manager: Optional :class:`EventManager` used to emit
            ``LOCK_ACQUIRED``/``LOCK_RELEASED``/``LOCK_TIMEOUT`` events.

    Yields:
        None.

    Raises:
        LockAcquisitionError: If the lock cannot be acquired (either
            immediately when ``timeout=0`` or after the timeout expires).
    """
    if os.environ.get(SKIP_LOCK_ENV):
        logger.warning(
            "%s is set - bypassing deployment lock for environment '%s'. "
            "This should only be used in emergencies.",
            SKIP_LOCK_ENV,
            env_name,
        )
        yield
        return

    lock = _acquire_with_timeout(
        state_manager=state_manager,
        env_name=env_name,
        ttl=ttl,
        locked_by=locked_by,
        deployment_id=deployment_id,
        timeout=timeout,
        poll_interval=poll_interval,
        event_manager=event_manager,
    )

    if event_manager is not None:
        event_manager.emit_event(
            EventType.LOCK_ACQUIRED,
            env_name,
            {
                "locked_by": locked_by,
                "acquired_at": str(lock.acquired_at),
                "expires_at": str(lock.expires_at),
            },
        )

    try:
        yield
    finally:
        try:
            state_manager.release_lock(env_name, locked_by=locked_by, force=True)
        except Exception:
            logger.exception("Failed to release lock on environment '%s'", env_name)
        else:
            if event_manager is not None:
                event_manager.emit_event(
                    EventType.LOCK_RELEASED,
                    env_name,
                    {"locked_by": locked_by},
                )


def _acquire_with_timeout(
    state_manager: StateManager,
    env_name: str,
    ttl: int,
    locked_by: str,
    deployment_id: int | None,
    timeout: int,
    poll_interval: float,
    event_manager: EventManager | None,
) -> DeploymentLock:
    """Acquire a lock, polling when ``timeout`` is positive.

    Returns the acquired :class:`DeploymentLock` on success. Raises
    :class:`LockAcquisitionError` on failure.
    """
    start = time.monotonic()
    while True:
        try:
            return state_manager.acquire_lock(
                environment=env_name,
                ttl_seconds=ttl,
                locked_by=locked_by,
                deployment_id=deployment_id,
            )
        except LockAcquisitionError:
            if timeout <= 0:
                raise
            elapsed = time.monotonic() - start
            if elapsed >= timeout:
                if event_manager is not None:
                    event_manager.emit_event(
                        EventType.LOCK_TIMEOUT,
                        env_name,
                        {"locked_by": locked_by, "timeout": timeout},
                    )
                raise
            time.sleep(poll_interval)
