"""OpenWrtAnsibleRunner and the glinet.firmware resource (#1655, ADR-0036)."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from rich.console import Console

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.runners.openwrt_ansible_runner import OpenWrtAnsibleRunner
from infrafoundry.providers.openwrt import OpenWrtProvider
from infrafoundry.providers.openwrt.glinet.firmware import FIRMWARE_TYPE
from infrafoundry.providers.openwrt.settings import OpenWrtSettings
from tests.unit.providers.openwrt.conftest import doc, lan, res, task

pytestmark = pytest.mark.unit

SETTINGS = OpenWrtSettings(address="192.0.2.2")
LINES = [("glinet.firmware 'fw': 4.8.7 → 4.8.8 available (run upgrade)", False)]


def _firmware() -> ResourceConfig:
    return res(FIRMWARE_TYPE, "fw")


def _provider(tmp_path: Path) -> OpenWrtProvider:
    provider = OpenWrtProvider(tmp_path, tmp_path / "generated")
    provider.set_environment("test")
    return provider


class Ansible:
    """Stands in for ``_run`` and counts calls."""

    def __init__(self, *outputs: str) -> None:
        self.outputs = list(outputs)
        self.calls = 0

    def __call__(self, argv: list[str], cwd: Path, env: dict[str, str]) -> Any:
        import subprocess

        self.calls += 1
        out = self.outputs.pop(0) if self.outputs else ""
        return subprocess.CompletedProcess(argv, 0, out, "")


def _go(
    action: str,
    provider: OpenWrtProvider,
    resources: list[ResourceConfig],
    *,
    ansible: Ansible,
    lines: Any = None,
    **kwargs: Any,
) -> tuple[Any, str, Any]:
    out = io.StringIO()
    runner = OpenWrtAnsibleRunner(Console(file=out, width=200, no_color=True))
    hook = patch.object(OpenWrtProvider, "firmware_plan_lines", autospec=True, side_effect=lines)
    with (
        patch("infrafoundry.core.runners.openwrt_ansible_runner._run", ansible),
        patch(
            "infrafoundry.core.runners.openwrt_ansible_runner.shutil.which",
            return_value="/usr/bin/ansible-playbook",
        ),
        patch("infrafoundry.providers.openwrt.load_settings", return_value=SETTINGS),
        patch.object(OpenWrtAnsibleRunner, "_load_resources", return_value=resources),
        hook as mocked,
    ):
        result = getattr(runner, action)(provider, **kwargs)
    return result, out.getvalue(), mocked


def _lines(*_a: Any, **_k: Any) -> list[tuple[str, bool]]:
    return LINES


def test_firmware_only_plan_skips_ansible_and_reports_the_offer(tmp_path: Path) -> None:
    ansible = Ansible()
    result, output, _ = _go(
        "plan", _provider(tmp_path), [_firmware()], ansible=ansible, lines=_lines
    )
    assert ansible.calls == 0
    assert result["success"] and not result["has_changes"]
    assert "4.8.7 → 4.8.8 available" in output
    assert "openwrt_ansible:" in output


def test_firmware_only_apply_never_runs_ansible(tmp_path: Path) -> None:
    ansible = Ansible()
    result, _, mocked = _go(
        "apply", _provider(tmp_path), [_firmware()], ansible=ansible, lines=_lines
    )
    assert ansible.calls == 0
    assert result["success"]
    assert (result["resources_created"], result["resources_updated"]) == (0, 0)
    mocked.assert_not_called()  # apply never checks for a firmware offer


def test_firmware_only_destroy_never_runs_ansible(tmp_path: Path) -> None:
    ansible = Ansible()
    result, _, _ = _go("destroy", _provider(tmp_path), [_firmware()], ansible=ansible)
    assert ansible.calls == 0
    assert result["success"]


def test_a_firmware_warning_does_not_fail_the_plan(tmp_path: Path) -> None:
    warn = [("glinet.firmware 'fw': firmware check failed: router unreachable", True)]
    result, output, _ = _go(
        "plan", _provider(tmp_path), [_firmware()], ansible=Ansible(), lines=lambda *a, **k: warn
    )
    assert result["success"] and not result["has_changes"]
    assert "firmware check failed" in output


def test_a_raising_hook_does_not_fail_the_plan(tmp_path: Path) -> None:
    def boom(*_a: Any, **_k: Any) -> list[tuple[str, bool]]:
        raise RuntimeError("secret-looking detail")

    result, output, _ = _go(
        "plan", _provider(tmp_path), [_firmware()], ansible=Ansible(), lines=boom
    )
    assert result["success"]
    assert "secret-looking detail" not in output


def test_uci_changes_still_run_and_firmware_does_not_set_has_changes(tmp_path: Path) -> None:
    ansible = Ansible(doc(task("noop")))
    result, output, _ = _go(
        "plan", _provider(tmp_path), [lan(), _firmware()], ansible=ansible, lines=_lines
    )
    assert ansible.calls == 1
    assert result["success"] and not result["has_changes"]
    assert "available" in output


@pytest.mark.parametrize("kwargs", [{"add_only": True}, {"target_resources": ["lan"]}])
def test_no_firmware_call_for_drift_or_excluding_targets(
    tmp_path: Path, kwargs: dict[str, Any]
) -> None:
    ansible = Ansible(doc(task("noop")))
    _, _, mocked = _go(
        "plan", _provider(tmp_path), [lan(), _firmware()], ansible=ansible, lines=_lines, **kwargs
    )
    mocked.assert_not_called()


def test_a_target_naming_the_firmware_resource_checks_it(tmp_path: Path) -> None:
    ansible = Ansible(doc(task("noop")))
    _, _, mocked = _go(
        "plan",
        _provider(tmp_path),
        [lan(), _firmware()],
        ansible=ansible,
        lines=_lines,
        target_resources=["fw"],
    )
    mocked.assert_called_once()


def test_no_firmware_resource_means_no_hook_call(tmp_path: Path) -> None:
    ansible = Ansible(doc(task("noop")))
    _, _, mocked = _go("plan", _provider(tmp_path), [lan()], ansible=ansible, lines=_lines)
    mocked.assert_not_called()
