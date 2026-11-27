"""Every command that reads or writes generated files honours the output root (#1716)."""

from __future__ import annotations

import tarfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from infrafoundry.cli.main import _get_orchestrator, main
from infrafoundry.core.config import ConfigManager
from infrafoundry.core.orchestrator import Orchestrator
from infrafoundry.core.paths import OUTPUT_DIR_ENV


@pytest.fixture
def relative_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Run from ``tmp_path`` with a relative output dir; return its absolute form."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(OUTPUT_DIR_ENV, "rel/gen")
    return (tmp_path / "rel" / "gen").resolve()


@pytest.fixture
def config_dir(tmp_path: Path) -> Path:
    (tmp_path / "config" / "envs" / "prod").mkdir(parents=True)
    return tmp_path / "config"


def test_orchestrator_default_uses_the_output_root(tmp_path: Path, relative_root: Path) -> None:
    orchestrator = Orchestrator(ConfigManager(base_dir=tmp_path / "envs"))
    assert orchestrator.output_dir == relative_root


def test_get_orchestrator_gives_every_provider_the_same_root(
    config_dir: Path, relative_root: Path
) -> None:
    orchestrator = _get_orchestrator(config_dir)

    assert orchestrator.output_dir == relative_root
    providers = list(orchestrator.providers.values())
    assert providers
    assert {p.base_output_dir for p in providers} == {relative_root}


def test_infra_security_scans_the_output_root(config_dir: Path, relative_root: Path) -> None:
    (relative_root / "prod").mkdir(parents=True)
    with patch("infrafoundry.cli.commands.infra.security.SecurityScanner") as scanner_cls:
        scanner = scanner_cls.return_value
        scanner.is_available.return_value = True
        scanner.get_version.return_value = "1"
        scanner.scan.return_value = MagicMock(error=None, passed=True)
        CliRunner().invoke(
            main, ["-c", str(config_dir), "infra", "security", "--env", "prod", "-o", "json"]
        )

    assert scanner.scan.call_args.args[0] == relative_root / "prod"


def test_infra_security_missing_dir_names_the_env(config_dir: Path, relative_root: Path) -> None:
    with patch("infrafoundry.cli.commands.infra.security.SecurityScanner") as scanner_cls:
        scanner_cls.return_value.is_available.return_value = True
        scanner_cls.return_value.get_version.return_value = None
        result = CliRunner().invoke(
            main, ["-c", str(config_dir), "infra", "security", "--env", "prod"]
        )

    assert result.exit_code == 1
    assert "infra plan --env prod" in result.output


def test_state_backup_archives_the_output_root(
    config_dir: Path, relative_root: Path, tmp_path: Path
) -> None:
    (relative_root / "prod").mkdir(parents=True)
    (relative_root / "prod" / "main.tf").write_text("x", encoding="utf-8")
    backups = tmp_path / "backups"
    result = CliRunner().invoke(
        main,
        [
            "-c",
            str(config_dir),
            "state",
            "backup",
            "--include-generated",
            "--output-dir",
            str(backups),
        ],
    )

    assert result.exit_code == 0, result.output
    archives = list(backups.glob("infrafoundry_generated_*.tar.gz"))
    assert len(archives) == 1
    with tarfile.open(archives[0]) as tar:
        assert any(name.endswith("prod/main.tf") for name in tar.getnames())


def test_move_package_uses_the_output_root(config_dir: Path, relative_root: Path) -> None:
    with patch("infrafoundry.cli.commands.infra.move_package.PackageMover") as mover_cls:
        mover_cls.return_value.execute.return_value = {
            "dry_run": True,
            "actions": [],
            "source_path": "s",
            "target_path": "t",
            "provider": "p",
            "state_addresses": [],
        }
        CliRunner().invoke(
            main,
            [
                "-c",
                str(config_dir),
                "infra",
                "move-package",
                "--env",
                "prod",
                "--package",
                "pkg",
                "--to-env",
                "dev",
                "--dry-run",
            ],
        )

    assert mover_cls.call_args.kwargs["generated_dir"] == relative_root
