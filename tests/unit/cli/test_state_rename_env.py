"""CLI tests for ``foundry state rename-env`` against the per-test isolated state DB."""

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

_SQLITE_PATH = "infrafoundry.cli.commands.state.rename_env.sqlite_db_path"


@pytest.fixture
def config_dir(tmp_path: Path) -> Path:
    """Config repo whose only environment is ``new`` (already renamed)."""
    (tmp_path / "config" / "envs" / "new").mkdir(parents=True)
    return tmp_path / "config"


@pytest.fixture
def backup_dir(tmp_path: Path) -> Path:
    return tmp_path / "backups"


@pytest.fixture
def generated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Generated root with a populated ``old`` directory."""
    root = tmp_path / "generated"
    (root / "old").mkdir(parents=True)
    (root / "old" / "main.tf").write_text("x")
    monkeypatch.setenv("INFRAFOUNDRY_OUTPUT_DIR", str(root))
    return root


@pytest.fixture
def manager() -> StateManager:
    mgr = StateManager()
    mgr.initialize()
    return mgr


def _seed(mgr: StateManager, env: str) -> None:
    dep_id = mgr.create_deployment(env, "apply")
    mgr.update_deployment_status(dep_id, DeploymentStatus.COMPLETED)
    mgr.track_resource(dep_id, env, "p", "vm", f"{env}-vm", ResourceState.ACTIVE)


def _run(config_dir: Path, *args: str, input: str | None = None):  # type: ignore[no-untyped-def]
    return CliRunner().invoke(
        main,
        ["-c", str(config_dir), "state", "rename-env", "--env", "old", "--to-env", "new", *args],
        input=input,
    )


def _audit(mgr: StateManager) -> AuditLogger:
    return AuditLogger(session_factory=mgr.SessionLocal)


def test_rename_moves_rows_directory_backup_and_audit(
    manager: StateManager, config_dir: Path, backup_dir: Path, generated: Path
) -> None:
    _seed(manager, "old")

    result = _run(config_dir, "--yes", "--backup-dir", str(backup_dir))

    assert result.exit_code == 0, result.output
    assert manager.list_environments() == ["new"]
    assert (generated / "new" / "main.tf").exists()
    assert not (generated / "old").exists()
    backups = list(backup_dir.glob("infrafoundry_state_*.db"))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as conn:
        envs = {r[0] for r in conn.execute("SELECT DISTINCT environment FROM resources")}
    assert envs == {"old"}

    audit = _audit(manager)
    entries = audit.query(action="state_env_renamed")
    assert len(entries) == 1
    entry = entries[0]
    assert entry.event_type == "state_env_renamed"
    assert entry.environment == "new"
    assert entry.changes_summary is not None
    assert entry.changes_summary["resources"] == 1
    assert entry.request_metadata is not None
    assert entry.request_metadata["old_environment"] == "old"
    assert entry.request_metadata["new_environment"] == "new"
    assert entry.request_metadata["backup_path"] == str(backups[0])
    assert entry.request_metadata["generated_moved"] is True
    assert entry.request_metadata["force"] is False
    assert audit.verify_integrity(entry.id)


def test_dry_run_changes_nothing(
    manager: StateManager, config_dir: Path, backup_dir: Path, generated: Path
) -> None:
    _seed(manager, "old")

    result = _run(config_dir, "--dry-run", "--backup-dir", str(backup_dir))

    assert result.exit_code == 0, result.output
    assert manager.list_environments() == ["old"]
    assert (generated / "old").exists()
    assert not backup_dir.exists()
    assert _audit(manager).query(action="state_env_renamed") == []


def test_declining_prompt_changes_nothing(
    manager: StateManager, config_dir: Path, backup_dir: Path, generated: Path
) -> None:
    _seed(manager, "old")

    result = _run(config_dir, "--backup-dir", str(backup_dir), input="n\n")

    assert result.exit_code == 0
    assert "Rename cancelled" in result.output
    assert manager.list_environments() == ["old"]
    assert (generated / "old").exists()
    assert not backup_dir.exists()


def test_same_name_refused(manager: StateManager, config_dir: Path, generated: Path) -> None:
    result = CliRunner().invoke(
        main,
        ["-c", str(config_dir), "state", "rename-env", "--env", "x", "--to-env", "x", "--yes"],
    )
    assert result.exit_code != 0
    assert "same ('x')" in result.output


def test_new_not_in_config_refused_and_force(
    manager: StateManager, tmp_path: Path, backup_dir: Path, generated: Path
) -> None:
    empty = tmp_path / "empty-config"
    (empty / "envs").mkdir(parents=True)
    _seed(manager, "old")

    refused = _run(empty, "--yes", "--backup-dir", str(backup_dir))
    assert refused.exit_code != 0
    assert "'new' does not exist in the config repo" in refused.output
    assert manager.list_environments() == ["old"]

    forced = _run(empty, "--yes", "--force", "--backup-dir", str(backup_dir))
    assert forced.exit_code == 0, forced.output
    assert manager.list_environments() == ["new"]
    entry = _audit(manager).query(action="state_env_renamed")[0]
    assert entry.request_metadata is not None
    assert entry.request_metadata["force"] is True


def test_old_still_in_config_refused_and_force(
    manager: StateManager, config_dir: Path, backup_dir: Path, generated: Path
) -> None:
    (config_dir / "envs" / "old").mkdir()
    _seed(manager, "old")

    refused = _run(config_dir, "--yes", "--backup-dir", str(backup_dir))
    assert refused.exit_code != 0
    assert "'old' still exists in the config repo" in refused.output
    assert manager.list_environments() == ["old"]

    forced = _run(config_dir, "--yes", "--force", "--backup-dir", str(backup_dir))
    assert forced.exit_code == 0, forced.output
    assert manager.list_environments() == ["new"]


def test_active_lock_refused(
    manager: StateManager, config_dir: Path, backup_dir: Path, generated: Path
) -> None:
    _seed(manager, "old")
    manager.acquire_lock("old", 3600, "someone")

    result = _run(config_dir, "--yes", "--backup-dir", str(backup_dir))

    assert result.exit_code != 0
    assert "infra unlock" in result.output
    assert manager.list_environments() == ["old"]


def test_expired_lock_is_renamed(
    manager: StateManager, config_dir: Path, backup_dir: Path, generated: Path
) -> None:
    _seed(manager, "old")
    assert manager.acquire_lock("old", 3600, "someone") is not None
    manager.extend_lock("old", "someone", datetime.now(UTC) - timedelta(minutes=1))

    result = _run(config_dir, "--yes", "--backup-dir", str(backup_dir))

    assert result.exit_code == 0, result.output
    assert [lock.environment for lock in manager.list_locks()] == ["new"]


def test_existing_new_generated_dir_refused(
    manager: StateManager, config_dir: Path, backup_dir: Path, generated: Path
) -> None:
    _seed(manager, "old")
    (generated / "new").mkdir()

    result = _run(config_dir, "--yes", "--backup-dir", str(backup_dir))

    assert result.exit_code != 0
    assert "already exists" in result.output
    assert manager.list_environments() == ["old"]
    assert not backup_dir.exists()


def test_missing_old_generated_dir_refused(
    manager: StateManager, config_dir: Path, backup_dir: Path, generated: Path
) -> None:
    _seed(manager, "old")
    (generated / "old" / "main.tf").unlink()
    (generated / "old").rmdir()

    result = _run(config_dir, "--yes", "--backup-dir", str(backup_dir))

    assert result.exit_code != 0
    assert "--no-move-generated" in result.output
    assert manager.list_environments() == ["old"]


def test_no_move_generated(
    manager: StateManager, config_dir: Path, backup_dir: Path, generated: Path
) -> None:
    _seed(manager, "old")

    result = _run(config_dir, "--yes", "--no-move-generated", "--backup-dir", str(backup_dir))

    assert result.exit_code == 0, result.output
    assert manager.list_environments() == ["new"]
    assert (generated / "old").exists()
    entry = _audit(manager).query(action="state_env_renamed")[0]
    assert entry.request_metadata is not None
    assert entry.request_metadata["generated_moved"] is False


def test_backup_failure_aborts(
    manager: StateManager, config_dir: Path, backup_dir: Path, generated: Path
) -> None:
    _seed(manager, "old")

    with patch(
        "infrafoundry.cli.commands.state.rename_env.copy_state_db",
        side_effect=OSError("disk full"),
    ):
        result = _run(config_dir, "--yes", "--backup-dir", str(backup_dir))

    assert result.exit_code != 0
    assert "nothing was renamed" in result.output
    assert manager.list_environments() == ["old"]
    assert (generated / "old").exists()


def test_no_backup_skips_copy(
    manager: StateManager, config_dir: Path, backup_dir: Path, generated: Path
) -> None:
    _seed(manager, "old")

    result = _run(config_dir, "--yes", "--no-backup", "--backup-dir", str(backup_dir))

    assert result.exit_code == 0, result.output
    assert not backup_dir.exists()
    assert manager.list_environments() == ["new"]


def test_non_sqlite_refused_without_no_backup(
    manager: StateManager, config_dir: Path, generated: Path
) -> None:
    _seed(manager, "old")

    with patch(_SQLITE_PATH, return_value=None):
        refused = _run(config_dir, "--yes")
        assert refused.exit_code != 0
        assert "pg_dump" in refused.output
        assert manager.list_environments() == ["old"]

        allowed = _run(config_dir, "--yes", "--no-backup")
    assert allowed.exit_code == 0, allowed.output
    assert manager.list_environments() == ["new"]


def test_failed_move_leaves_database_renamed(
    manager: StateManager, config_dir: Path, backup_dir: Path, generated: Path
) -> None:
    _seed(manager, "old")

    with patch(
        "infrafoundry.cli.commands.state.rename_env.shutil.move",
        side_effect=OSError("permission denied"),
    ):
        result = _run(config_dir, "--yes", "--backup-dir", str(backup_dir))

    assert result.exit_code != 0
    assert "already renamed" in result.output
    assert "mv" in result.output
    assert manager.list_environments() == ["new"]
    assert (generated / "old").exists()
    entry = _audit(manager).query(action="state_env_renamed")[0]
    assert entry.request_metadata is not None
    assert entry.request_metadata["generated_moved"] is False
    assert "permission denied" in (entry.message or "")
