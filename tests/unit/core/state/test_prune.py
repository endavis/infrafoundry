"""Tests for ``StateManager.prune_environment`` against a real temporary SQLite DB."""

from __future__ import annotations

import itertools
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import event, func, select

from infrafoundry.core.exceptions import StateError
from infrafoundry.core.state import StateManager
from infrafoundry.core.state.models import (
    Deployment,
    DeploymentEvent,
    DeploymentLock,
    DeploymentStatus,
    Resource,
    ResourceDependency,
    ResourceState,
)

TABLES = {
    "resource_dependencies": ResourceDependency,
    "deployment_events": DeploymentEvent,
    "resources": Resource,
    "deployment_locks": DeploymentLock,
    "deployments": Deployment,
}


@pytest.fixture
def manager(tmp_path: Path) -> Iterator[StateManager]:
    """A StateManager on its own SQLite file with foreign keys enforced."""
    mgr = StateManager(f"sqlite:///{tmp_path / 'state.db'}")

    @event.listens_for(mgr.engine, "connect")
    def _fk_on(dbapi_conn, _record) -> None:  # type: ignore[no-untyped-def]
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    mgr.initialize()
    yield mgr
    mgr.cleanup()


def _seed(mgr: StateManager, env: str, *, resources: int = 2) -> list[int]:
    """Add 1 deployment, its event and lock, and ``resources`` chained resources."""
    with mgr.SessionLocal() as s:
        dep = Deployment(environment=env, command="apply", status=DeploymentStatus.COMPLETED)
        s.add(dep)
        s.flush()
        s.add(DeploymentEvent(deployment_id=dep.id, event_type="x"))
        s.add(
            DeploymentLock(
                environment=env,
                locked_by="me",
                expires_at=datetime.now(UTC) - timedelta(hours=1),
                deployment_id=dep.id,
            )
        )
        rows = [
            Resource(
                deployment_id=dep.id,
                environment=env,
                provider="p",
                resource_type="vm",
                name=f"{env}-{i}",
                state=ResourceState.ACTIVE,
            )
            for i in range(resources)
        ]
        s.add_all(rows)
        s.flush()
        for a, b in itertools.pairwise(rows):
            s.add(ResourceDependency(resource_id=a.id, depends_on_id=b.id))
        s.commit()
        return [r.id for r in rows]


def _counts(mgr: StateManager) -> dict[str, int]:
    with mgr.SessionLocal() as s:
        return {
            n: s.execute(select(func.count()).select_from(m)).scalar_one()
            for n, m in TABLES.items()
        }


def test_prunes_only_target_environment(manager: StateManager) -> None:
    _seed(manager, "stale", resources=3)
    _seed(manager, "keep", resources=2)

    result = manager.prune_environment("stale")

    assert result == {
        "resource_dependencies": 2,
        "deployment_events": 1,
        "resources": 3,
        "deployment_locks": 1,
        "deployments": 1,
    }
    assert manager.list_environments() == ["keep"]
    assert _counts(manager) == {
        "resource_dependencies": 1,
        "deployment_events": 1,
        "resources": 2,
        "deployment_locks": 1,
        "deployments": 1,
    }


def test_dry_run_deletes_nothing(manager: StateManager) -> None:
    _seed(manager, "stale")
    before = _counts(manager)

    result = manager.prune_environment("stale", dry_run=True)

    assert result["resources"] == 2
    assert _counts(manager) == before


def test_unknown_environment_returns_zeros(manager: StateManager) -> None:
    _seed(manager, "keep")

    result = manager.prune_environment("ghost")

    assert set(result) == set(TABLES)
    assert not any(result.values())


def test_audit_entries_are_kept(manager: StateManager) -> None:
    from infrafoundry.core.audit import AuditLogger
    from infrafoundry.core.audit.models import AuditStatus
    from infrafoundry.core.events.types import EventType

    _seed(manager, "stale")
    logger = AuditLogger(session_factory=manager.SessionLocal)
    logger.log(EventType.AFTER_APPLY, "apply_completed", AuditStatus.SUCCESS, environment="stale")

    manager.prune_environment("stale")

    assert len(logger.query(env="stale")) == 1


def test_midway_failure_rolls_back_earlier_deletes(manager: StateManager) -> None:
    """The last delete fails after earlier ones ran; nothing may be committed."""
    _seed(manager, "stale")
    before = _counts(manager)
    from infrafoundry.core.state import prune as prune_mod

    real_delete = prune_mod.delete
    calls = {"n": 0}

    def flaky(table: object) -> object:
        calls["n"] += 1
        if calls["n"] == 5:
            raise RuntimeError("boom")
        return real_delete(table)  # type: ignore[arg-type]

    with patch.object(prune_mod, "delete", flaky), pytest.raises(RuntimeError):
        manager.prune_environment("stale")

    assert calls["n"] == 5
    assert _counts(manager) == before


def test_cross_environment_reference_raises_and_deletes_nothing(manager: StateManager) -> None:
    _seed(manager, "stale")
    with manager.SessionLocal() as s:
        dep_id = s.execute(
            select(Deployment.id).where(Deployment.environment == "stale")
        ).scalar_one()
        s.add(
            Resource(
                deployment_id=dep_id,
                environment="other",
                provider="p",
                resource_type="vm",
                name="x",
                state=ResourceState.ACTIVE,
            )
        )
        s.commit()
    before = _counts(manager)

    with pytest.raises(
        StateError, match=r"reference its deployments: other \(1\)\. Prune those environments"
    ):
        manager.prune_environment("stale")

    assert _counts(manager) == before
