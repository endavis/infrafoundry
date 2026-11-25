"""MikroTikRestRunner and the system.package.update plan hook (ADR-0037)."""

from __future__ import annotations

import io
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
from rich.console import Console

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.runners.mikrotik_rest_runner import MikroTikRestRunner
from infrafoundry.providers.mikrotik import MikroTikProvider
from infrafoundry.providers.mikrotik.components.manager import MikroTikPlan

pytestmark = pytest.mark.unit

LINES = [("system.package.update 'ros': 7.24 → 7.25 available (run upgrade)", False)]


def _update() -> ResourceConfig:
    return ResourceConfig(name="ros", type="system.package.update", provider="mikrotik", config={})


def _provider(tmp_path: Path) -> MikroTikProvider:
    provider = MikroTikProvider(tmp_path, tmp_path / "generated")
    provider.set_environment("test")
    return provider


def _plan(tmp_path: Path, lines: Any, **kwargs: Any) -> tuple[Any, str, Any]:
    out = io.StringIO()
    runner = MikroTikRestRunner(Console(file=out, width=200, no_color=True))
    provider = _provider(tmp_path)
    hook = patch.object(MikroTikProvider, "update_plan_lines", autospec=True, side_effect=lines)
    with (
        patch.object(provider, "rest_plan", return_value=MikroTikPlan(diffs={}, refusals=[])),
        patch.object(MikroTikRestRunner, "_load_resources", return_value=[_update()]),
        hook as mocked,
    ):
        result = runner.plan(provider, **kwargs)
    return result, out.getvalue(), mocked


def test_plan_prints_hook_lines(tmp_path: Path) -> None:
    result, output, _ = _plan(tmp_path, lambda *a, **k: LINES)
    assert result["success"] and not result["has_changes"]
    assert "7.24 → 7.25 available" in output and "mikrotik_rest:" in output


def test_warning_line_does_not_fail_the_plan(tmp_path: Path) -> None:
    warn = [("system.package.update 'ros': update check failed: unreachable", True)]
    result, output, _ = _plan(tmp_path, lambda *a, **k: warn)
    assert result["success"] and "update check failed" in output


def test_raising_hook_does_not_fail_the_plan(tmp_path: Path) -> None:
    def boom(*_a: Any, **_k: Any) -> list[tuple[str, bool]]:
        raise RuntimeError("secret-looking detail")

    result, output, _ = _plan(tmp_path, boom)
    assert result["success"] and "secret-looking detail" not in output


@pytest.mark.parametrize("kwargs", [{"add_only": True}, {"target_resources": ["other"]}])
def test_hook_skipped_for_drift_and_other_targets(tmp_path: Path, kwargs: Any) -> None:
    result, output, mocked = _plan(tmp_path, lambda *a, **k: LINES, **kwargs)
    assert result["success"]
    mocked.assert_not_called()
    assert "available" not in output


def test_apply_never_calls_the_hook(tmp_path: Path) -> None:
    runner = MikroTikRestRunner(Console(quiet=True))
    provider = _provider(tmp_path)
    outcome = SimpleNamespace(
        refusals=[], warnings=[], success=True, counts={}, outcomes=[], completed=[], released=[]
    )
    with (
        patch.object(MikroTikProvider, "update_plan_lines", autospec=True) as mocked,
        patch.object(MikroTikRestRunner, "_load_resources", return_value=[_update()]),
        patch.object(provider, "rest_apply", return_value=outcome),
    ):
        result = runner.apply(provider)
    assert result["success"]
    mocked.assert_not_called()
