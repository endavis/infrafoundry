"""Tests for composite state indexes and their upgrade path (#242)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine, inspect, text

from infrafoundry.core.state import StateManager
from infrafoundry.core.state.indexes import ensure_indexes
from infrafoundry.core.state.models import (
    Base,
    Deployment,
    DeploymentStatus,
    Resource,
    ResourceState,
)

RES_IDX = "ix_resources_env_provider_name"
DEP_IDX = "ix_deployments_env_started_at"


def _names(engine: Engine, table: str) -> set[str]:
    return {i["name"] for i in inspect(engine).get_indexes(table) if i["name"]}


def _drop_composites(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text(f"DROP INDEX {RES_IDX}"))
        conn.execute(text(f"DROP INDEX {DEP_IDX}"))


@pytest.fixture
def db_url(tmp_path: Path) -> str:
    return f"sqlite:///{tmp_path / 'state.db'}"


@pytest.fixture
def manager(db_url: str) -> Iterator[StateManager]:
    mgr = StateManager(db_url)
    mgr.initialize()
    yield mgr
    mgr.cleanup()


def test_new_database_has_composite_and_single_indexes(manager: StateManager) -> None:
    assert {RES_IDX, "ix_resources_environment", "ix_resources_provider"} <= _names(
        manager.engine, "resources"
    )
    assert {DEP_IDX, "ix_deployments_environment"} <= _names(manager.engine, "deployments")


def test_ensure_indexes_reports_created_names(manager: StateManager) -> None:
    assert ensure_indexes(manager.engine) == []
    _drop_composites(manager.engine)
    assert ensure_indexes(manager.engine) == [DEP_IDX, RES_IDX]
    assert ensure_indexes(manager.engine) == []


def test_upgrade_old_schema_keeps_rows(db_url: str, caplog: pytest.LogCaptureFixture) -> None:
    mgr = StateManager(db_url)
    Base.metadata.create_all(mgr.engine)
    _drop_composites(mgr.engine)
    with mgr.SessionLocal() as s:
        dep = Deployment(environment="dev", command="apply", status=DeploymentStatus.COMPLETED)
        s.add(dep)
        s.flush()
        s.add(
            Resource(
                deployment_id=dep.id,
                environment="dev",
                provider="p",
                resource_type="t",
                name="n",
                state=ResourceState.ACTIVE,
            )
        )
        s.commit()
    mgr.cleanup()

    upgraded = StateManager(db_url)
    try:
        with caplog.at_level("INFO"):
            upgraded.initialize()
        assert RES_IDX in _names(upgraded.engine, "resources")
        assert DEP_IDX in _names(upgraded.engine, "deployments")
        with upgraded.SessionLocal() as s:
            assert s.query(Deployment).count() == 1
            assert s.query(Resource).count() == 1
        assert RES_IDX in caplog.text
        upgraded.initialize()
        assert ensure_indexes(upgraded.engine) == []
    finally:
        upgraded.cleanup()


def test_resource_lookup_uses_composite_index(manager: StateManager) -> None:
    with manager.engine.connect() as conn:
        plan = conn.execute(
            text(
                "EXPLAIN QUERY PLAN SELECT id FROM resources "
                "WHERE environment=:e AND provider=:p AND name=:n"
            ),
            {"e": "dev", "p": "p", "n": "n"},
        ).fetchall()
    assert RES_IDX in " ".join(str(r) for r in plan)


def test_deployment_history_uses_composite_index(manager: StateManager) -> None:
    with manager.engine.connect() as conn:
        plan = conn.execute(
            text(
                "EXPLAIN QUERY PLAN SELECT id FROM deployments WHERE environment=:e "
                "ORDER BY started_at DESC LIMIT 10"
            ),
            {"e": "dev"},
        ).fetchall()
    assert DEP_IDX in " ".join(str(r) for r in plan)
