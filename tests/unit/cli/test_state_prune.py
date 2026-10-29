"""CLI tests for ``foundry state prune`` against the per-test isolated state DB."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from infrafoundry.cli.main import main
from infrafoundry.core.audit import AuditLogger
from infrafoundry.core.state import StateManager
from infrafoundry.core.state.models import DeploymentStatus, ResourceState

_SQLITE_PATH = "infrafoundry.cli.commands.state.prune.sqlite_db_path"


@pytest.fixture
def config_dir(tmp_path: Path) -> Path:
    """Config repo whose only environment is ``live``."""
    (tmp_path / "config" / "envs" / "live").mkdir(parents=True)
    return tmp_path / "config"


@pytest.fixture
def backup_dir(tmp_path: Path) -> Path:
    return tmp_path / "backups"


@pytest.fixture
def manager() -> StateManager:
    """StateManager on the isolated default DB the CLI will also open."""
    mgr = StateManager()
    mgr.initialize()
    return mgr


def _seed(mgr: StateManager, env: str) -> None:
    dep_id = mgr.create_deployment(env, "apply")
    mgr.update_deployment_status(dep_id, DeploymentStatus.COMPLETED)
    mgr.track_resource(dep_id, env, "p", "vm", f"{env}-vm", ResourceState.ACTIVE)


def _run(config_dir: Path, *args: str, input: str | None = None):  # type: ignore[no-untyped-def]
    return CliRunner().invoke(main, ["-c", str(config_dir), "state", "prune", *args], input=input)


def _db_file(mgr: StateManager) -> Path:
    return Path(str(mgr.engine.url.database))


def test_dry_run_changes_nothing(manager: StateManager, config_dir: Path, backup_dir: Path) -> None:
    _seed(manager, "stale")

    result = _run(config_dir, "--env", "stale", "--dry-run", "--backup-dir", str(backup_dir))

    assert result.exit_code == 0, result.output
    assert "resources" in result.output
    assert manager.list_environments() == ["stale"]
    assert not backup_dir.exists()
    assert AuditLogger(session_factory=manager.SessionLocal).query(action="state_pruned") == []


def test_yes_prunes_backs_up_and_audits(
    manager: StateManager, config_dir: Path, backup_dir: Path
) -> None:
    _seed(manager, "stale")
    _seed(manager, "keep")

    result = _run(config_dir, "--env", "stale", "--yes", "--backup-dir", str(backup_dir))

    assert result.exit_code == 0, result.output
    assert manager.list_environments() == ["keep"]
    backups = list(backup_dir.glob("infrafoundry_state_*.db"))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as conn:
        envs = {r[0] for r in conn.execute("SELECT DISTINCT environment FROM resources")}
    assert envs == {"stale", "keep"}

    audit = AuditLogger(session_factory=manager.SessionLocal)
    entries = audit.query(action="state_pruned")
    assert len(entries) == 1
    assert entries[0].event_type == "state_pruned"
    assert entries[0].environment == "stale"
    assert entries[0].changes_summary is not None
    assert entries[0].request_metadata is not None
    assert entries[0].changes_summary["resources"] == 1
    assert entries[0].request_metadata["backup_path"] == str(backups[0])
    assert entries[0].request_metadata["force"] is False
    assert audit.verify_integrity(entries[0].id)


def test_pruned_environment_leaves_list_environments(
    manager: StateManager, config_dir: Path, backup_dir: Path
) -> None:
    _seed(manager, "stale")
    _run(config_dir, "--env", "stale", "--yes", "--backup-dir", str(backup_dir))
    assert "stale" not in StateManager().list_environments()


def test_config_repo_environment_refused_without_force(
    manager: StateManager, config_dir: Path, backup_dir: Path
) -> None:
    _seed(manager, "live")

    refused = _run(config_dir, "--env", "live", "--yes", "--backup-dir", str(backup_dir))
    assert refused.exit_code != 0
    assert "--force" in refused.output
    assert manager.list_environments() == ["live"]

    forced = _run(config_dir, "--env", "live", "--yes", "--force", "--backup-dir", str(backup_dir))
    assert forced.exit_code == 0, forced.output
    assert manager.list_environments() == []
    entry = AuditLogger(session_factory=manager.SessionLocal).query(action="state_pruned")[0]
    assert entry.request_metadata is not None
    assert entry.request_metadata["force"] is True


def test_declining_prompt_deletes_nothing(
    manager: StateManager, config_dir: Path, backup_dir: Path
) -> None:
    _seed(manager, "stale")

    result = _run(config_dir, "--env", "stale", "--backup-dir", str(backup_dir), input="n\n")

    assert result.exit_code == 0
    assert "Prune cancelled" in result.output
    assert manager.list_environments() == ["stale"]
    assert not backup_dir.exists()


def test_empty_environment_is_nothing_to_prune(manager: StateManager, config_dir: Path) -> None:
    result = _run(config_dir, "--env", "ghost", "--yes")

    assert result.exit_code == 0
    assert "nothing to prune" in result.output.lower()


def test_active_lock_refuses_prune(
    manager: StateManager, config_dir: Path, backup_dir: Path
) -> None:
    _seed(manager, "stale")
    manager.acquire_lock("stale", 3600, "someone")

    result = _run(config_dir, "--env", "stale", "--yes", "--backup-dir", str(backup_dir))

    assert result.exit_code != 0
    assert "infra unlock" in result.output
    assert manager.list_environments() == ["stale"]


def test_expired_lock_is_pruned(manager: StateManager, config_dir: Path, backup_dir: Path) -> None:
    _seed(manager, "stale")
    lock = manager.acquire_lock("stale", 3600, "someone")
    assert lock is not None
    manager.extend_lock("stale", "someone", datetime.now(UTC) - timedelta(minutes=1))

    result = _run(config_dir, "--env", "stale", "--yes", "--backup-dir", str(backup_dir))

    assert result.exit_code == 0, result.output
    assert manager.list_locks() == []


def test_backup_failure_aborts_prune(
    manager: StateManager, config_dir: Path, backup_dir: Path
) -> None:
    _seed(manager, "stale")

    with patch(
        "infrafoundry.cli.commands.state.prune.copy_state_db", side_effect=OSError("disk full")
    ):
        result = _run(config_dir, "--env", "stale", "--yes", "--backup-dir", str(backup_dir))

    assert result.exit_code != 0
    assert "nothing was deleted" in result.output
    assert manager.list_environments() == ["stale"]


def test_no_backup_skips_copy(manager: StateManager, config_dir: Path, backup_dir: Path) -> None:
    _seed(manager, "stale")

    result = _run(
        config_dir, "--env", "stale", "--yes", "--no-backup", "--backup-dir", str(backup_dir)
    )

    assert result.exit_code == 0, result.output
    assert not backup_dir.exists()
    assert manager.list_environments() == []


def test_non_sqlite_refused_without_no_backup(
    manager: StateManager, config_dir: Path, backup_dir: Path
) -> None:
    _seed(manager, "stale")

    with patch(_SQLITE_PATH, return_value=None):
        refused = _run(config_dir, "--env", "stale", "--yes")
        assert refused.exit_code != 0
        assert "pg_dump" in refused.output
        assert manager.list_environments() == ["stale"]

        allowed = _run(config_dir, "--env", "stale", "--yes", "--no-backup")
    assert allowed.exit_code == 0, allowed.output
    assert manager.list_environments() == []


def test_doctor_suggestion_names_prune(config_dir: Path) -> None:
    from infrafoundry.cli.commands.config.doctor import _check_consistency

    with patch(
        "infrafoundry.cli.commands.config.doctor._get_state_db_environments",
        return_value=(["stale"], {}, True),
    ):
        result = _check_consistency(config_dir, deep=False)

    assert result.suggestion is not None
    assert "foundry state prune --env stale" in result.suggestion
