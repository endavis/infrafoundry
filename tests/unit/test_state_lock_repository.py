"""Unit tests for LockRepository."""

from __future__ import annotations

import tempfile
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from infrafoundry.core.exceptions import LockAcquisitionError
from infrafoundry.core.state import LockRepository, StateManager
from infrafoundry.core.state.models import Base, DeploymentLock


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_locks.db"
        connection_string = f"sqlite:///{db_path}"
        yield connection_string


@pytest.fixture
def state_manager(temp_db):
    """Create a StateManager with temporary database."""
    manager = StateManager(connection_string=temp_db)
    manager.initialize()
    return manager


@pytest.fixture
def repo(state_manager: StateManager) -> LockRepository:
    """Return the state manager's lock repository."""
    return state_manager.locks


class TestLockRepositoryAcquire:
    def test_acquire_creates_lock(self, repo: LockRepository) -> None:
        lock = repo.acquire("dev", ttl_seconds=60, locked_by="alice@host:1")
        assert lock.environment == "dev"
        assert lock.locked_by == "alice@host:1"
        assert lock.expires_at > lock.acquired_at

    def test_acquire_when_held_raises(self, repo: LockRepository) -> None:
        repo.acquire("dev", ttl_seconds=60, locked_by="alice@host:1")
        with pytest.raises(LockAcquisitionError) as excinfo:
            repo.acquire("dev", ttl_seconds=60, locked_by="bob@host:2")
        err = excinfo.value
        assert err.environment == "dev"
        assert err.locked_by == "alice@host:1"
        assert err.acquired_at is not None
        assert err.expires_at is not None

    def test_acquire_takes_over_expired_lock(self, repo: LockRepository) -> None:
        # Insert an already-expired row directly via the session.
        past = datetime.now(UTC) - timedelta(hours=1)
        with repo.SessionLocal() as session:
            session.add(
                DeploymentLock(
                    environment="dev",
                    locked_by="stale@host:99",
                    acquired_at=past - timedelta(seconds=60),
                    expires_at=past,
                )
            )
            session.commit()

        lock = repo.acquire("dev", ttl_seconds=60, locked_by="alice@host:1")
        assert lock.locked_by == "alice@host:1"
        assert lock.expires_at > datetime.now(UTC).replace(tzinfo=None)

    def test_lock_per_environment_independent(self, repo: LockRepository) -> None:
        repo.acquire("dev", ttl_seconds=60, locked_by="alice@host:1")
        # Different env should still succeed.
        lock = repo.acquire("prod", ttl_seconds=60, locked_by="alice@host:1")
        assert lock.environment == "prod"


class TestLockRepositoryRelease:
    def test_release_removes_row(self, repo: LockRepository) -> None:
        repo.acquire("dev", ttl_seconds=60, locked_by="alice@host:1")
        released = repo.release("dev", locked_by="alice@host:1")
        assert released is True
        assert repo.get("dev") is None

    def test_release_wrong_owner_refused_without_force(self, repo: LockRepository) -> None:
        repo.acquire("dev", ttl_seconds=60, locked_by="alice@host:1")
        released = repo.release("dev", locked_by="bob@host:2")
        assert released is False
        # Lock still present.
        assert repo.get("dev") is not None

    def test_release_force_succeeds(self, repo: LockRepository) -> None:
        repo.acquire("dev", ttl_seconds=60, locked_by="alice@host:1")
        released = repo.release("dev", locked_by="bob@host:2", force=True)
        assert released is True
        assert repo.get("dev") is None

    def test_release_nonexistent_returns_false(self, repo: LockRepository) -> None:
        assert repo.release("missing") is False


class TestLockRepositoryCleanup:
    def test_cleanup_stale_only_removes_expired(self, repo: LockRepository) -> None:
        past = datetime.now(UTC) - timedelta(hours=1)
        with repo.SessionLocal() as session:
            session.add(
                DeploymentLock(
                    environment="expired",
                    locked_by="stale@host:1",
                    acquired_at=past - timedelta(seconds=60),
                    expires_at=past,
                )
            )
            session.commit()
        # Active lock.
        repo.acquire("active", ttl_seconds=300, locked_by="alice@host:1")

        count = repo.cleanup_stale()
        assert count == 1
        assert repo.get("expired") is None
        assert repo.get("active") is not None

    def test_list_all_returns_detached(self, repo: LockRepository) -> None:
        repo.acquire("a", ttl_seconds=60, locked_by="alice@host:1")
        repo.acquire("b", ttl_seconds=60, locked_by="bob@host:2")
        locks = repo.list_all()
        assert {lock.environment for lock in locks} == {"a", "b"}


class TestLockRepositoryConcurrency:
    def test_concurrent_acquire_only_one_wins(self, tmp_path: Path) -> None:
        """Two threads racing on the same SQLite file: exactly one wins."""
        db_path = tmp_path / "race.db"
        url = f"sqlite:///{db_path}"

        # Prepare schema using one engine.
        init_engine = create_engine(url)
        Base.metadata.create_all(init_engine)
        init_engine.dispose()

        # Two independent engines simulating two processes.
        def make_repo() -> LockRepository:
            engine = create_engine(
                url,
                connect_args={"check_same_thread": False, "timeout": 30},
            )
            return LockRepository(sessionmaker(bind=engine))

        repo_a = make_repo()
        repo_b = make_repo()

        barrier = threading.Barrier(2)
        results: dict[str, object] = {}

        def worker(name: str, repo: LockRepository) -> None:
            barrier.wait()
            try:
                repo.acquire("shared", ttl_seconds=60, locked_by=name)
                results[name] = "ok"
            except LockAcquisitionError as exc:
                results[name] = exc

        t1 = threading.Thread(target=worker, args=("a@host:1", repo_a))
        t2 = threading.Thread(target=worker, args=("b@host:2", repo_b))
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

        successes = [v for v in results.values() if v == "ok"]
        failures = [v for v in results.values() if isinstance(v, LockAcquisitionError)]
        assert len(successes) == 1
        assert len(failures) == 1
