"""CLI tests for ``foundry state reconcile`` against the per-test isolated state DB."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner, Result

from infrafoundry.cli.main import main
from infrafoundry.core.audit import AuditLogger
from infrafoundry.core.state import StateManager
from infrafoundry.core.state.models import DeploymentStatus, ResourceState


@pytest.fixture
def config_dir(tmp_path: Path) -> Path:
    (tmp_path / "config" / "envs" / "live").mkdir(parents=True)
    return tmp_path / "config"


@pytest.fixture
def manager() -> StateManager:
    mgr = StateManager()
    mgr.initialize()
    return mgr


def _seed(mgr: StateManager, env: str = "prod") -> None:
    """vps-01 is deployed then re-planned; web-01 was only ever planned."""
    for name, states in (
        ("vps-01", [ResourceState.ACTIVE, ResourceState.PLANNED]),
        ("web-01", [ResourceState.PLANNED]),
    ):
        for state in states:
            dep = mgr.create_deployment(env, "apply")
            mgr.update_deployment_status(dep, DeploymentStatus.COMPLETED)
            mgr.track_resource(dep, env, "p", "vm", name, state, config={"cpu": 1})


def _run(config_dir: Path, *args: str, input: str | None = None) -> Result:
    return CliRunner().invoke(
        main, ["-c", str(config_dir), "state", "reconcile", *args], input=input
    )


def _audit(mgr: StateManager) -> list[Any]:
    return list(AuditLogger(session_factory=mgr.SessionLocal).query(action="state_reconciled"))


def _count(mgr: StateManager) -> int:
    return len(mgr.get_resources(environment="prod"))


def test_dry_run_lists_and_writes_nothing(manager: StateManager, config_dir: Path) -> None:
    _seed(manager)

    result = _run(config_dir, "--env", "prod", "--dry-run")

    assert result.exit_code == 0, result.output
    assert "vps-01" in result.output
    assert "web-01" not in result.output
    assert _count(manager) == 3
    assert _audit(manager) == []


def test_yes_reconciles_and_audits(manager: StateManager, config_dir: Path) -> None:
    _seed(manager)

    result = _run(config_dir, "--env", "prod", "--yes")

    assert result.exit_code == 0, result.output
    newest = {
        r.name: r for r in sorted(manager.get_resources(environment="prod"), key=lambda r: r.id)
    }
    assert newest["vps-01"].state == ResourceState.ACTIVE
    assert newest["web-01"].state == ResourceState.PLANNED
    entries = _audit(manager)
    assert len(entries) == 1
    assert entries[0].event_type == "state_reconciled"
    assert entries[0].environment == "prod"
    assert entries[0].changes_summary["resources"] == 1


def test_declined_confirmation_changes_nothing(manager: StateManager, config_dir: Path) -> None:
    _seed(manager)

    declined = _run(config_dir, "--env", "prod", input="n\n")
    assert declined.exit_code == 0, declined.output
    assert _count(manager) == 3
    assert _audit(manager) == []

    accepted = _run(config_dir, "--env", "prod", input="y\n")
    assert accepted.exit_code == 0, accepted.output
    assert _count(manager) == 4
    assert len(_audit(manager)) == 1


def test_prompt_at_end_of_input_is_a_cancellation(manager: StateManager, config_dir: Path) -> None:
    """A prompt with no terminal stdin is a cancellation, not an unknown error (#1429)."""
    _seed(manager)

    result = _run(config_dir, "--env", "prod", input="")

    assert result.exit_code != 0
    assert "Operation cancelled" in result.output
    assert "IF-GENERAL-001" not in result.output
    assert "Unknown Error" not in result.output
    assert _count(manager) == 3
    assert _audit(manager) == []


def test_active_lock_refuses(manager: StateManager, config_dir: Path) -> None:
    _seed(manager)
    manager.acquire_lock("prod", 3600, "someone")

    result = _run(config_dir, "--env", "prod", "--yes")

    assert result.exit_code != 0
    assert "infra unlock" in result.output
    assert _count(manager) == 3


def test_nothing_to_reconcile(manager: StateManager, config_dir: Path) -> None:
    result = _run(config_dir, "--env", "prod", "--yes")

    assert result.exit_code == 0, result.output
    assert "Nothing to reconcile" in result.output
    assert _audit(manager) == []
