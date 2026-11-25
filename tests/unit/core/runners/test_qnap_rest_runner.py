"""QnapRestRunner: report-only plan with the firmware hook (ADR-0038)."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

import pytest
from rich.console import Console

from infrafoundry.core.config import ConfigManager
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.provider_registry_service import ProviderRegistryService
from infrafoundry.core.runners.qnap_rest_runner import QnapRestRunner
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
    with patch.object(QnapProvider, "firmware_plan_lines", autospec=True) as mocked:
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
