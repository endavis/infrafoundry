"""Tests for MikroTikRestRunner."""

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from rich.console import Console

from infrafoundry.core.provider_registry_service import ProviderRegistryService
from infrafoundry.core.runners.mikrotik_rest_runner import (
    NOT_IMPLEMENTED_MESSAGE,
    MikroTikRestRunner,
)
from infrafoundry.providers.mikrotik import MikroTikProvider
from infrafoundry.providers.mikrotik.components.diff import Change, TypeDiff
from infrafoundry.providers.mikrotik.components.manager import MikroTikPlan


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


def test_apply_and_destroy_fail_loudly(tmp_path: Path) -> None:
    runner = MikroTikRestRunner()
    provider = _provider(tmp_path)
    applied = runner.apply(provider)
    destroyed = runner.destroy(provider)
    assert applied == {"success": False, "error": NOT_IMPLEMENTED_MESSAGE}
    assert destroyed == {"success": False, "error": NOT_IMPLEMENTED_MESSAGE}
    assert "#1483" in NOT_IMPLEMENTED_MESSAGE


def test_apply_ignores_other_providers() -> None:
    other = SimpleNamespace(name="host")
    assert MikroTikRestRunner().apply(other)["success"]  # type: ignore[arg-type]
    assert MikroTikRestRunner().destroy(other)["success"]  # type: ignore[arg-type]


def test_runner_is_registered_by_default() -> None:
    service = ProviderRegistryService(Path("generated"), MagicMock())
    assert "mikrotik_rest" in service.runner_registry.list_runners()
