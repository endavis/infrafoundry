"""Every runner satisfies the runner protocols it implements (#1073).

The runners returned ``dict[str, Any]`` and took ``auto_approve`` through
``**kwargs``, so none was assignable to ``Plannable``, ``Applyable`` or
``Destroyable`` under mypy. The runtime ``isinstance`` check only compares
attribute names and could not catch that. The ``_as_*`` helpers return each
runner typed as the protocol, so ``doit type_check`` fails here if an
implementation drifts again; the tests cover the runtime side.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest

from infrafoundry.core.protocols import Applyable, Destroyable, Plannable, StateAware
from infrafoundry.core.provider import ProviderBase
from infrafoundry.core.runners.ansible_runner import AnsibleRunner
from infrafoundry.core.runners.opentofu_runner import OpenTofuRunner
from infrafoundry.core.runners.opnsense_direct_runner import OPNsenseDirectRunner
from infrafoundry.core.runners.pulumi_runner import PulumiRunner
from infrafoundry.core.runners.pyinfra_runner import PyInfraRunner
from infrafoundry.core.runners.terraform_runner import TerraformRunner

PlanCapable = (
    TerraformRunner
    | OpenTofuRunner
    | AnsibleRunner
    | PyInfraRunner
    | PulumiRunner
    | OPNsenseDirectRunner
)
DestroyCapable = TerraformRunner | OpenTofuRunner | PulumiRunner | OPNsenseDirectRunner


def _as_plannable(runner: PlanCapable) -> Plannable:
    """Return the runner typed as ``Plannable``; mypy rejects this if one drifts."""
    return runner


def _as_applyable(runner: PlanCapable) -> Applyable:
    """Return the runner typed as ``Applyable``; mypy rejects this if one drifts."""
    return runner


def _as_destroyable(runner: DestroyCapable) -> Destroyable:
    """Return the runner typed as ``Destroyable``; mypy rejects this if one drifts."""
    return runner


def _as_state_aware(runner: TerraformRunner | OpenTofuRunner) -> StateAware:
    """Return the runner typed as ``StateAware``; mypy rejects this if one drifts."""
    return runner


ALL_RUNNERS = [
    TerraformRunner,
    OpenTofuRunner,
    AnsibleRunner,
    PyInfraRunner,
    PulumiRunner,
    OPNsenseDirectRunner,
]
DESTROY_RUNNERS = [TerraformRunner, OpenTofuRunner, PulumiRunner, OPNsenseDirectRunner]


@pytest.mark.parametrize("cls", ALL_RUNNERS)
def test_runner_is_plannable_and_applyable(cls: type[PlanCapable]) -> None:
    runner = cls()

    assert isinstance(_as_plannable(runner), Plannable)
    assert isinstance(_as_applyable(runner), Applyable)


@pytest.mark.parametrize("cls", DESTROY_RUNNERS)
def test_runner_is_destroyable(cls: type[DestroyCapable]) -> None:
    assert isinstance(_as_destroyable(cls()), Destroyable)


@pytest.mark.parametrize("cls", [TerraformRunner, OpenTofuRunner])
def test_terraform_runner_is_state_aware(cls: type[TerraformRunner]) -> None:
    assert isinstance(_as_state_aware(cls()), StateAware)


@pytest.mark.parametrize("method", ["apply", "destroy"])
def test_terraform_auto_approve_defaults_to_false(method: str) -> None:
    runner = TerraformRunner()
    provider = cast(ProviderBase, MagicMock())

    with patch.object(runner, "_run_terraform", return_value={"success": True}) as run:
        getattr(runner, method)(provider)

    assert run.call_args.kwargs["auto_approve"] is False


@pytest.mark.parametrize("method", ["apply", "destroy"])
def test_terraform_auto_approve_is_passed_through(method: str) -> None:
    runner = TerraformRunner()
    provider = cast(ProviderBase, MagicMock())

    with patch.object(runner, "_run_terraform", return_value={"success": True}) as run:
        getattr(runner, method)(provider, auto_approve=True)

    assert run.call_args.kwargs["auto_approve"] is True


def _pulumi_plan(tmp_path: Path, returncode: int, stderr: str = "") -> dict[str, Any]:
    (tmp_path / "pulumi" / "net").mkdir(parents=True)
    provider = cast(ProviderBase, SimpleNamespace(output_dir=tmp_path, name="net"))
    completed = SimpleNamespace(returncode=returncode, stdout="preview", stderr=stderr)

    with (
        patch("shutil.which", return_value="/usr/bin/pulumi"),
        patch("subprocess.run", return_value=completed),
    ):
        return dict(PulumiRunner().plan(provider))


def test_pulumi_plan_success_has_no_error_key(tmp_path: Path) -> None:
    result = _pulumi_plan(tmp_path, returncode=0)

    assert result == {"success": True, "exit_code": 0, "output": "preview"}


def test_pulumi_plan_failure_carries_stderr_as_error(tmp_path: Path) -> None:
    result = _pulumi_plan(tmp_path, returncode=1, stderr="stack not found")

    assert result["success"] is False
    assert result["exit_code"] == 1
    assert result["error"] == "stack not found"
