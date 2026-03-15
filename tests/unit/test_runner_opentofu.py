"""Unit tests for OpenTofuRunner."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from infrafoundry.core.provider import ProviderBase
from infrafoundry.core.runners.opentofu_runner import OpenTofuRunner
from infrafoundry.core.runners.terraform_runner import TerraformRunner


@pytest.fixture
def runner() -> OpenTofuRunner:
    """Create OpenTofuRunner instance."""
    return OpenTofuRunner()


@pytest.fixture
def provider(tmp_path: Path) -> MagicMock:
    """Create a mock provider with terraform_dir."""
    mock = MagicMock(spec=ProviderBase)
    mock.terraform_dir = tmp_path / "terraform"
    mock.terraform_dir.mkdir(parents=True)
    return mock


class TestOpenTofuRunnerBasics:
    """Basic tests for OpenTofuRunner identity and inheritance."""

    def test_inherits_from_terraform_runner(self, runner: OpenTofuRunner) -> None:
        """OpenTofuRunner must be a subclass of TerraformRunner."""
        assert isinstance(runner, TerraformRunner)

    def test_tool_name_returns_tofu(self, runner: OpenTofuRunner) -> None:
        """tool_name must return 'tofu' for binary resolution."""
        assert runner.tool_name == "tofu"

    def test_priority_same_as_terraform(self, runner: OpenTofuRunner) -> None:
        """OpenTofu should have the same priority as Terraform (provisioning first)."""
        assert runner.priority == 0

    def test_is_available(self, runner: OpenTofuRunner) -> None:
        """Availability depends on tofu binary."""
        with patch("shutil.which", return_value="/usr/bin/tofu"):
            assert runner.is_available()
        with patch("shutil.which", return_value=None):
            assert not runner.is_available()


class TestOpenTofuRunnerOperations:
    """Test that inherited operations use the tofu binary."""

    def test_initialize_uses_tofu_binary(self, runner: OpenTofuRunner, provider: MagicMock) -> None:
        """Initialize should invoke tofu, not terraform."""
        with (
            patch("shutil.which", return_value="/usr/bin/tofu"),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value = SimpleNamespace(returncode=0, stdout="ok", stderr="")
            result = runner.initialize(provider.terraform_dir)

        assert result["success"]
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "/usr/bin/tofu"
        assert cmd[1] == "init"

    def test_plan_uses_tofu_binary(self, runner: OpenTofuRunner, provider: MagicMock) -> None:
        """Plan should use tofu binary."""
        with (
            patch("shutil.which", return_value="/usr/bin/tofu"),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.side_effect = [
                SimpleNamespace(returncode=0, stdout="", stderr=""),  # init
                SimpleNamespace(returncode=0, stdout="Plan: 1 to add", stderr=""),
            ]
            result = runner.plan(provider)

        assert result["success"]

    def test_apply_uses_tofu_binary(self, runner: OpenTofuRunner, provider: MagicMock) -> None:
        """Apply should use tofu binary with -auto-approve."""
        mock_process = MagicMock()
        mock_process.stdout = iter([])
        mock_process.stderr = MagicMock()
        mock_process.stderr.__iter__ = MagicMock(return_value=iter([]))
        mock_process.returncode = 0
        mock_process.wait.return_value = 0

        with (
            patch("shutil.which", return_value="/usr/bin/tofu"),
            patch("subprocess.run") as mock_run,
            patch("subprocess.Popen", return_value=mock_process) as mock_popen,
        ):
            # subprocess.run is used for init
            mock_run.return_value = SimpleNamespace(returncode=0, stdout="", stderr="")
            runner.apply(provider, auto_approve=True)

        args = mock_popen.call_args[0][0]
        assert args[0] == "/usr/bin/tofu"
        assert "-auto-approve" in args

    def test_get_version_uses_tofu_binary(self, runner: OpenTofuRunner) -> None:
        """get_version should call tofu version -json."""
        version_data = {"terraform_version": "1.8.0"}
        with (
            patch("shutil.which", return_value="/usr/bin/tofu"),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value = SimpleNamespace(
                returncode=0, stdout=json.dumps(version_data), stderr=""
            )
            version = runner.get_version()

        assert version == "1.8.0"
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "/usr/bin/tofu"

    def test_get_resource_ids(self, runner: OpenTofuRunner, provider: MagicMock) -> None:
        """Resource IDs parsed from tofu show output."""
        state = {
            "values": {
                "root_module": {
                    "resources": [
                        {"address": "proxmox_vm.vm1", "name": "vm1"},
                    ]
                }
            }
        }
        with (
            patch("shutil.which", return_value="/usr/bin/tofu"),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value = SimpleNamespace(stdout=json.dumps(state), returncode=0)
            resource_ids = runner.get_resource_ids(provider)
        assert resource_ids == {"vm1": "proxmox_vm.vm1"}

    def test_parse_plan_for_drift(self, runner: OpenTofuRunner) -> None:
        """Plan parser works identically to TerraformRunner."""
        output = "Plan: 2 to add, 1 to change, 0 to destroy"
        result = runner.parse_plan_for_drift({"output": output})
        assert result["has_changes"] is True
        assert result["to_add"] == 2
        assert result["to_change"] == 1


class TestOpenTofuRunnerRegistry:
    """Test registry integration."""

    def test_registry_key_is_opentofu(self) -> None:
        """RunnerRegistry derives key 'opentofu' from class name."""
        from infrafoundry.core.runners.runner_registry import RunnerRegistry

        registry = RunnerRegistry()
        registry.register(OpenTofuRunner)
        assert "opentofu" in registry.list_runners()

    def test_create_runner_from_registry(self) -> None:
        """create_runner('opentofu') should return an OpenTofuRunner instance."""
        from infrafoundry.core.runners.runner_registry import RunnerRegistry

        registry = RunnerRegistry()
        registry.register(OpenTofuRunner)
        runner = registry.create_runner("opentofu")
        assert isinstance(runner, OpenTofuRunner)
        assert runner.tool_name == "tofu"
