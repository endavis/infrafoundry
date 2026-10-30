"""Tests for ``StateManager.rename_environment`` against a real temporary SQLite DB."""

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


def _seed(mgr: StateManager, env: str, *, resources: int = 2) -> None:
    with mgr.SessionLocal() as s:
        dep = Deployment(
            environment=env,
            command="apply",
            status=DeploymentStatus.COMPLETED,
            rollback_data={"environment": env, "resources": []},
        )
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


def _snapshot(mgr: StateManager) -> list[tuple[str, str, str | None]]:
    with mgr.SessionLocal() as s:
        res = [("r", r.environment, None) for r in s.execute(select(Resource)).scalars()]
        dep = [
            ("d", d.environment, (d.rollback_data or {}).get("environment"))
            for d in s.execute(select(Deployment)).scalars()
        ]
        lock = [("l", k.environment, None) for k in s.execute(select(DeploymentLock)).scalars()]
    return sorted(res + dep + lock, key=str)


def _count(mgr: StateManager, model: type) -> int:
    with mgr.SessionLocal() as s:
        return int(s.execute(select(func.count()).select_from(model)).scalar_one())


def test_renames_only_target_environment(manager: StateManager) -> None:
    _seed(manager, "old", resources=3)
    _seed(manager, "keep")

    result = manager.rename_environment("old", "new")

    assert result == {"resources": 3, "deployments": 1, "deployment_locks": 1, "rollback_data": 1}
    assert manager.list_environments() == ["keep", "new"]
    assert manager.count_environment_rows("old") == dict.fromkeys(result, 0)
    assert manager.count_environment_rows("keep")["resources"] == 2


def test_rewrites_rollback_data(manager: StateManager) -> None:
    _seed(manager, "old")
    manager.rename_environment("old", "new")
    with manager.SessionLocal() as s:
        dep = s.execute(select(Deployment)).scalar_one()
    assert dep.rollback_data is not None
    assert dep.rollback_data["environment"] == "new"
    assert dep.rollback_data["resources"] == []


def test_keeps_dependencies_and_events(manager: StateManager) -> None:
    _seed(manager, "old", resources=3)
    manager.rename_environment("old", "new")
    assert _count(manager, ResourceDependency) == 2
    assert _count(manager, DeploymentEvent) == 1


def test_dry_run_changes_nothing(manager: StateManager) -> None:
    _seed(manager, "old")
    before = _snapshot(manager)

    result = manager.rename_environment("old", "new", dry_run=True)

    assert result["resources"] == 2
    assert _snapshot(manager) == before


def test_audit_entries_are_kept(manager: StateManager) -> None:
    from infrafoundry.core.audit import AuditLogger
    from infrafoundry.core.audit.models import AuditStatus
    from infrafoundry.core.events.types import EventType

    _seed(manager, "old")
    logger = AuditLogger(session_factory=manager.SessionLocal)
    logger.log(EventType.AFTER_APPLY, "apply_completed", AuditStatus.SUCCESS, environment="old")

    manager.rename_environment("old", "new")

    assert len(logger.query(env="old")) == 1


def test_midway_failure_rolls_back(manager: StateManager) -> None:
    _seed(manager, "old")
    before = _snapshot(manager)
    from infrafoundry.core.state import rename as rename_mod

    real_update = rename_mod.update
    calls = {"n": 0}

    def flaky(table: object) -> object:
        calls["n"] += 1
        if calls["n"] == 3:
            raise RuntimeError("boom")
        return real_update(table)  # type: ignore[arg-type]

    with patch.object(rename_mod, "update", flaky), pytest.raises(RuntimeError):
        manager.rename_environment("old", "new")

    assert calls["n"] == 3
    assert _snapshot(manager) == before


def test_refusals_change_nothing(manager: StateManager) -> None:
    _seed(manager, "old")
    _seed(manager, "taken")
    before = _snapshot(manager)

    with pytest.raises(StateError, match="itself"):
        manager.rename_environment("old", "old")
    with pytest.raises(StateError, match="has no state rows"):
        manager.rename_environment("ghost", "new")
    with pytest.raises(StateError, match="already has state rows"):
        manager.rename_environment("old", "taken")

    assert _snapshot(manager) == before
