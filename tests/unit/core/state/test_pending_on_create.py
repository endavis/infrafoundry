"""Tests for the ``on_create`` ledger against a real temporary SQLite database."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from infrafoundry.core.state import StateManager
from infrafoundry.core.state.models import DeploymentEvent
from infrafoundry.core.state.pending_on_create import PendingOnCreate


@pytest.fixture
def manager(tmp_path: Path) -> Iterator[StateManager]:
    """A StateManager on its own SQLite file."""
    mgr = StateManager(f"sqlite:///{tmp_path / 'state.db'}")
    mgr.initialize()
    yield mgr
    mgr.cleanup()


def _dep(mgr: StateManager, env: str = "dev") -> int:
    return mgr.create_deployment(env, "apply")


def test_pending_then_done_then_pending_again(manager: StateManager) -> None:
    dep = _dep(manager)
    manager.record_pending_on_create(dep, "px", "web", "resource", "px_vm.web")
    assert manager.get_pending_on_create("dev") == [
        PendingOnCreate("px", "web", "resource", "px_vm.web")
    ]

    manager.record_on_create_done(dep, "px", "web", "resource", "px_vm.web")
    assert manager.get_pending_on_create("dev") == []

    manager.record_pending_on_create(dep, "px", "web", "resource", "px_vm.web")
    assert [p.name for p in manager.get_pending_on_create("dev")] == ["web"]


def test_isolation_by_kind_provider_and_environment(manager: StateManager) -> None:
    dev = _dep(manager, "dev")
    prod = _dep(manager, "prod")
    manager.record_pending_on_create(dev, "px", "web", "resource", "a")
    manager.record_pending_on_create(dev, "px", "web", "package", "a")
    manager.record_pending_on_create(dev, "fw", "web", "resource", "b")
    manager.record_pending_on_create(prod, "px", "web", "resource", "c")

    manager.record_on_create_done(dev, "px", "web", "package", "a")

    pending = manager.get_pending_on_create("dev")
    assert {(p.provider, p.kind) for p in pending} == {("px", "resource"), ("fw", "resource")}
    assert [p.provider for p in manager.get_pending_on_create("dev", provider="fw")] == ["fw"]
    assert manager.get_pending_on_create("dev", kind="package") == []
    assert [p.address for p in manager.get_pending_on_create("prod")] == ["c"]


def test_ledger_survives_rename_and_is_removed_by_prune(manager: StateManager) -> None:
    dep = _dep(manager)
    manager.record_pending_on_create(dep, "px", "web", "resource", "a")

    manager.rename_environment("dev", "stage")
    assert manager.get_pending_on_create("dev") == []
    assert [p.name for p in manager.get_pending_on_create("stage")] == ["web"]

    manager.prune_environment("stage")
    assert manager.get_pending_on_create("stage") == []
    with manager.SessionLocal() as session:
        assert session.query(DeploymentEvent).count() == 0
