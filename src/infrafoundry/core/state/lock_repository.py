"""Repository for deployment lock operations.

Backs the ``deployment_locks`` table used by :mod:`infrafoundry.core.state.lock_context`
to provide per-environment exclusive locking around ``apply`` and ``destroy``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from infrafoundry.core.exceptions import LockAcquisitionError
from infrafoundry.core.state.models import DeploymentLock


class LockRepository:
    """Handles all deployment-lock database operations.

    Mirrors :class:`DeploymentRepository` in shape: constructed with a
    ``sessionmaker``, opens a fresh session per call, and returns detached
    (expunged) ORM instances so callers do not hold onto closed sessions.
    """

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        """Initialize repository with SQLAlchemy session factory.

        Args:
            session_factory: SQLAlchemy sessionmaker instance.
        """
        self.SessionLocal = session_factory

    def acquire(
        self,
        environment: str,
        ttl_seconds: int,
        locked_by: str,
        deployment_id: int | None = None,
    ) -> DeploymentLock:
        """Acquire an exclusive lock on ``environment``.

        Behavior:
        - If no row exists, insert one. Commit, return.
        - If an active (non-expired) row exists, raise ``LockAcquisitionError``.
        - If an expired row exists, update it in place (stale takeover).
        - If a concurrent inserter wins the race, ``IntegrityError`` is caught
          and converted to ``LockAcquisitionError`` with fresh metadata.

        Args:
            environment: Environment name to lock.
            ttl_seconds: How long (seconds) the lock should remain valid.
            locked_by: Identifier of the lock holder (``user@host:pid``).
            deployment_id: Optional deployment ID to associate with the lock.

        Returns:
            The freshly-acquired :class:`DeploymentLock` (detached).

        Raises:
            LockAcquisitionError: If the lock is already held by another
                active owner.
        """
        now = datetime.now(UTC)
        expires_at = now + timedelta(seconds=ttl_seconds)

        with self.SessionLocal() as session:
            existing = (
                session.query(DeploymentLock)
                .filter(DeploymentLock.environment == environment)
                .one_or_none()
            )
            if existing is not None:
                existing_expires = _as_aware(existing.expires_at)
                if existing_expires > now:
                    # Active lock held by another owner.
                    raise LockAcquisitionError(
                        environment=environment,
                        locked_by=existing.locked_by,
                        acquired_at=_as_aware(existing.acquired_at),
                        expires_at=existing_expires,
                    )
                # Stale lock - take it over in place.
                existing.locked_by = locked_by
                existing.acquired_at = now
                existing.expires_at = expires_at
                existing.deployment_id = deployment_id
                session.commit()
                session.refresh(existing)
                session.expunge(existing)
                return existing

            # No row - insert a new one. Another process racing us may
            # succeed first; catch IntegrityError and convert.
            lock = DeploymentLock(
                environment=environment,
                locked_by=locked_by,
                acquired_at=now,
                expires_at=expires_at,
                deployment_id=deployment_id,
            )
            session.add(lock)
            try:
                session.commit()
            except IntegrityError as exc:
                session.rollback()
                # Re-query to surface the winner's metadata.
                winner = (
                    session.query(DeploymentLock)
                    .filter(DeploymentLock.environment == environment)
                    .one_or_none()
                )
                if winner is None:
                    # Shouldn't happen, but be defensive.
                    raise LockAcquisitionError(
                        environment=environment,
                        locked_by="unknown",
                        acquired_at=now,
                        expires_at=now,
                        message=(f"Failed to acquire lock on '{environment}': {exc}"),
                    ) from exc
                raise LockAcquisitionError(
                    environment=environment,
                    locked_by=winner.locked_by,
                    acquired_at=_as_aware(winner.acquired_at),
                    expires_at=_as_aware(winner.expires_at),
                ) from exc
            session.refresh(lock)
            session.expunge(lock)
            return lock

    def release(
        self,
        environment: str,
        locked_by: str | None = None,
        force: bool = False,
    ) -> bool:
        """Release the lock on ``environment``.

        Args:
            environment: Environment name whose lock should be released.
            locked_by: Optional owner identifier. If provided (and ``force``
                is False) the lock is only released when the owner matches.
            force: If True, release the lock regardless of the owner.

        Returns:
            ``True`` if a row was actually deleted. ``False`` if no lock
            existed, or if the owner did not match and ``force`` was False
            (silent refusal - wrong-owner without force is a no-op).
        """
        with self.SessionLocal() as session:
            lock = (
                session.query(DeploymentLock)
                .filter(DeploymentLock.environment == environment)
                .one_or_none()
            )
            if lock is None:
                return False
            if not force and locked_by is not None and lock.locked_by != locked_by:
                # Wrong-owner without force: silent refusal per design.
                return False
            session.delete(lock)
            session.commit()
            return True

    def get(self, environment: str) -> DeploymentLock | None:
        """Return the current lock row for ``environment``, if any.

        Args:
            environment: Environment name.

        Returns:
            Detached :class:`DeploymentLock` or ``None`` when no row exists.
        """
        with self.SessionLocal() as session:
            lock = (
                session.query(DeploymentLock)
                .filter(DeploymentLock.environment == environment)
                .one_or_none()
            )
            if lock is None:
                return None
            session.expunge(lock)
            return lock

    def list_all(self) -> list[DeploymentLock]:
        """Return all lock rows (detached).

        Returns:
            List of :class:`DeploymentLock` instances, possibly empty.
        """
        with self.SessionLocal() as session:
            locks = session.query(DeploymentLock).all()
            for lock in locks:
                session.expunge(lock)
            return list(locks)

    def cleanup_stale(self) -> int:
        """Delete all expired locks.

        Returns:
            Number of rows removed.
        """
        now = datetime.now(UTC)
        with self.SessionLocal() as session:
            expired = session.query(DeploymentLock).filter(DeploymentLock.expires_at <= now).all()
            count = len(expired)
            for lock in expired:
                session.delete(lock)
            if count:
                session.commit()
            return count


def _as_aware(value: datetime) -> datetime:
    """Return ``value`` as a timezone-aware UTC datetime.

    SQLite stores naive datetimes even when we pass aware ones in; normalize
    on read so comparisons and rendered messages are consistent.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value
