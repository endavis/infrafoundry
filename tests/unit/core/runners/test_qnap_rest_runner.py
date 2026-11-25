"""QnapRestRunner: VLAN and LACP plan, apply and destroy plus the firmware hook (ADR-0038, 0039)."""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

import pytest
from rich.console import Console

from infrafoundry.core.config import ConfigManager
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.provider_registry_service import ProviderRegistryService
from infrafoundry.core.runners.qnap_rest_runner import QnapRestRunner
from infrafoundry.core.types import ResourceOutcome
from infrafoundry.providers.mikrotik import MikroTikProvider
from infrafoundry.providers.qnap import QnapProvider

pytestmark = pytest.mark.unit

LINES = [("firmware.update 'sw': 2.5.0 → 2.6.0 available (run upgrade)", False)]


def _firmware() -> ResourceConfig:
    return ResourceConfig(name="sw", type="firmware.update", provider="qnap", config={})


def _provider(tmp_path: Path) -> QnapProvider:
    provider = QnapProvider(tmp_path, tmp_path / "generated")
    provider.set_environment("test")
    return provider


def _plan(tmp_path: Path, lines: Any, **kwargs: Any) -> tuple[Any, str, Any]:
    out = io.StringIO()
    runner = QnapRestRunner(Console(file=out, width=200, no_color=True))
    provider = _provider(tmp_path)
    hook = patch.object(QnapProvider, "firmware_plan_lines", autospec=True, side_effect=lines)
    with (
        patch.object(QnapRestRunner, "_load_resources", return_value=[_firmware()]),
        hook as mocked,
    ):
        result = runner.plan(provider, **kwargs)
    return result, out.getvalue(), mocked


def test_plan_prints_hook_lines_and_reports_no_changes(tmp_path: Path) -> None:
    result, output, _ = _plan(tmp_path, lambda *a, **k: LINES)
    assert result["success"] and not result["has_changes"]
    assert "2.5.0 → 2.6.0 available" in output and "qnap_rest:" in output


def test_warning_line_does_not_fail_the_plan(tmp_path: Path) -> None:
    warn = [("firmware.update 'sw': update check failed: unreachable", True)]
    result, output, _ = _plan(tmp_path, lambda *a, **k: warn)
    assert result["success"] and "update check failed" in output


def test_raising_hook_does_not_fail_the_plan_and_logs_the_type_only(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    def boom(*_a: Any, **_k: Any) -> list[tuple[str, bool]]:
        raise RuntimeError("secret-looking detail")

    result, output, _ = _plan(tmp_path, boom)
    assert result["success"]
    assert "secret-looking detail" not in output + caplog.text
    assert "RuntimeError" in caplog.text


@pytest.mark.parametrize("kwargs", [{"add_only": True}, {"target_resources": ["other"]}])
def test_hook_skipped_for_drift_and_other_targets(tmp_path: Path, kwargs: Any) -> None:
    result, output, mocked = _plan(tmp_path, lambda *a, **k: LINES, **kwargs)
    assert result["success"]
    mocked.assert_not_called()
    assert "available" not in output


def test_apply_and_destroy_never_call_the_hook(tmp_path: Path) -> None:
    runner = QnapRestRunner(Console(quiet=True))
    provider = _provider(tmp_path)
    with (
        patch.object(QnapRestRunner, "_load_resources", return_value=[_firmware()]),
        patch.object(QnapProvider, "firmware_plan_lines", autospec=True) as mocked,
    ):
        applied = runner.apply(provider)
        destroyed = runner.destroy(provider)
    assert applied["success"] and applied["resources_created"] == 0
    assert destroyed["success"] and destroyed["resources_destroyed"] == 0
    mocked.assert_not_called()


def test_non_qnap_provider_gets_no_changes(tmp_path: Path) -> None:
    runner = QnapRestRunner(Console(quiet=True))
    other = MikroTikProvider(tmp_path, tmp_path / "generated")
    result = runner.plan(other)
    assert result["success"] and not result["has_changes"]


def test_parse_plan_for_drift_reports_no_changes(tmp_path: Path) -> None:
    runner = QnapRestRunner(Console(quiet=True))
    with patch.object(QnapRestRunner, "_load_resources", return_value=[]):
        plan = runner.plan(_provider(tmp_path))
    drift = runner.parse_plan_for_drift(plan)
    assert not drift["has_changes"]
    failed = runner.parse_plan_for_drift({"success": False, "error": "boom"})
    assert failed["summary"] == "boom"


def test_runner_is_registered(tmp_path: Path) -> None:
    service = ProviderRegistryService(
        base_output_dir=tmp_path, config_manager=Mock(spec=ConfigManager)
    )
    assert "qnap_rest" in service.runner_registry.list_runners()


# -- config management (ADR-0039)


class _FakePlan:
    def __init__(self, **over: Any) -> None:
        self.refusals: list[str] = []
        self.warnings: list[str] = ["a warning"]
        self.has_changes = True
        self.counts = {"create": 1, "update": 2, "delete": 3}
        self.unmanaged = {"vlan": ["10", "20"]}
        for key, value in over.items():
            setattr(self, key, value)

    def summary_lines(self) -> list[str]:
        return ["vlan: 1 to create, 2 to update, 3 to delete"]


class _FakeOutcome:
    def __init__(self, **over: Any) -> None:
        self.refusals: list[str] = []
        self.warnings: list[str] = ["careful"]
        self.error: str | None = None
        self.outcomes = [ResourceOutcome("qnap_vlan.a", "create", "a")]
        self.counts = {"create": 1, "update": 0, "delete": 2}
        self.released = [{"resource_type": "vlan", "name": "old"}]
        self.completed = [object(), object()]
        self.success = True
        for key, value in over.items():
            setattr(self, key, value)


def _run(tmp_path: Path, method: str, attr: str, value: Any, **kwargs: Any) -> tuple[Any, str]:
    out = io.StringIO()
    runner = QnapRestRunner(Console(file=out, width=200, no_color=True))
    provider = _provider(tmp_path)
    with (
        patch.object(QnapRestRunner, "_load_resources", return_value=[_firmware()]),
        patch.object(QnapProvider, attr, **value) as mocked,
    ):
        result = getattr(runner, method)(provider, **kwargs)
    assert mocked is not None
    return result, out.getvalue()


def test_plan_prints_summary_unmanaged_and_warnings_and_returns_counts(tmp_path: Path) -> None:
    result, output = _run(
        tmp_path, "plan", "rest_plan", {"return_value": _FakePlan()}, add_only=True
    )
    assert result["success"] and result["has_changes"]
    assert json.loads(result["output"]) == {"create": 1, "update": 2, "delete": 3}
    assert "vlan: 1 to create" in output and "a warning" in output
    assert "vlan: unmanaged (kept): 10, 20" in output


def test_plan_passes_its_scope_to_the_provider(tmp_path: Path) -> None:
    runner = QnapRestRunner(Console(quiet=True))
    with (
        patch.object(QnapRestRunner, "_load_resources", return_value=[]),
        patch.object(QnapProvider, "rest_plan", return_value=_FakePlan()) as mocked,
    ):
        runner.plan(
            _provider(tmp_path), add_only=True, managed_resources={}, target_resources=["a"]
        )
    assert mocked.call_args.kwargs == {
        "add_only": True,
        "managed_resources": {},
        "target_resources": ["a"],
    }


def test_refused_plan_fails_the_run(tmp_path: Path) -> None:
    refused = _FakePlan(refusals=["the plan deletes the management VLAN 1"])
    result, _ = _run(tmp_path, "plan", "rest_plan", {"return_value": refused})
    assert not result["success"]
    assert "qnap plan refused, it could cut the management connection" in result["error"]
    assert "management VLAN 1" in result["error"]


def test_plan_error_fails_the_run(tmp_path: Path) -> None:
    result, _ = _run(tmp_path, "plan", "rest_plan", {"side_effect": RuntimeError("boom")})
    assert not result["success"] and "boom" in result["error"]


def test_parse_plan_for_drift_counts_add_change_and_destroy(tmp_path: Path) -> None:
    runner = QnapRestRunner(Console(quiet=True))
    result, _ = _run(tmp_path, "plan", "rest_plan", {"return_value": _FakePlan()})
    drift = runner.parse_plan_for_drift(result)
    assert (drift["to_add"], drift["to_change"], drift["to_destroy"]) == (1, 2, 3)
    assert drift["has_changes"]
    bad = runner.parse_plan_for_drift({"success": True, "output": "not json"})
    assert not bad["has_changes"]


def test_apply_maps_outcomes_and_released_resources(tmp_path: Path) -> None:
    result, output = _run(
        tmp_path, "apply", "rest_apply", {"return_value": _FakeOutcome()}, target_resources=["a"]
    )
    assert result["success"]
    assert (result["resources_created"], result["resources_deleted"]) == (1, 2)
    assert result["resource_outcomes_summary"][0]["address"] == "qnap_vlan.a"
    assert result["released_resources"] == [{"resource_type": "vlan", "name": "old"}]
    assert "careful" in output and "applied 2 step(s)" in output


def test_apply_refusal_and_failure(tmp_path: Path) -> None:
    refused = _FakeOutcome(refusals=["nope"], success=False)
    result, _ = _run(tmp_path, "apply", "rest_apply", {"return_value": refused})
    assert not result["success"] and "qnap apply refused" in result["error"]
    failed = _FakeOutcome(success=False, error="step 2 failed")
    result, _ = _run(tmp_path, "apply", "rest_apply", {"return_value": failed})
    assert not result["success"] and result["error"] == "step 2 failed"
    assert "released_resources" not in result
    result, _ = _run(tmp_path, "apply", "rest_apply", {"side_effect": RuntimeError("down")})
    assert not result["success"] and "down" in result["error"]


def test_targeted_apply_is_add_only(tmp_path: Path) -> None:
    runner = QnapRestRunner(Console(quiet=True))
    with (
        patch.object(QnapRestRunner, "_load_resources", return_value=[]),
        patch.object(QnapProvider, "rest_apply", return_value=_FakeOutcome()) as mocked,
    ):
        runner.apply(_provider(tmp_path), target_resources=["a"])
    assert mocked.call_args.kwargs["add_only"] is True


def test_destroy_maps_counts_and_refusals(tmp_path: Path) -> None:
    result, _ = _run(tmp_path, "destroy", "rest_destroy", {"return_value": _FakeOutcome()})
    assert result["success"] and result["resources_destroyed"] == 2
    refused = _FakeOutcome(refusals=["x"], success=False)
    result, _ = _run(tmp_path, "destroy", "rest_destroy", {"return_value": refused})
    assert not result["success"] and "qnap destroy refused" in result["error"]
    failed = _FakeOutcome(success=False, error="half done")
    result, _ = _run(tmp_path, "destroy", "rest_destroy", {"return_value": failed})
    assert result["error"] == "half done"
    result, _ = _run(tmp_path, "destroy", "rest_destroy", {"side_effect": RuntimeError("x")})
    assert not result["success"]


def test_needs_managed_dispatch_for_managed_vlan_rows(tmp_path: Path) -> None:
    runner = QnapRestRunner(Console(quiet=True))
    provider = _provider(tmp_path)
    row = ResourceConfig(name="a", type="vlan", provider="qnap", config={"id": 10})
    assert runner.needs_managed_dispatch(provider, {"vlan": [row]})
    assert runner.needs_managed_dispatch(provider, {"lacp.group": [row]})
    assert not runner.needs_managed_dispatch(provider, {"vlan": []})
    assert not runner.needs_managed_dispatch(provider, {"firmware.update": [row]})
    other = MikroTikProvider(tmp_path, tmp_path / "generated")
    assert not runner.needs_managed_dispatch(other, {"vlan": [row]})


def test_get_resource_ids(tmp_path: Path) -> None:
    runner = QnapRestRunner(Console(quiet=True))
    provider = _provider(tmp_path)
    with (
        patch.object(QnapRestRunner, "_load_resources", return_value=[]),
        patch.object(QnapProvider, "rest_resource_ids", return_value={"a": "10"}),
    ):
        assert runner.get_resource_ids(provider) == {"a": "10"}
    with (
        patch.object(QnapRestRunner, "_load_resources", return_value=[]),
        patch.object(QnapProvider, "rest_resource_ids", side_effect=RuntimeError("x")),
    ):
        assert runner.get_resource_ids(provider) == {}
    assert runner.get_resource_ids(MikroTikProvider(tmp_path, tmp_path / "generated")) == {}


def test_firmware_only_environment_plans_no_changes_and_applies_with_zero_counts(
    tmp_path: Path,
) -> None:
    out = io.StringIO()
    runner = QnapRestRunner(Console(file=out, width=200, no_color=True))
    provider = _provider(tmp_path)
    with (
        patch.object(QnapRestRunner, "_load_resources", return_value=[_firmware()]),
        patch.object(QnapProvider, "firmware_plan_lines", return_value=LINES),
    ):
        planned = runner.plan(provider)
        applied = runner.apply(provider)
        destroyed = runner.destroy(provider)
    assert planned["success"] and not planned["has_changes"]
    assert json.loads(planned["output"]) == {"create": 0, "update": 0, "delete": 0}
    assert "2.5.0 → 2.6.0 available" in out.getvalue()
    assert applied["success"] and applied["resources_created"] == 0
    assert destroyed["success"] and destroyed["resources_destroyed"] == 0
