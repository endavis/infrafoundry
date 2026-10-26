"""The ``foundry deps check`` and ``deps sync`` commands (#1047)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner, Result

from infrafoundry.cli.main import main
from infrafoundry.core.exceptions import RequirementInstallError
from infrafoundry.core.requirements.installer import InstallStep
from infrafoundry.core.requirements.manager import RequirementsReport, SyncResult
from infrafoundry.core.requirements.models import RequirementKind, RequirementStatus

MET = RequirementStatus(
    kind=RequirementKind.PYTHON,
    name="netapp-lib",
    wanted=">=2021.6.25",
    installed="2021.6.25",
    satisfied=True,
    blueprints=("ontap-cluster",),
)
UNMET = RequirementStatus(
    kind=RequirementKind.ANSIBLE_COLLECTION,
    name="netapp.ontap",
    wanted=">=22.0.0",
    installed=None,
    satisfied=False,
    blueprints=("ontap-cluster",),
    problem="not installed",
    fix="ansible-galaxy collection install --upgrade -r /bp/requirements.yml",
    install_args=("/bp/requirements.yml",),
)
STEP = InstallStep(
    kind=RequirementKind.ANSIBLE_COLLECTION,
    command=("ansible-galaxy", "collection", "install", "--upgrade", "-r", "/bp/requirements.yml"),
    covers=("netapp.ontap",),
)


def _report(*statuses: RequirementStatus) -> RequirementsReport:
    return RequirementsReport(env_name="prod", statuses=statuses)


@pytest.fixture
def orchestrator() -> Iterator[MagicMock]:
    """The orchestrator the commands receive."""
    with patch("infrafoundry.cli.main._get_orchestrator") as get_orchestrator:
        yield get_orchestrator.return_value


def _invoke(tmp_path: Path, *args: str) -> Result:
    return CliRunner().invoke(main, ["-c", str(tmp_path), "deps", *args])


def test_deps_group_lists_check_and_sync() -> None:
    result = CliRunner().invoke(main, ["deps", "--help"])

    assert result.exit_code == 0
    assert "check" in result.output
    assert "sync" in result.output


def test_check_exits_zero_when_every_requirement_is_met(
    orchestrator: MagicMock, tmp_path: Path
) -> None:
    orchestrator.requirements_manager.check.return_value = _report(MET)

    result = _invoke(tmp_path, "check", "--env", "prod")

    assert result.exit_code == 0, result.output
    assert "netapp-lib" in result.output
    assert "All 1 requirement(s) met" in result.output
    orchestrator.requirements_manager.check.assert_called_once_with("prod", None, None)


def test_check_exits_one_and_points_at_sync_when_unmet(
    orchestrator: MagicMock, tmp_path: Path
) -> None:
    orchestrator.requirements_manager.check.return_value = _report(MET, UNMET)

    result = _invoke(tmp_path, "check", "--env", "prod", "-P", "ontap")

    assert result.exit_code == 1
    assert "1 of 2 requirement(s) unmet" in result.output
    assert "foundry deps sync --env prod" in result.output
    orchestrator.requirements_manager.check.assert_called_once_with("prod", None, ["ontap"])


def test_check_with_nothing_in_scope_says_so(orchestrator: MagicMock, tmp_path: Path) -> None:
    orchestrator.requirements_manager.check.return_value = _report()

    result = _invoke(tmp_path, "check", "--env", "prod", "--package", "minio")

    assert result.exit_code == 0
    assert "No blueprint requirements in scope" in result.output
    orchestrator.requirements_manager.check.assert_called_once_with("prod", "minio", None)


@pytest.mark.parametrize("command", ["check", "sync"])
def test_package_and_provider_are_mutually_exclusive(
    orchestrator: MagicMock, tmp_path: Path, command: str
) -> None:
    result = _invoke(tmp_path, command, "--env", "prod", "-p", "ontap-cluster", "-P", "ontap")

    assert result.exit_code == 2
    assert "mutually exclusive" in result.output
    orchestrator.requirements_manager.check.assert_not_called()
    orchestrator.requirements_manager.sync.assert_not_called()


def test_sync_dry_run_prints_the_commands(orchestrator: MagicMock, tmp_path: Path) -> None:
    orchestrator.requirements_manager.sync.return_value = SyncResult(
        steps=(STEP,), report=_report(UNMET), dry_run=True
    )

    result = _invoke(tmp_path, "sync", "--env", "prod", "--dry-run")

    assert result.exit_code == 0, result.output
    assert "Would run for prod" in result.output
    assert "ansible-galaxy collection install --upgrade -r /bp/requirements.yml" in result.output
    orchestrator.requirements_manager.sync.assert_called_once_with("prod", None, None, dry_run=True)


def test_sync_reports_what_it_installed(orchestrator: MagicMock, tmp_path: Path) -> None:
    orchestrator.requirements_manager.sync.return_value = SyncResult(
        steps=(STEP,), report=_report(MET), dry_run=False
    )

    result = _invoke(tmp_path, "sync", "--env", "prod")

    assert result.exit_code == 0, result.output
    assert "Installed for prod" in result.output
    assert "All requirements met" in result.output


def test_sync_with_nothing_to_install(orchestrator: MagicMock, tmp_path: Path) -> None:
    orchestrator.requirements_manager.sync.return_value = SyncResult(
        steps=(), report=_report(MET), dry_run=False
    )

    result = _invoke(tmp_path, "sync", "--env", "prod")

    assert result.exit_code == 0
    assert "nothing to install" in result.output


def test_sync_failure_carries_its_error_code(orchestrator: MagicMock, tmp_path: Path) -> None:
    orchestrator.requirements_manager.sync.side_effect = RequirementInstallError(
        "Cannot install blueprint requirements: uv not found on PATH"
    )

    result = _invoke(tmp_path, "sync", "--env", "prod")

    assert result.exit_code == 1
    assert "IF-PACKAGE-003" in result.output
    assert "uv not found on PATH" in " ".join(result.output.split())
