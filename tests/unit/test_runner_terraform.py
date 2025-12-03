"""Unit tests for TerraformRunner."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from infrafoundry.core.provider import ProviderBase
from infrafoundry.core.runners.terraform_runner import TerraformRunner


@pytest.fixture
def runner() -> TerraformRunner:
    """Create TerraformRunner instance."""
    return TerraformRunner()


@pytest.fixture
def provider(tmp_path: Path) -> MagicMock:
    """Create a mock provider with terraform_dir."""
    mock = MagicMock(spec=ProviderBase)
    mock.terraform_dir = tmp_path / "terraform"
    mock.terraform_dir.mkdir(parents=True)
    return mock


def test_is_available(runner: TerraformRunner) -> None:
    """Availability depends on terraform binary."""
    with patch("shutil.which", return_value="/usr/bin/terraform"):
        assert runner.is_available()
    with patch("shutil.which", return_value=None):
        assert not runner.is_available()


def test_initialize_skips_when_already_initialized(
    runner: TerraformRunner, provider: MagicMock
) -> None:
    """Initialization short-circuits when .terraform exists."""
    (provider.terraform_dir / ".terraform").mkdir()
    result = runner.initialize(provider.terraform_dir)
    assert result["success"]
    assert "Already initialized" in result["message"]


def test_initialize_missing_binary(runner: TerraformRunner, provider: MagicMock) -> None:
    """Initialization fails when terraform is unavailable."""
    with patch("shutil.which", return_value=None):
        result = runner.initialize(provider.terraform_dir)
    assert not result["success"]
    assert "command not found" in result["error"]


def test_plan_runs_terraform_with_capture(runner: TerraformRunner, provider: MagicMock) -> None:
    """Plan should capture stdout/stderr and set success based on return code."""
    with (
        patch("shutil.which", return_value="/usr/bin/terraform"),
        patch("subprocess.run") as mock_run,
    ):
        mock_run.side_effect = [
            SimpleNamespace(returncode=0, stdout="", stderr=""),  # init
            SimpleNamespace(returncode=0, stdout="Plan: 1 to add", stderr=""),
        ]
        result = runner.plan(provider)

    assert result["success"]
    assert "output" in result
    mock_run.assert_called()  # ensure terraform invoked


def test_apply_adds_auto_approve(runner: TerraformRunner, provider: MagicMock) -> None:
    """Apply passes -auto-approve when requested."""
    with (
        patch("shutil.which", return_value="/usr/bin/terraform"),
        patch("subprocess.run") as mock_run,
    ):
        mock_run.side_effect = [
            SimpleNamespace(returncode=0, stdout="", stderr=""),  # init
            SimpleNamespace(returncode=0, stdout="", stderr=""),
        ]
        runner.apply(provider, auto_approve=True)

        _, kwargs = mock_run.call_args
        args = mock_run.call_args[0][0]
        assert "-auto-approve" in args
        assert kwargs["cwd"] == provider.terraform_dir


def test_validate_config_success(runner: TerraformRunner, provider: MagicMock) -> None:
    """Validate config succeeds when terraform validate exits 0."""
    (provider.terraform_dir / "main.tf").write_text("# test")
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = SimpleNamespace(returncode=0, stdout="ok", stderr="")
        result = runner.validate_config(provider)
    assert result["valid"]


def test_get_resource_ids_parses_state(runner: TerraformRunner, provider: MagicMock) -> None:
    """Resource IDs parsed from terraform show output."""
    state = {
        "values": {
            "root_module": {
                "resources": [
                    {"address": "proxmox_vm.vm1", "name": "vm1"},
                    {"address": "opnsense_fw.rule1", "name": "rule1"},
                ]
            }
        }
    }
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = SimpleNamespace(stdout=json.dumps(state), returncode=0)
        resource_ids = runner.get_resource_ids(provider)
    assert resource_ids == {"vm1": "proxmox_vm.vm1", "rule1": "opnsense_fw.rule1"}


def test_parse_plan_for_drift_detects_changes(runner: TerraformRunner) -> None:
    """Plan parser returns counts and summary."""
    output = "Plan: 1 to add, 2 to change, 0 to destroy"
    result = runner.parse_plan_for_drift({"output": output})
    assert result["has_changes"] is True
    assert result["to_add"] == 1
    assert result["to_change"] == 2
    assert result["to_destroy"] == 0
    assert "add" in result["summary"]
