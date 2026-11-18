"""Tests for MikroTikRestRunner."""

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from rich.console import Console

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.provider_registry_service import ProviderRegistryService
from infrafoundry.core.runners.mikrotik_rest_runner import MikroTikRestRunner
from infrafoundry.core.types import ResourceOutcome
from infrafoundry.providers.mikrotik import MikroTikProvider
from infrafoundry.providers.mikrotik.components.diff import Change, TypeDiff
from infrafoundry.providers.mikrotik.components.manager import MikroTikApplyResult, MikroTikPlan
from infrafoundry.providers.mikrotik.components.ordering import Step


def _provider(tmp_path: Path) -> MikroTikProvider:
    provider = MikroTikProvider(tmp_path, tmp_path / "generated")
    provider.set_environment("test")
    return provider


def _run(provider: MikroTikProvider, plan: MikroTikPlan | Exception, **kwargs: Any) -> Any:
    runner = MikroTikRestRunner(Console(quiet=True))
    target = {"side_effect": plan} if isinstance(plan, Exception) else {"return_value": plan}
    with (
        patch.object(provider, "rest_plan", **target) as rest_plan,
        patch.object(MikroTikRestRunner, "_load_resources", return_value=[]),
    ):
        result = runner.plan(provider, **kwargs)
    return result, rest_plan


def _plan_with(*kinds: str, refusals: list[str] | None = None) -> MikroTikPlan:
    diff = TypeDiff("ip.address")
    diff.changes = [
        Change(k, "ip.address", (f"198.51.100.{i}/24",), f"r{i}") for i, k in enumerate(kinds)
    ]
    return MikroTikPlan(diffs={"ip.address": diff}, refusals=refusals or [])


def test_runner_properties() -> None:
    runner = MikroTikRestRunner()
    assert (runner.tool_name, runner.is_iac_runner, runner.priority) == ("mikrotik_rest", True, -10)
    assert runner.is_available()
    assert runner.initialize(Path("."))["success"]


def test_other_providers_are_skipped() -> None:
    other = SimpleNamespace(name="opnsense")
    result = MikroTikRestRunner().plan(other, env_name="x")  # type: ignore[arg-type]
    assert result == {"success": True, "has_changes": False, "changes_summary": "No changes"}


def test_clean_plan_has_no_changes(tmp_path: Path) -> None:
    result, _ = _run(_provider(tmp_path), MikroTikPlan())
    assert result["success"] and result["has_changes"] is False


def test_changes_are_reported_with_structured_counts(tmp_path: Path) -> None:
    result, _ = _run(_provider(tmp_path), _plan_with("create", "update", "update"))
    assert result["has_changes"] is True
    assert json.loads(result["output"]) == {"create": 1, "update": 2, "delete": 0}


def test_refusal_fails_the_plan_with_reason(tmp_path: Path) -> None:
    result, _ = _run(_provider(tmp_path), _plan_with(refusals=["cuts the management address"]))
    assert result["success"] is False
    assert "cuts the management address" in result["error"]


def test_provider_error_fails_the_plan(tmp_path: Path) -> None:
    result, _ = _run(_provider(tmp_path), RuntimeError("device unreachable"))
    assert result["success"] is False and "device unreachable" in result["error"]


def test_kwargs_reach_the_provider(tmp_path: Path) -> None:
    _, rest_plan = _run(
        _provider(tmp_path),
        MikroTikPlan(),
        add_only=True,
        target_resources=["a"],
        managed_resources={"ip.address": []},
    )
    assert rest_plan.call_args.kwargs == {
        "add_only": True,
        "managed_resources": {"ip.address": []},
        "target_resources": ["a"],
    }


def test_missing_environment_raises(tmp_path: Path) -> None:
    provider = MikroTikProvider(tmp_path, tmp_path)
    with pytest.raises(RuntimeError, match="set_environment"):
        MikroTikRestRunner().plan(provider)


def test_parse_plan_for_drift_counts(tmp_path: Path) -> None:
    runner = MikroTikRestRunner(Console(quiet=True))
    result, _ = _run(_provider(tmp_path), _plan_with("create", "update"))
    info = runner.parse_plan_for_drift(result)
    assert (info["has_changes"], info["to_add"], info["to_change"], info["to_destroy"]) == (
        True,
        1,
        1,
        0,
    )
    clean = runner.parse_plan_for_drift({"success": True, "output": json.dumps({})})
    assert clean["has_changes"] is False
    failed = runner.parse_plan_for_drift({"success": False, "error": "boom"})
    assert failed["has_changes"] is False and failed["summary"] == "boom"


def _step(kind: str = "create", name: str = "b1") -> Step:
    return Step("B", kind, "interface.bridge", (name,), name, None, {})


def _applied(**fields: Any) -> MikroTikApplyResult:
    return MikroTikApplyResult(**fields)


def _run_apply(
    provider: MikroTikProvider,
    outcome: MikroTikApplyResult | Exception,
    method: str = "apply",
    **kwargs: Any,
) -> tuple[Any, MagicMock]:
    runner = MikroTikRestRunner(Console(quiet=True))
    name = "rest_apply" if method == "apply" else "rest_destroy"
    target = (
        {"side_effect": outcome} if isinstance(outcome, Exception) else {"return_value": outcome}
    )
    with (
        patch.object(provider, name, **target) as rest,
        patch.object(MikroTikRestRunner, "_load_resources", return_value=[]),
    ):
        result = getattr(runner, method)(provider, **kwargs)
    return result, rest


def test_apply_maps_counts_outcomes_and_released(tmp_path: Path) -> None:
    outcome = _applied(
        completed=[_step(), _step("update", "b2")],
        outcomes=[
            ResourceOutcome("mikrotik_interface_bridge.b1", "create", "b1"),
            ResourceOutcome("mikrotik_interface_bridge.b2", "update", "b2"),
        ],
        counts={"create": 1, "update": 1, "delete": 0},
        released=[{"resource_type": "interface.bridge", "name": "old"}],
    )

    result, rest = _run_apply(_provider(tmp_path), outcome, managed_resources={"x": []})

    assert result["success"] is True
    assert (result["resources_created"], result["resources_updated"]) == (1, 1)
    assert result["resources_deleted"] == 0
    assert result["resource_outcomes"] == outcome.outcomes
    assert result["resource_outcomes_summary"][0] == {
        "address": "mikrotik_interface_bridge.b1",
        "action": "create",
        "resource_name": "b1",
    }
    assert result["released_resources"] == outcome.released
    assert rest.call_args.kwargs["managed_resources"] == {"x": []}
    assert rest.call_args.kwargs["add_only"] is False


def test_apply_without_released_omits_the_key(tmp_path: Path) -> None:
    result, _ = _run_apply(_provider(tmp_path), _applied(counts={}))
    assert result["success"] and "released_resources" not in result


def test_apply_refusal_fails_with_the_reason(tmp_path: Path) -> None:
    result, _ = _run_apply(_provider(tmp_path), _applied(refusals=["no management address"]))
    assert result["success"] is False
    assert "refused" in result["error"] and "no management address" in result["error"]


def test_apply_step_failure_reports_the_error_and_completed_outcomes(tmp_path: Path) -> None:
    outcome = _applied(
        completed=[_step()],
        failed=_step("create", "b2"),
        error="mikrotik apply failed at step 2 of 2: boom",
        outcomes=[ResourceOutcome("mikrotik_interface_bridge.b1", "create", "b1")],
        counts={"create": 1, "update": 0, "delete": 0},
        released=[{"resource_type": "interface.bridge", "name": "old"}],
    )

    result, _ = _run_apply(_provider(tmp_path), outcome)

    assert result["success"] is False
    assert "step 2 of 2" in result["error"]
    assert result["resources_created"] == 1 and len(result["resource_outcomes"]) == 1
    assert "released_resources" not in result


def test_apply_provider_exception_fails(tmp_path: Path) -> None:
    result, _ = _run_apply(_provider(tmp_path), RuntimeError("device unreachable"))
    assert result == {"success": False, "error": "device unreachable"}


def test_apply_with_target_resources_is_add_only(tmp_path: Path) -> None:
    _, rest = _run_apply(_provider(tmp_path), _applied(), target_resources=["b1"])
    assert rest.call_args.kwargs["add_only"] is True
    assert rest.call_args.kwargs["target_resources"] == ["b1"]


def test_destroy_maps_the_deleted_count(tmp_path: Path) -> None:
    outcome = _applied(
        completed=[_step("delete")],
        outcomes=[ResourceOutcome("mikrotik_interface_bridge.b1", "delete", "b1")],
        counts={"create": 0, "update": 0, "delete": 1},
    )

    result, rest = _run_apply(_provider(tmp_path), outcome, "destroy", target_resources=["b1"])

    assert result["success"] and result["resources_destroyed"] == 1
    assert result["resource_outcomes"] == outcome.outcomes
    assert rest.call_args.kwargs["target_resources"] == ["b1"]


def test_destroy_refusal_and_failure(tmp_path: Path) -> None:
    refused, _ = _run_apply(_provider(tmp_path), _applied(refusals=["path"]), "destroy")
    assert refused["success"] is False and "path" in refused["error"]
    failed, _ = _run_apply(
        _provider(tmp_path), _applied(failed=_step(), error="step 1 failed"), "destroy"
    )
    assert failed["success"] is False and failed["error"] == "step 1 failed"
    raised, _ = _run_apply(_provider(tmp_path), RuntimeError("boom"), "destroy")
    assert raised == {"success": False, "error": "boom"}


def test_needs_managed_dispatch(tmp_path: Path) -> None:
    runner = MikroTikRestRunner()
    provider = _provider(tmp_path)
    row = ResourceConfig(name="v", type="interface.vlan", provider="mikrotik", config={})
    svc = ResourceConfig(name="s", type="ip.service", provider="mikrotik", config={})
    assert runner.needs_managed_dispatch(provider, {"interface.vlan": [row]})
    assert not runner.needs_managed_dispatch(provider, {"ip.service": [svc]})
    assert not runner.needs_managed_dispatch(provider, {"interface.vlan": []})
    other = SimpleNamespace(name="opnsense")
    assert not runner.needs_managed_dispatch(other, {"interface.vlan": [row]})  # type: ignore[arg-type]


def test_get_resource_ids(tmp_path: Path) -> None:
    runner = MikroTikRestRunner()
    provider = _provider(tmp_path)
    with (
        patch.object(provider, "rest_resource_ids", return_value={"b1": "*5"}),
        patch.object(MikroTikRestRunner, "_load_resources", return_value=[]),
    ):
        assert runner.get_resource_ids(provider) == {"b1": "*5"}
    with (
        patch.object(provider, "rest_resource_ids", side_effect=RuntimeError("down")),
        patch.object(MikroTikRestRunner, "_load_resources", return_value=[]),
    ):
        assert runner.get_resource_ids(provider) == {}
    assert runner.get_resource_ids(SimpleNamespace(name="x")) == {}  # type: ignore[arg-type]


def test_apply_ignores_other_providers() -> None:
    other = SimpleNamespace(name="host")
    assert MikroTikRestRunner().apply(other)["success"]  # type: ignore[arg-type]
    assert MikroTikRestRunner().destroy(other)["success"]  # type: ignore[arg-type]


def test_runner_is_registered_by_default() -> None:
    service = ProviderRegistryService(Path("generated"), MagicMock())
    assert "mikrotik_rest" in service.runner_registry.list_runners()
