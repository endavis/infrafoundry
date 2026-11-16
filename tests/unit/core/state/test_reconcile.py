"""Tests for ``StateManager.reconcile_planned`` against a real temporary SQLite DB."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import select

from infrafoundry.core.state import StateManager
from infrafoundry.core.state.models import (
    Deployment,
    DeploymentStatus,
    Resource,
    ResourceState,
)

S = ResourceState


@pytest.fixture
def manager(tmp_path: Path) -> Iterator[StateManager]:
    mgr = StateManager(f"sqlite:///{tmp_path / 'state.db'}")
    mgr.initialize()
    yield mgr
    mgr.cleanup()


def _add(
    mgr: StateManager,
    states: list[ResourceState],
    *,
    env: str = "prod",
    provider: str = "p",
    rtype: str = "vm",
    name: str = "web-01",
) -> None:
    """Append one row per state, oldest first, each with its own deployment."""
    for state in states:
        dep = mgr.create_deployment(env, "apply")
        mgr.update_deployment_status(dep, DeploymentStatus.COMPLETED)
        mgr.track_resource(
            dep,
            env,
            provider,
            rtype,
            name,
            state,
            config={"cpu": 2},
            terraform_id=f"tf-{name}",
        )


def _rows(mgr: StateManager) -> list[Resource]:
    with mgr.SessionLocal() as s:
        rows = list(s.scalars(select(Resource).order_by(Resource.id)))
        s.expunge_all()
        return rows


def _reconcile_deployments(mgr: StateManager) -> list[Deployment]:
    with mgr.SessionLocal() as s:
        deps = list(s.scalars(select(Deployment).where(Deployment.command == "reconcile")))
        s.expunge_all()
        return deps


def test_active_then_planned_appends_active(manager: StateManager) -> None:
    _add(manager, [S.ACTIVE, S.PLANNED, S.PLANNED])

    cands, dep_id = manager.reconcile_planned("prod")

    assert len(cands) == 1
    assert cands[0].stale_planned == 2
    assert cands[0].name == "web-01"
    rows = _rows(manager)
    assert [r.state for r in rows] == [S.ACTIVE, S.PLANNED, S.PLANNED, S.ACTIVE]
    new, old = rows[-1], rows[0]
    assert (new.config, new.terraform_id, new.extra_data) == (
        old.config,
        old.terraform_id,
        old.extra_data,
    )
    assert new.deployment_id == dep_id


@pytest.mark.parametrize(
    "states",
    [
        [S.PLANNED],
        [S.PLANNED, S.PLANNED],
        [S.ACTIVE, S.DELETED, S.PLANNED],
        [S.ACTIVE, S.ERROR, S.PLANNED],
        [S.ACTIVE, S.CREATING, S.PLANNED],
        [S.ACTIVE, S.UPDATING, S.PLANNED],
        [S.ACTIVE, S.DELETING, S.PLANNED],
        [S.ACTIVE],
        [S.PLANNED, S.ACTIVE],
    ],
)
def test_untouched_cases(manager: StateManager, states: list[ResourceState]) -> None:
    _add(manager, states)

    cands, dep_id = manager.reconcile_planned("prod")

    assert cands == []
    assert dep_id is None
    assert len(_rows(manager)) == len(states)
    assert _reconcile_deployments(manager) == []


def test_groups_are_separate_and_environments_isolated(manager: StateManager) -> None:
    _add(manager, [S.ACTIVE, S.PLANNED], rtype="vm")
    _add(manager, [S.PLANNED], rtype="disk")
    _add(manager, [S.ACTIVE, S.PLANNED], provider="q")
    _add(manager, [S.ACTIVE, S.PLANNED], env="other")

    cands, _ = manager.reconcile_planned("prod")

    assert sorted((c.provider, c.resource_type) for c in cands) == [("p", "vm"), ("q", "vm")]
    assert len([r for r in _rows(manager) if r.environment == "other"]) == 2


def test_dry_run_changes_nothing(manager: StateManager) -> None:
    _add(manager, [S.ACTIVE, S.PLANNED])

    cands, dep_id = manager.reconcile_planned("prod", dry_run=True)

    assert len(cands) == 1
    assert dep_id is None
    assert len(_rows(manager)) == 2
    assert _reconcile_deployments(manager) == []


def test_single_reconcile_deployment_and_managed_set_unchanged(manager: StateManager) -> None:
    _add(manager, [S.ACTIVE, S.PLANNED], name="web-01")
    _add(manager, [S.ACTIVE, S.PLANNED], name="web-02")
    before = [
        (r.name, r.terraform_id, r.config) for r in manager.get_managed_resources("prod", "p")
    ]

    _, dep_id = manager.reconcile_planned("prod", user="alice")

    after = [(r.name, r.terraform_id, r.config) for r in manager.get_managed_resources("prod", "p")]
    assert sorted(after) == sorted(before)
    deps = _reconcile_deployments(manager)
    assert [d.id for d in deps] == [dep_id]
    assert deps[0].status == DeploymentStatus.COMPLETED
    assert deps[0].user == "alice"
    assert len([r for r in _rows(manager) if r.deployment_id == dep_id]) == 2


def test_second_run_is_noop(manager: StateManager) -> None:
    _add(manager, [S.ACTIVE, S.PLANNED])
    manager.reconcile_planned("prod")
    count = len(_rows(manager))

    cands, dep_id = manager.reconcile_planned("prod")

    assert (cands, dep_id) == ([], None)
    assert len(_rows(manager)) == count
    assert len(_reconcile_deployments(manager)) == 1


def test_failure_leaves_no_new_rows(manager: StateManager) -> None:
    _add(manager, [S.ACTIVE, S.PLANNED])

    with (
        patch("sqlalchemy.orm.Session.commit", side_effect=RuntimeError("boom")),
        pytest.raises(RuntimeError),
    ):
        manager.reconcile_planned("prod")

    assert len(_rows(manager)) == 2
    assert _reconcile_deployments(manager) == []
