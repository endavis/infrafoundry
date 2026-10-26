"""The requirements preflight in the orchestrator, config doctor and blueprints (#1046)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

import pytest

from infrafoundry.cli.commands.config.doctor import _check_requirements
from infrafoundry.cli.errors import get_error_code
from infrafoundry.core.config import ConfigManager
from infrafoundry.core.config.blueprint_resolver import BlueprintResolver
from infrafoundry.core.exceptions import MissingRequirementsError
from infrafoundry.core.orchestrator import Orchestrator
from infrafoundry.core.requirements.manager import RequirementsReport
from infrafoundry.core.requirements.models import (
    BlueprintRequirements,
    PythonRequirement,
    RequirementKind,
    RequirementStatus,
)
from infrafoundry.core.state import StateManager

REPO_ROOT = Path(__file__).resolve().parents[4]


def _orchestrator(tmp_path: Path) -> Orchestrator:
    config_manager = Mock(spec=ConfigManager)
    config_manager.base_dir = tmp_path
    state_manager = StateManager(connection_string=f"sqlite:///{tmp_path / 'state.db'}")
    state_manager.initialize()
    orchestrator = Orchestrator(config_manager=config_manager, state_manager=state_manager)
    orchestrator.plan_orchestrator = Mock()
    orchestrator.apply_orchestrator = Mock()
    orchestrator.destroy_orchestrator = Mock()
    orchestrator.requirements_manager = Mock()
    orchestrator.requirements_manager.ensure.side_effect = MissingRequirementsError("netapp-lib")
    return orchestrator


@pytest.mark.parametrize("operation", ["plan", "apply", "destroy"])
def test_unmet_requirements_stop_the_run_before_any_provider_work(
    tmp_path: Path, operation: str
) -> None:
    orchestrator = _orchestrator(tmp_path)

    with pytest.raises(MissingRequirementsError):
        getattr(orchestrator, operation)(
            "prod", package_filter="ontap", provider_filter=["proxmox"]
        )

    orchestrator.requirements_manager.ensure.assert_called_once_with(  # type: ignore[attr-defined]
        "prod", "ontap", ["proxmox"]
    )
    orchestrator.plan_orchestrator.plan.assert_not_called()  # type: ignore[attr-defined]
    orchestrator.apply_orchestrator.apply.assert_not_called()  # type: ignore[attr-defined]
    orchestrator.destroy_orchestrator.destroy.assert_not_called()  # type: ignore[attr-defined]


def test_destroy_checks_requirements_before_taking_the_lock(tmp_path: Path) -> None:
    orchestrator = _orchestrator(tmp_path)

    with (
        patch("infrafoundry.core.orchestrator.environment_lock") as lock,
        pytest.raises(MissingRequirementsError),
    ):
        orchestrator.destroy("prod")

    lock.assert_not_called()


def test_missing_requirements_have_their_own_error_code() -> None:
    assert get_error_code(MissingRequirementsError("x")) == "IF-PACKAGE-002"


def test_blueprints_without_requirements_still_resolve(tmp_path: Path) -> None:
    blueprint = tmp_path / "blueprints" / "plain"
    blueprint.mkdir(parents=True)
    (blueprint / "blueprint.yaml").write_text("name: plain\n", encoding="utf-8")
    resolver = BlueprintResolver(tmp_path / "envs")
    resolver.blueprints_dir = tmp_path / "blueprints"

    assert resolver.resolve("plain")["requirements"] == BlueprintRequirements()


def test_ontap_cluster_declares_netapp_lib_and_its_collections() -> None:
    resolver = BlueprintResolver(REPO_ROOT / "example-config" / "envs")

    declared = resolver.resolve("ontap-cluster")["requirements"]

    assert PythonRequirement("netapp-lib>=2021.6.25", import_name="netapp_lib") in declared.python
    assert "netapp.ontap" in {c.name for c in declared.collections}


def _status(name: str, satisfied: bool) -> RequirementStatus:
    return RequirementStatus(
        kind=RequirementKind.PYTHON,
        name=name,
        wanted=">=1",
        installed=None if not satisfied else "1.0",
        satisfied=satisfied,
        blueprints=("bp",),
        problem="" if satisfied else "not installed",
        fix="" if satisfied else f"uv pip install '{name}>=1'",
    )


def _doctor(tmp_path: Path, reports: dict[str, Any]) -> list[Any]:
    for env in reports:
        (tmp_path / "envs" / env).mkdir(parents=True)
        (tmp_path / "envs" / env / "settings.yaml").write_text(f"name: {env}\n", encoding="utf-8")

    def check(self: Any, env_name: str, *args: Any) -> RequirementsReport:
        result = reports[env_name]
        if isinstance(result, Exception):
            raise result
        return RequirementsReport(env_name=env_name, statuses=tuple(result))

    with patch("infrafoundry.cli.commands.config.doctor.RequirementsManager.check", check):
        return _check_requirements(tmp_path)


def test_doctor_reports_requirement_status_per_environment(tmp_path: Path) -> None:
    results = _doctor(
        tmp_path,
        {
            "dev": [],
            "prod": [_status("alpha", True), _status("beta", False)],
            "lab": [_status("alpha", True)],
            "broken": ValueError("bad spec"),
        },
    )

    by_name = {r.name: r for r in results}
    assert by_name["Requirements (dev)"].status == "ok"
    assert by_name["Requirements (dev)"].message == "No blueprint requirements"
    assert by_name["Requirements (lab)"].status == "ok"
    assert by_name["Requirements (lab)"].message == "1 met"
    assert by_name["Requirements (prod)"].status == "error"
    assert by_name["Requirements (prod)"].message == "1 of 2 unmet: beta>=1 (not installed)"
    assert by_name["Requirements (prod)"].suggestion == "uv pip install 'beta>=1'"
    assert by_name["Requirements (broken)"].status == "error"
    assert "bad spec" in by_name["Requirements (broken)"].message


def test_doctor_warns_without_a_config_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("INFRAFOUNDRY_CONFIG_REPO", raising=False)

    [result] = _check_requirements(None)

    assert result.status == "warning"
