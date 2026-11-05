"""Tests for the OPNsense singleton name migration (#1237)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import select

from infrafoundry.core.state import StateManager
from infrafoundry.core.state.models import (
    Deployment,
    DeploymentEvent,
    DeploymentStatus,
    Resource,
    ResourceState,
)
from infrafoundry.core.state.singleton_names import rename_legacy_singleton_rows

_ROWS = [
    ("opnsense", "system.tuning", "settings"),
    ("opnsense", "radvd", "settings"),
    ("opnsense", "firewall.aliases", "settings"),
    ("proxmox", "system.tuning", "settings"),
    ("opnsense", "system.dns", "dns"),
]


def _seed(mgr: StateManager) -> None:
    with mgr.SessionLocal() as s:
        dep = Deployment(
            environment="dev",
            command="apply",
            status=DeploymentStatus.COMPLETED,
            rollback_data={"environment": "dev", "resources": []},
        )
        s.add(dep)
        s.flush()
        s.add(DeploymentEvent(deployment_id=dep.id, event_type="x", resource_name="settings"))
        s.add_all(
            Resource(
                deployment_id=dep.id,
                environment="dev",
                provider=provider,
                resource_type=rtype,
                name=name,
                state=ResourceState.ACTIVE,
            )
            for provider, rtype, name in _ROWS
        )
        s.commit()


def _names(mgr: StateManager) -> list[tuple[str, str, str]]:
    with mgr.SessionLocal() as s:
        return sorted(
            (r.provider, r.resource_type, r.name) for r in s.execute(select(Resource)).scalars()
        )


@pytest.fixture
def manager(tmp_path: Path) -> Iterator[StateManager]:
    """A StateManager on its own SQLite file."""
    mgr = StateManager(f"sqlite:///{tmp_path / 'state.db'}")
    mgr.initialize()
    yield mgr
    mgr.cleanup()


def test_renames_only_legacy_opnsense_singleton_rows(manager: StateManager) -> None:
    _seed(manager)

    assert rename_legacy_singleton_rows(manager.SessionLocal) == 2

    assert _names(manager) == sorted(
        [
            ("opnsense", "system.tuning", "system.tuning"),
            ("opnsense", "radvd", "radvd"),
            ("opnsense", "firewall.aliases", "settings"),
            ("proxmox", "system.tuning", "settings"),
            ("opnsense", "system.dns", "dns"),
        ]
    )


def test_is_idempotent(manager: StateManager) -> None:
    _seed(manager)
    rename_legacy_singleton_rows(manager.SessionLocal)

    assert rename_legacy_singleton_rows(manager.SessionLocal) == 0


def test_leaves_event_history_untouched(manager: StateManager) -> None:
    _seed(manager)
    rename_legacy_singleton_rows(manager.SessionLocal)

    with manager.SessionLocal() as s:
        events = list(s.execute(select(DeploymentEvent)).scalars())
    assert [e.resource_name for e in events] == ["settings"]


def test_initialize_runs_the_migration(manager: StateManager) -> None:
    _seed(manager)

    manager.initialize()

    assert ("opnsense", "system.tuning", "system.tuning") in _names(manager)
    assert ("opnsense", "radvd", "radvd") in _names(manager)
