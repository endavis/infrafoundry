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


def test_initialize_runs_init_even_when_already_initialized(
    runner: TerraformRunner, provider: MagicMock
) -> None:
    """Init is always invoked, even when ``.terraform/`` is already present.

    Regression test for #524: the previous short-circuit trusted
    ``.terraform/`` presence as proof of consistency and hid ``provider.tf``
    changes (e.g. a newly-declared provider) until apply time, producing
    an ``Inconsistent dependency lock file`` error. ``terraform init`` is
    idempotent and cheap, so we always run it.
    """
    (provider.terraform_dir / ".terraform").mkdir()
    with (
        patch("shutil.which", return_value="/usr/bin/terraform"),
        patch("subprocess.run") as mock_run,
    ):
        mock_run.return_value = SimpleNamespace(returncode=0, stdout="", stderr="")
        result = runner.initialize(provider.terraform_dir)
    assert result["success"]
    mock_run.assert_called_once()
    assert mock_run.call_args[0][0][1] == "init"
    # No special flags should be added in the default re-init case
    assert "-reconfigure" not in mock_run.call_args[0][0]
    assert "-upgrade" not in mock_run.call_args[0][0]


def test_initialize_detects_stale_provider_lock_scenario(
    runner: TerraformRunner, provider: MagicMock
) -> None:
    """Documents the #524 repro: stale ``.terraform.lock.hcl`` after a new provider is added.

    Creates a working dir with ``.terraform/``, a stale lock file containing
    only provider A, and a ``provider.tf`` declaring both A and B. Before
    the fix, initialize short-circuited and apply later failed with
    ``Inconsistent dependency lock file``. After the fix, init runs and
    (in a real terraform invocation) would download B and update the lock.
    Here we mock subprocess and assert init is actually called.
    """
    (provider.terraform_dir / ".terraform").mkdir()
    (provider.terraform_dir / ".terraform.lock.hcl").write_text(
        'provider "registry.terraform.io/bpg/proxmox" {\n  version = "0.98.1"\n}\n'
    )
    (provider.terraform_dir / "provider.tf").write_text(
        "terraform {\n  required_providers {\n"
        '    proxmox = { source = "bpg/proxmox" }\n'
        '    cloudinit = { source = "hashicorp/cloudinit" }\n'
        "  }\n}\n"
    )
    with (
        patch("shutil.which", return_value="/usr/bin/terraform"),
        patch("subprocess.run") as mock_run,
    ):
        mock_run.return_value = SimpleNamespace(returncode=0, stdout="", stderr="")
        result = runner.initialize(provider.terraform_dir)
    assert result["success"]
    mock_run.assert_called_once()
    assert mock_run.call_args[0][0][1] == "init"


def test_initialize_preserves_backend_change_reconfigure(
    runner: TerraformRunner, provider: MagicMock
) -> None:
    """Backend swap detection still adds ``-reconfigure`` to the init command."""
    (provider.terraform_dir / ".terraform").mkdir()
    # Simulate prior local-backend state + a new backend.tf (i.e. a swap TO remote)
    (provider.terraform_dir / ".terraform" / "terraform.tfstate").write_text(
        json.dumps({"backend": {"type": "local"}})
    )
    (provider.terraform_dir / "backend.tf").write_text('terraform { backend "s3" {} }\n')
    with (
        patch("shutil.which", return_value="/usr/bin/terraform"),
        patch("subprocess.run") as mock_run,
    ):
        mock_run.return_value = SimpleNamespace(returncode=0, stdout="", stderr="")
        result = runner.initialize(provider.terraform_dir)
    assert result["success"]
    args = mock_run.call_args[0][0]
    assert "-reconfigure" in args


def test_initialize_honors_explicit_upgrade_flag(
    runner: TerraformRunner, provider: MagicMock
) -> None:
    """Explicit ``upgrade=True`` still triggers ``terraform init -upgrade``."""
    (provider.terraform_dir / ".terraform").mkdir()
    with (
        patch("shutil.which", return_value="/usr/bin/terraform"),
        patch("subprocess.run") as mock_run,
    ):
        mock_run.return_value = SimpleNamespace(returncode=0, stdout="", stderr="")
        runner.initialize(provider.terraform_dir, upgrade=True)
    args = mock_run.call_args[0][0]
    assert "-upgrade" in args


def test_initialize_honors_explicit_reconfigure_flag(
    runner: TerraformRunner, provider: MagicMock
) -> None:
    """Explicit ``reconfigure=True`` still triggers ``terraform init -reconfigure``."""
    (provider.terraform_dir / ".terraform").mkdir()
    with (
        patch("shutil.which", return_value="/usr/bin/terraform"),
        patch("subprocess.run") as mock_run,
    ):
        mock_run.return_value = SimpleNamespace(returncode=0, stdout="", stderr="")
        runner.initialize(provider.terraform_dir, reconfigure=True)
    args = mock_run.call_args[0][0]
    assert "-reconfigure" in args


def test_initialize_fresh_directory(runner: TerraformRunner, provider: MagicMock) -> None:
    """Fresh directory (no ``.terraform/``) runs plain ``terraform init``."""
    # provider fixture already leaves .terraform absent
    assert not (provider.terraform_dir / ".terraform").exists()
    with (
        patch("shutil.which", return_value="/usr/bin/terraform"),
        patch("subprocess.run") as mock_run,
    ):
        mock_run.return_value = SimpleNamespace(returncode=0, stdout="", stderr="")
        result = runner.initialize(provider.terraform_dir)
    assert result["success"]
    args = mock_run.call_args[0][0]
    assert args[1] == "init"
    assert "-reconfigure" not in args
    assert "-upgrade" not in args


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
    mock_process = MagicMock()
    mock_process.stdout = iter([])
    mock_process.stderr = MagicMock()
    mock_process.stderr.__iter__ = MagicMock(return_value=iter([]))
    mock_process.returncode = 0
    mock_process.wait.return_value = 0

    with (
        patch("shutil.which", return_value="/usr/bin/terraform"),
        patch("subprocess.run") as mock_run,
        patch("subprocess.Popen", return_value=mock_process) as mock_popen,
    ):
        # subprocess.run is used for init
        mock_run.return_value = SimpleNamespace(returncode=0, stdout="", stderr="")
        runner.apply(provider, auto_approve=True)

        # Popen is used for apply with -json
        mock_popen.assert_called_once()
        args = mock_popen.call_args[0][0]
        assert "-auto-approve" in args
        assert "-json" in args
        assert mock_popen.call_args[1]["cwd"] == provider.terraform_dir


def test_apply_passes_parallelism_flag(runner: TerraformRunner, provider: MagicMock) -> None:
    """Apply passes -parallelism=N when requested."""
    mock_process = MagicMock()
    mock_process.stdout = iter([])
    mock_process.stderr = MagicMock()
    mock_process.stderr.__iter__ = MagicMock(return_value=iter([]))
    mock_process.returncode = 0
    mock_process.wait.return_value = 0

    with (
        patch("shutil.which", return_value="/usr/bin/terraform"),
        patch("subprocess.run") as mock_run,
        patch("subprocess.Popen", return_value=mock_process) as mock_popen,
    ):
        mock_run.return_value = SimpleNamespace(returncode=0, stdout="", stderr="")
        runner.apply(provider, auto_approve=True, parallelism=1)

        args = mock_popen.call_args[0][0]
        assert "-parallelism=1" in args
        assert "-auto-approve" in args


def test_apply_omits_parallelism_when_none(runner: TerraformRunner, provider: MagicMock) -> None:
    """Apply does not add -parallelism when parallelism is None."""
    mock_process = MagicMock()
    mock_process.stdout = iter([])
    mock_process.stderr = MagicMock()
    mock_process.stderr.__iter__ = MagicMock(return_value=iter([]))
    mock_process.returncode = 0
    mock_process.wait.return_value = 0

    with (
        patch("shutil.which", return_value="/usr/bin/terraform"),
        patch("subprocess.run") as mock_run,
        patch("subprocess.Popen", return_value=mock_process) as mock_popen,
    ):
        mock_run.return_value = SimpleNamespace(returncode=0, stdout="", stderr="")
        runner.apply(provider, auto_approve=True)

        args = mock_popen.call_args[0][0]
        assert not any(a.startswith("-parallelism") for a in args)


def test_destroy_passes_parallelism_flag(runner: TerraformRunner, provider: MagicMock) -> None:
    """Destroy passes -parallelism=N when requested."""
    mock_process = MagicMock()
    mock_process.stdout = iter([])
    mock_process.stderr = MagicMock()
    mock_process.stderr.__iter__ = MagicMock(return_value=iter([]))
    mock_process.returncode = 0
    mock_process.wait.return_value = 0

    with (
        patch("shutil.which", return_value="/usr/bin/terraform"),
        patch("subprocess.run") as mock_run,
        patch("subprocess.Popen", return_value=mock_process) as mock_popen,
    ):
        mock_run.return_value = SimpleNamespace(returncode=0, stdout="", stderr="")
        runner.destroy(provider, auto_approve=True, parallelism=2)

        args = mock_popen.call_args[0][0]
        assert "-parallelism=2" in args


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


class TestResolveTargets:
    """Tests for _resolve_terraform_targets."""

    def test_exact_match(self, runner: TerraformRunner, tmp_path: Path) -> None:
        """Exact resource name matches."""
        tf_file = tmp_path / "main.tf"
        tf_file.write_text('resource "esxi_guest" "my_vm" {\n}\n')
        targets = runner._resolve_terraform_targets(tmp_path, ["my-vm"])
        assert targets == ["esxi_guest.my_vm"]

    def test_prefix_suffix_match(self, runner: TerraformRunner, tmp_path: Path) -> None:
        """Resource with prefix matches via suffix (e.g., ovf_ontap_node_01)."""
        tf_file = tmp_path / "ovf.tf"
        tf_file.write_text('resource "terraform_data" "ovf_ontap_node_01" {\n}\n')
        targets = runner._resolve_terraform_targets(tmp_path, ["ontap-node-01"])
        assert targets == ["terraform_data.ovf_ontap_node_01"]

    def test_no_match_returns_empty(self, runner: TerraformRunner, tmp_path: Path) -> None:
        """Unmatched filter returns empty list."""
        tf_file = tmp_path / "main.tf"
        tf_file.write_text('resource "esxi_guest" "other_vm" {\n}\n')
        targets = runner._resolve_terraform_targets(tmp_path, ["my-vm"])
        assert targets == []

    def test_no_false_suffix_match(self, runner: TerraformRunner, tmp_path: Path) -> None:
        """Suffix match requires underscore separator (no partial matches)."""
        tf_file = tmp_path / "main.tf"
        tf_file.write_text('resource "esxi_guest" "bigontap_node_01" {\n}\n')
        targets = runner._resolve_terraform_targets(tmp_path, ["node-01"])
        assert targets == ["esxi_guest.bigontap_node_01"]

    def test_multiple_resources_matched(self, runner: TerraformRunner, tmp_path: Path) -> None:
        """Multiple resources can match from different files."""
        (tmp_path / "a.tf").write_text('resource "terraform_data" "ovf_node_01" {\n}\n')
        (tmp_path / "b.tf").write_text('resource "terraform_data" "ovf_node_02" {\n}\n')
        targets = runner._resolve_terraform_targets(tmp_path, ["node-01", "node-02"])
        assert sorted(targets) == [
            "terraform_data.ovf_node_01",
            "terraform_data.ovf_node_02",
        ]

    def test_unmatched_filter_skips_terraform(
        self, runner: TerraformRunner, provider: MagicMock
    ) -> None:
        """When no targets match, the apply subprocess is skipped."""
        (provider.terraform_dir / "main.tf").write_text('resource "esxi_guest" "other_vm" {\n}\n')
        (provider.terraform_dir / ".terraform").mkdir()
        with (
            patch("shutil.which", return_value="/usr/bin/terraform"),
            patch("subprocess.run") as mock_run,
            patch("subprocess.Popen") as mock_popen,
        ):
            mock_run.return_value = SimpleNamespace(returncode=0, stdout="", stderr="")
            result = runner.apply(provider, auto_approve=True, target_resources=["no-match"])

        assert result["success"]
        # Init runs (via subprocess.run) regardless, but the apply itself
        # (via subprocess.Popen) must be skipped when the filter matches nothing.
        mock_popen.assert_not_called()


class TestDestroyFailureCapture:
    """Tests for _run_terraform capturing stderr/error on destroy failures."""

    def _popen_mock(
        self, returncode: int, stdout_lines: list[str], stderr_lines: list[str]
    ) -> MagicMock:
        process = MagicMock()
        process.stdout = iter([line + "\n" for line in stdout_lines])
        process.stderr = MagicMock()
        process.stderr.__iter__ = MagicMock(
            return_value=iter([line + "\n" for line in stderr_lines])
        )
        process.returncode = returncode
        process.wait.return_value = returncode
        return process

    def test_run_terraform_destroy_includes_stderr_in_response(
        self, runner: TerraformRunner, provider: MagicMock
    ) -> None:
        """On non-zero exit the response surfaces stderr and error keys."""
        (provider.terraform_dir / ".terraform").mkdir()
        process = self._popen_mock(
            returncode=1,
            stdout_lines=[],
            stderr_lines=["Error: Instance cannot be destroyed"],
        )

        with (
            patch("shutil.which", return_value="/usr/bin/terraform"),
            patch("subprocess.run") as mock_run,
            patch("subprocess.Popen", return_value=process),
        ):
            mock_run.return_value = SimpleNamespace(returncode=0, stdout="", stderr="")
            result = runner.destroy(provider, auto_approve=True)

        assert result["success"] is False
        assert result["exit_code"] == 1
        assert "Instance cannot be destroyed" in result["stderr"]
        assert "Instance cannot be destroyed" in result["error"]

    def test_run_terraform_destroy_extracts_diagnostic_summary(
        self, runner: TerraformRunner, provider: MagicMock
    ) -> None:
        """JSON diagnostic summaries are extracted into the error field."""
        (provider.terraform_dir / ".terraform").mkdir()
        diagnostic = json.dumps(
            {
                "@level": "error",
                "@message": "Error: Instance cannot be destroyed",
                "type": "diagnostic",
                "diagnostic": {
                    "summary": "Instance cannot be destroyed",
                    "detail": "Resource has lifecycle.prevent_destroy set",
                },
            }
        )
        process = self._popen_mock(
            returncode=1,
            stdout_lines=[diagnostic],
            stderr_lines=["(from terraform)"],
        )

        with (
            patch("shutil.which", return_value="/usr/bin/terraform"),
            patch("subprocess.run") as mock_run,
            patch("subprocess.Popen", return_value=process),
        ):
            mock_run.return_value = SimpleNamespace(returncode=0, stdout="", stderr="")
            result = runner.destroy(provider, auto_approve=True)

        assert result["success"] is False
        assert "Instance cannot be destroyed" in result["error"]


class TestVerifyDestroyed:
    """Tests for TerraformRunner.verify_destroyed."""

    def test_verify_destroyed_returns_empty_when_state_is_clean(
        self, runner: TerraformRunner, provider: MagicMock
    ) -> None:
        """Empty state means nothing remains."""
        with patch.object(runner, "get_resource_ids", return_value={}):
            assert runner.verify_destroyed(provider, ["vm1"]) == []

    def test_verify_destroyed_returns_remaining_names(
        self, runner: TerraformRunner, provider: MagicMock
    ) -> None:
        """Names still in state are reported; missing ones are not."""
        with patch.object(runner, "get_resource_ids", return_value={"vm1": "proxmox_vm_qemu.vm1"}):
            result = runner.verify_destroyed(provider, ["vm1", "vm2"])
        assert result == ["vm1"]

    def test_verify_destroyed_handles_templated_names(
        self, runner: TerraformRunner, provider: MagicMock
    ) -> None:
        """Suffix matching mirrors _resolve_terraform_targets for templated names."""
        with patch.object(
            runner,
            "get_resource_ids",
            return_value={"ovf_ontap_node_01": "terraform_data.ovf_ontap_node_01"},
        ):
            result = runner.verify_destroyed(provider, ["ontap-node-01"])
        assert result == ["ontap-node-01"]
