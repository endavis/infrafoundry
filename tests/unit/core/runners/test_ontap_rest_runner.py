"""OntapRestRunner: plan, apply, destroy, drift counts and managed dispatch (ADR-0026, 0042)."""

from __future__ import annotations

import io
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
from rich.console import Console

from infrafoundry.core.provider_registry_service import ProviderRegistryService
from infrafoundry.core.runners.ontap_rest_runner import OntapRestRunner
from infrafoundry.core.types import ResourceOutcome
from infrafoundry.providers.mikrotik import MikroTikProvider
from infrafoundry.providers.ontap import OntapProvider
from infrafoundry.providers.ontap.components.interface import CREATE, UPDATE, Change, InterfaceDiff
from infrafoundry.providers.ontap.components.manager import OntapApplyResult, OntapPlan, Step

pytestmark = pytest.mark.unit

KEY = ("svm1", "lif1")


def _provider(tmp_path: Path) -> OntapProvider:
    provider = OntapProvider(tmp_path, tmp_path / "generated")
    provider.set_environment("test")
    return provider


def _runner() -> tuple[OntapRestRunner, io.StringIO]:
    out = io.StringIO()
    return OntapRestRunner(Console(file=out, width=200, no_color=True)), out


def _plan(*kinds: str, **fields: Any) -> OntapPlan:
    plan = OntapPlan()
    plan.diff = InterfaceDiff(
        changes=[Change(k, KEY, "lif1", "u1", {}, {}, ("address",)) for k in kinds], **fields
    )
    return plan


def _run(runner: OntapRestRunner, method: str, provider: OntapProvider, **kwargs: Any) -> Any:
    with patch.object(OntapRestRunner, "_load_resources", return_value=[]):
        return getattr(runner, method)(provider, **kwargs)


def test_runner_identity(tmp_path: Path) -> None:
    runner = OntapRestRunner()
    assert runner.tool_name == "ontap_rest" and runner.is_iac_runner and runner.priority == -10
    assert runner.is_available()
    assert runner.initialize(tmp_path)["success"]
    assert callable(OntapProvider.generate_ontap_rest)


def test_other_providers_are_ignored(tmp_path: Path) -> None:
    runner = OntapRestRunner()
    other = MikroTikProvider(tmp_path, tmp_path / "generated")
    assert not runner._supports(other)
    assert runner.plan(other)["has_changes"] is False
    assert runner.apply(other)["success"] and runner.destroy(other)["success"]
    assert runner.get_resource_ids(other) == {}
    assert not runner.needs_managed_dispatch(other, {"network.ip.interface": [object()]})  # type: ignore[list-item]


def test_plan_prints_the_summary_and_reports_the_counts(tmp_path: Path) -> None:
    runner, out = _runner()
    plan = _plan(UPDATE, CREATE, unmanaged=["svm1/other"])
    plan.warnings.append("LIF 'svm1/x' is not on its home port")
    with patch.object(OntapProvider, "rest_plan", return_value=plan):
        result = _run(runner, "plan", _provider(tmp_path))
    assert result["success"] and result["has_changes"]
    assert json.loads(result["output"]) == {"create": 1, "update": 1, "delete": 0}
    assert "1 to create, 1 to update, 0 to delete, 1 unmanaged (kept)" in result["changes_summary"]
    text = out.getvalue()
    assert "unmanaged (kept): svm1/other" in text and "not on its home port" in text


def test_a_clean_plan_has_no_changes(tmp_path: Path) -> None:
    runner, _ = _runner()
    with patch.object(OntapProvider, "rest_plan", return_value=_plan()):
        result = _run(runner, "plan", _provider(tmp_path))
    assert result["success"] and not result["has_changes"]
    assert result["changes_summary"] == "No changes"


def test_a_refused_plan_fails_with_the_reasons(tmp_path: Path) -> None:
    runner, _ = _runner()
    plan = _plan(UPDATE)
    plan.refusals.append("refusing to update LIF 'svm1/lif1'")
    with patch.object(OntapProvider, "rest_plan", return_value=plan):
        result = _run(runner, "plan", _provider(tmp_path))
    assert not result["success"]
    assert "ontap plan refused" in result["error"] and "refusing to update" in result["error"]


def test_plan_exceptions_become_failed_results(tmp_path: Path) -> None:
    runner, _ = _runner()
    with patch.object(OntapProvider, "rest_plan", side_effect=RuntimeError("down")):
        result = _run(runner, "plan", _provider(tmp_path))
    assert not result["success"] and result["error"] == "down"


def test_plan_passes_the_run_options_through(tmp_path: Path) -> None:
    runner, _ = _runner()
    managed: Any = {"network.ip.interface": []}
    with patch.object(OntapProvider, "rest_plan", return_value=_plan()) as rest_plan:
        _run(
            runner,
            "plan",
            _provider(tmp_path),
            add_only=True,
            managed_resources=managed,
            target_resources=["lif1"],
        )
    assert rest_plan.call_args.args[0] == "test"
    assert rest_plan.call_args.kwargs == {
        "add_only": True,
        "managed_resources": managed,
        "target_resources": ["lif1"],
    }


def test_missing_environment_fails_the_plan() -> None:
    runner, _ = _runner()
    provider = OntapProvider(Path("."), Path("generated"))
    with pytest.raises(RuntimeError, match="set_environment"):
        runner.plan(provider)


@pytest.mark.parametrize(
    ("kinds", "expected"),
    [((), (0, 0, 0, False)), ((CREATE, UPDATE), (1, 1, 0, True))],
)
def test_drift_counts_come_from_the_plan_output(
    tmp_path: Path, kinds: tuple[str, ...], expected: tuple[int, int, int, bool]
) -> None:
    runner, _ = _runner()
    with patch.object(OntapProvider, "rest_plan", return_value=_plan(*kinds)):
        planned = _run(runner, "plan", _provider(tmp_path), add_only=True)
    info = runner.parse_plan_for_drift(planned)
    assert (info["to_add"], info["to_change"], info["to_destroy"], info["has_changes"]) == expected


def test_drift_of_a_failed_plan_reports_the_error() -> None:
    info = OntapRestRunner().parse_plan_for_drift({"success": False, "error": "unreachable"})
    assert not info["has_changes"] and info["summary"] == "unreachable"
    garbled = OntapRestRunner().parse_plan_for_drift({"success": True, "output": "{not json"})
    assert not garbled["has_changes"]


def _applied(**changes: Any) -> OntapApplyResult:
    result = OntapApplyResult(
        completed=[Step(CREATE, "lif1", KEY, "interface")],
        outcomes=[ResourceOutcome("ontap_network_ip_interface.lif1", CREATE, "lif1")],
        counts={CREATE: 1, UPDATE: 2, "delete": 3},
    )
    for name, value in changes.items():
        setattr(result, name, value)
    return result


def test_apply_maps_counts_outcomes_and_released_rows(tmp_path: Path) -> None:
    runner, out = _runner()
    released: Any = [{"resource_type": "network.ip.interface", "name": "old"}]
    with patch.object(
        OntapProvider, "rest_apply", return_value=_applied(released=released, warnings=["w1"])
    ) as rest_apply:
        result = _run(runner, "apply", _provider(tmp_path), target_resources=["lif1"])
    assert result["success"]
    assert (result["resources_created"], result["resources_updated"]) == (1, 2)
    assert result["resources_deleted"] == 3
    assert result["resource_outcomes_summary"][0]["address"] == "ontap_network_ip_interface.lif1"
    assert result["released_resources"] == released
    assert rest_apply.call_args.kwargs["add_only"] is True
    assert "w1" in out.getvalue() and "applied 1 step(s)" in out.getvalue()


def test_a_failed_apply_carries_the_error(tmp_path: Path) -> None:
    runner, _ = _runner()
    failed = _applied(failed=Step(CREATE, "lif1", KEY, "interface"), error="step 1 failed: boom")
    with patch.object(OntapProvider, "rest_apply", return_value=failed):
        result = _run(runner, "apply", _provider(tmp_path))
    assert not result["success"] and result["error"] == "step 1 failed: boom"


def test_a_refused_apply_and_exceptions_fail_without_writes(tmp_path: Path) -> None:
    runner, _ = _runner()
    with patch.object(
        OntapProvider, "rest_apply", return_value=OntapApplyResult(refusals=["no way"])
    ):
        refused = _run(runner, "apply", _provider(tmp_path))
    assert not refused["success"] and "ontap apply refused" in refused["error"]
    with patch.object(OntapProvider, "rest_apply", side_effect=RuntimeError("boom")):
        raised = _run(runner, "apply", _provider(tmp_path))
    assert not raised["success"] and raised["error"] == "boom"


def test_destroy_maps_the_delete_count(tmp_path: Path) -> None:
    runner, _ = _runner()
    with patch.object(OntapProvider, "rest_destroy", return_value=_applied()) as rest_destroy:
        result = _run(runner, "destroy", _provider(tmp_path), target_resources=["lif1"])
    assert result["success"] and result["resources_destroyed"] == 3
    assert rest_destroy.call_args.kwargs == {"target_resources": ["lif1"]}


def test_destroy_refusal_and_exception(tmp_path: Path) -> None:
    runner, _ = _runner()
    with patch.object(
        OntapProvider, "rest_destroy", return_value=OntapApplyResult(refusals=["mgmt lif"])
    ):
        refused = _run(runner, "destroy", _provider(tmp_path))
    assert not refused["success"] and "ontap destroy refused" in refused["error"]
    with patch.object(OntapProvider, "rest_destroy", side_effect=RuntimeError("boom")):
        assert _run(runner, "destroy", _provider(tmp_path))["error"] == "boom"
    failed = _applied(error="x", failed=Step("delete", "lif1", KEY, "interface"))
    with patch.object(OntapProvider, "rest_destroy", return_value=failed):
        assert not _run(runner, "destroy", _provider(tmp_path))["success"]


def test_managed_dispatch_needs_a_managed_lif(tmp_path: Path) -> None:
    runner = OntapRestRunner()
    provider = _provider(tmp_path)
    assert runner.needs_managed_dispatch(provider, {"network.ip.interface": [object()]})  # type: ignore[list-item]
    assert not runner.needs_managed_dispatch(provider, {"network.ip.interface": []})
    assert not runner.needs_managed_dispatch(provider, {"other": [object()]})  # type: ignore[list-item]


def test_resource_ids_and_their_failure_mode(tmp_path: Path) -> None:
    runner = OntapRestRunner()
    provider = _provider(tmp_path)
    with (
        patch.object(OntapRestRunner, "_load_resources", return_value=[]),
        patch.object(OntapProvider, "rest_resource_ids", return_value={"lif1": "u1"}),
    ):
        assert runner.get_resource_ids(provider) == {"lif1": "u1"}
    with (
        patch.object(OntapRestRunner, "_load_resources", return_value=[]),
        patch.object(OntapProvider, "rest_resource_ids", side_effect=RuntimeError("down")),
    ):
        assert runner.get_resource_ids(provider) == {}


def test_load_resources_filters_by_provider(tmp_path: Path) -> None:
    mine = SimpleNamespace(provider="ontap", name="a")
    theirs = SimpleNamespace(provider="mikrotik", name="b")
    with patch("infrafoundry.core.config.ConfigManager") as manager:
        manager.return_value.load_environment.return_value = object()
        manager.return_value.get_all_resources_all_providers.return_value = [mine, theirs]
        assert OntapRestRunner._load_resources(_provider(tmp_path), "test") == [mine]
        manager.return_value.load_environment.return_value = None
        assert OntapRestRunner._load_resources(_provider(tmp_path), "test") == []
    assert OntapRestRunner._load_resources(SimpleNamespace(name="ontap"), "test") == []  # type: ignore[arg-type]


def test_the_registry_registers_the_runner(tmp_path: Path) -> None:
    from unittest.mock import Mock

    from infrafoundry.core.config import ConfigManager
    from infrafoundry.core.runners import RunnerRegistry

    registry = Mock(spec=RunnerRegistry)
    ProviderRegistryService(
        base_output_dir=tmp_path,
        config_manager=Mock(spec=ConfigManager),
        runner_registry_factory=Mock(return_value=registry),
    )
    registered = [c.args[0] for c in registry.register.call_args_list]
    assert OntapRestRunner in registered
