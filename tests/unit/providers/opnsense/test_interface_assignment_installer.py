"""Unit tests for ``infrafoundry.providers.opnsense.extensions.interface_assignments.installer``.

Coverage:
    - ``load_ssh_target`` env-var resolution + fallbacks (host derived
      from API URL, optional key, port parsing, override of install
      path).
    - ``compute_local_checksum`` SHA-256 hex digest.
    - ``fetch_remote_checksum`` (SSH probe with mocked subprocess).
    - ``verify_installed_checksum`` match / mismatch / missing.
    - ``install_controller`` fast-path skip / fresh install / SCP
      failure / chmod failure / restart failure / post-install
      mismatch.
    - ``ensure_installed`` runs the SSH-tools-present check and
      proxies to ``install_controller``.
    - ``ensure_installed`` propagates RuntimeError from
      ``load_ssh_target`` when SSH credentials are missing.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from infrafoundry.providers.opnsense.extensions.interface_assignments import installer

# ---------------------------------------------------------------------------
# load_ssh_target
# ---------------------------------------------------------------------------


class TestLoadSshTarget:
    def test_minimal_happy_path(self, tmp_path: Path) -> None:
        key = tmp_path / "id_rsa"
        key.write_text("dummy", encoding="utf-8")
        env = {
            "OPNSENSE_SSH_HOST": "fw.lan",
            "OPNSENSE_SSH_KEY": str(key),
        }
        target = installer.load_ssh_target(env)
        assert target.host == "fw.lan"
        assert target.user == "root"
        assert target.port == 22
        assert target.key_path == key
        assert target.install_path.endswith("AssignSettingsController.php")

    def test_overrides_user_and_port(self, tmp_path: Path) -> None:
        key = tmp_path / "id_rsa"
        key.write_text("dummy", encoding="utf-8")
        env = {
            "OPNSENSE_SSH_HOST": "fw.lan",
            "OPNSENSE_SSH_KEY": str(key),
            "OPNSENSE_SSH_USER": "admin",
            "OPNSENSE_SSH_PORT": "2222",
            "OPNSENSE_INSTALL_PATH": "/custom/path/Foo.php",
        }
        target = installer.load_ssh_target(env)
        assert target.user == "admin"
        assert target.port == 2222
        assert target.install_path == "/custom/path/Foo.php"

    def test_missing_host_raises_when_no_api_url(self, tmp_path: Path) -> None:
        key = tmp_path / "id_rsa"
        key.write_text("d", encoding="utf-8")
        env = {"OPNSENSE_SSH_KEY": str(key)}
        with pytest.raises(RuntimeError, match="OPNSENSE_SSH_HOST"):
            installer.load_ssh_target(env)

    def test_host_derived_from_api_url(self) -> None:
        env = {"OPNSENSE_API_URL": "https://opnsense-a:8443"}
        target = installer.load_ssh_target(env)
        assert target.host == "opnsense-a"

    def test_explicit_ssh_host_wins_over_api_url(self) -> None:
        env = {
            "OPNSENSE_SSH_HOST": "fw.internal",
            "OPNSENSE_API_URL": "https://opnsense-a",
        }
        target = installer.load_ssh_target(env)
        assert target.host == "fw.internal"

    def test_missing_key_is_optional(self) -> None:
        env = {"OPNSENSE_SSH_HOST": "fw"}
        target = installer.load_ssh_target(env)
        assert target.key_path is None

    def test_nonexistent_key_path_raises(self, tmp_path: Path) -> None:
        env = {
            "OPNSENSE_SSH_HOST": "fw",
            "OPNSENSE_SSH_KEY": str(tmp_path / "missing"),
        }
        with pytest.raises(RuntimeError, match="does not exist"):
            installer.load_ssh_target(env)

    def test_invalid_port_raises(self, tmp_path: Path) -> None:
        key = tmp_path / "id_rsa"
        key.write_text("d", encoding="utf-8")
        env = {
            "OPNSENSE_SSH_HOST": "fw",
            "OPNSENSE_SSH_KEY": str(key),
            "OPNSENSE_SSH_PORT": "not-a-number",
        }
        with pytest.raises(RuntimeError, match="must be an integer"):
            installer.load_ssh_target(env)


class TestSshTargetProperties:
    def test_remote_property(self) -> None:
        t = installer.SshTarget(host="fw", user="root", port=22, key_path=None, install_path="/x")
        assert t.remote == "root@fw"


# ---------------------------------------------------------------------------
# Local checksum + path
# ---------------------------------------------------------------------------


class TestLocalChecksum:
    def test_compute_local_checksum_known_value(self, tmp_path: Path) -> None:
        f = tmp_path / "x.txt"
        f.write_bytes(b"hello world")
        # Known SHA-256 of b"hello world".
        expected = "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"
        assert installer.compute_local_checksum(f) == expected

    def test_local_controller_path_resolves(self) -> None:
        path = installer.local_controller_path()
        assert path.name == "AssignSettingsController.php"
        assert path.exists()


# ---------------------------------------------------------------------------
# SSH flow (subprocess.run patched)
# ---------------------------------------------------------------------------


def _completed(
    *, returncode: int = 0, stdout: str = "", stderr: str = ""
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def _target(tmp_path: Path) -> installer.SshTarget:
    key = tmp_path / "id_rsa"
    key.write_text("d", encoding="utf-8")
    return installer.SshTarget(
        host="fw.lan",
        user="root",
        port=22,
        key_path=key,
        install_path="/usr/local/Foo.php",
    )


class TestFetchRemoteChecksum:
    def test_present(self, tmp_path: Path) -> None:
        target = _target(tmp_path)
        with patch.object(installer, "_run") as run:
            run.return_value = _completed(stdout="abc123def456789\n")
            sha = installer.fetch_remote_checksum(target)
        assert sha == "abc123def456789"

    def test_missing(self, tmp_path: Path) -> None:
        target = _target(tmp_path)
        with patch.object(installer, "_run") as run:
            run.return_value = _completed(stdout="MISSING\n")
            sha = installer.fetch_remote_checksum(target)
        assert sha is None

    def test_empty_stdout_returns_none(self, tmp_path: Path) -> None:
        target = _target(tmp_path)
        with patch.object(installer, "_run") as run:
            run.return_value = _completed(stdout="")
            sha = installer.fetch_remote_checksum(target)
        assert sha is None

    def test_ssh_failure_raises(self, tmp_path: Path) -> None:
        target = _target(tmp_path)
        with patch.object(installer, "_run") as run:
            run.return_value = _completed(returncode=255, stderr="connection refused")
            with pytest.raises(RuntimeError, match="SSH probe failed"):
                installer.fetch_remote_checksum(target)


class TestVerifyInstalledChecksum:
    def test_match(self, tmp_path: Path) -> None:
        target = _target(tmp_path)
        with patch.object(installer, "fetch_remote_checksum") as remote:
            local_sum = installer.compute_local_checksum(installer.local_controller_path())
            remote.return_value = local_sum
            matches, remote_sum, ls = installer.verify_installed_checksum(target)
        assert matches is True
        assert remote_sum == local_sum
        assert ls == local_sum

    def test_mismatch(self, tmp_path: Path) -> None:
        target = _target(tmp_path)
        with patch.object(installer, "fetch_remote_checksum") as remote:
            remote.return_value = "different-sha"
            matches, _, _ = installer.verify_installed_checksum(target)
        assert matches is False

    def test_missing_returns_false(self, tmp_path: Path) -> None:
        target = _target(tmp_path)
        with patch.object(installer, "fetch_remote_checksum") as remote:
            remote.return_value = None
            matches, remote_sum, _ = installer.verify_installed_checksum(target)
        assert matches is False
        assert remote_sum is None


class TestInstallController:
    def test_fast_path_skips_when_already_current(self, tmp_path: Path) -> None:
        target = _target(tmp_path)
        with patch.object(installer, "verify_installed_checksum") as verify:
            local_sum = installer.compute_local_checksum(installer.local_controller_path())
            verify.return_value = (True, local_sum, local_sum)
            installed = installer.install_controller(target)
        assert installed is False

    def test_force_overrides_fast_path(self, tmp_path: Path) -> None:
        target = _target(tmp_path)
        with (
            patch.object(installer, "verify_installed_checksum") as verify,
            patch.object(installer, "_run") as run,
        ):
            local_sum = installer.compute_local_checksum(installer.local_controller_path())
            # First call: pre-install (already current). Second call:
            # post-install verify (still current).
            verify.side_effect = [
                (True, local_sum, local_sum),
                (True, local_sum, local_sum),
            ]
            run.return_value = _completed(returncode=0)
            installed = installer.install_controller(target, force=True)
        assert installed is True

    def test_runs_full_lifecycle_on_mismatch(self, tmp_path: Path) -> None:
        target = _target(tmp_path)
        with (
            patch.object(installer, "verify_installed_checksum") as verify,
            patch.object(installer, "_run") as run,
        ):
            local_sum = installer.compute_local_checksum(installer.local_controller_path())
            verify.side_effect = [(False, None, local_sum), (True, local_sum, local_sum)]
            run.return_value = _completed(returncode=0)
            installed = installer.install_controller(target)
        assert installed is True
        # SCP + chmod + 2x service restart = 4 _run calls.
        assert run.call_count == 4
        # First call must be SCP; following calls must use SSH.
        assert run.call_args_list[0].args[0][0] == "scp"
        for c in run.call_args_list[1:]:
            assert c.args[0][0] == "ssh"

    def test_runs_lifecycle_on_first_install(self, tmp_path: Path) -> None:
        # Same as mismatch but the pre-install probe explicitly returns
        # a None remote_sum (controller missing on box).
        target = _target(tmp_path)
        with (
            patch.object(installer, "verify_installed_checksum") as verify,
            patch.object(installer, "_run") as run,
        ):
            local_sum = installer.compute_local_checksum(installer.local_controller_path())
            verify.side_effect = [(False, None, local_sum), (True, local_sum, local_sum)]
            run.return_value = _completed(returncode=0)
            installer.install_controller(target)
        assert run.call_count == 4

    def test_scp_failure_raises(self, tmp_path: Path) -> None:
        target = _target(tmp_path)
        with (
            patch.object(installer, "verify_installed_checksum") as verify,
            patch.object(installer, "_run") as run,
        ):
            local_sum = installer.compute_local_checksum(installer.local_controller_path())
            verify.return_value = (False, None, local_sum)
            run.return_value = _completed(returncode=1, stderr="scp: permission denied")
            with pytest.raises(RuntimeError, match="SCP failed"):
                installer.install_controller(target)

    def test_chmod_failure_raises(self, tmp_path: Path) -> None:
        target = _target(tmp_path)
        with (
            patch.object(installer, "verify_installed_checksum") as verify,
            patch.object(installer, "_run") as run,
        ):
            local_sum = installer.compute_local_checksum(installer.local_controller_path())
            verify.return_value = (False, None, local_sum)
            # SCP succeeds, chmod fails.
            run.side_effect = [
                _completed(returncode=0),  # scp
                _completed(returncode=1, stderr="chmod: permission denied"),  # chmod
            ]
            with pytest.raises(RuntimeError, match="chmod failed"):
                installer.install_controller(target)

    def test_service_restart_failure_raises(self, tmp_path: Path) -> None:
        target = _target(tmp_path)
        with (
            patch.object(installer, "verify_installed_checksum") as verify,
            patch.object(installer, "_run") as run,
        ):
            local_sum = installer.compute_local_checksum(installer.local_controller_path())
            verify.return_value = (False, None, local_sum)
            # SCP + chmod succeed; configd restart fails.
            run.side_effect = [
                _completed(returncode=0),  # scp
                _completed(returncode=0),  # chmod
                _completed(returncode=1, stderr="service: not running"),  # configd
            ]
            with pytest.raises(RuntimeError, match="configd"):
                installer.install_controller(target)

    def test_post_check_mismatch_raises(self, tmp_path: Path) -> None:
        target = _target(tmp_path)
        with (
            patch.object(installer, "verify_installed_checksum") as verify,
            patch.object(installer, "_run") as run,
        ):
            local_sum = installer.compute_local_checksum(installer.local_controller_path())
            verify.side_effect = [
                (False, None, local_sum),
                (False, "different-sha", local_sum),
            ]
            run.return_value = _completed(returncode=0)
            with pytest.raises(RuntimeError, match="Post-install checksum mismatch"):
                installer.install_controller(target)

    def test_local_controller_missing_raises(self, tmp_path: Path) -> None:
        target = _target(tmp_path)
        with patch.object(installer, "local_controller_path") as local:
            local.return_value = tmp_path / "does-not-exist.php"
            with pytest.raises(RuntimeError, match="Local controller not found"):
                installer.install_controller(target)


# ---------------------------------------------------------------------------
# ensure_installed (manager-facing entry point)
# ---------------------------------------------------------------------------


class TestEnsureInstalled:
    def test_ensures_ssh_tools_then_calls_install(self, tmp_path: Path) -> None:
        target = _target(tmp_path)
        with (
            patch.object(installer, "_ensure_ssh_tools_present") as ensure_tools,
            patch.object(installer, "install_controller") as ic,
        ):
            ic.return_value = False
            installer.ensure_installed(target)
        ensure_tools.assert_called_once()
        ic.assert_called_once_with(target)

    def test_uses_load_ssh_target_when_no_target_passed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        key = tmp_path / "id_rsa"
        key.write_text("d", encoding="utf-8")
        monkeypatch.setenv("OPNSENSE_SSH_HOST", "fw")
        monkeypatch.setenv("OPNSENSE_SSH_KEY", str(key))
        with (
            patch.object(installer, "_ensure_ssh_tools_present"),
            patch.object(installer, "install_controller") as ic,
        ):
            ic.return_value = False
            installer.ensure_installed()
        # install_controller called with the SshTarget that load_ssh_target produced.
        called_target = ic.call_args.args[0]
        assert isinstance(called_target, installer.SshTarget)
        assert called_target.host == "fw"

    def test_propagates_load_ssh_target_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # No OPNSENSE_SSH_HOST and no OPNSENSE_API_URL.
        for key in ("OPNSENSE_SSH_HOST", "OPNSENSE_API_URL", "OPNSENSE_SSH_KEY"):
            monkeypatch.delenv(key, raising=False)
        with (
            patch.object(installer, "_ensure_ssh_tools_present"),
            pytest.raises(RuntimeError, match="OPNSENSE_SSH_HOST"),
        ):
            installer.ensure_installed()

    def test_fast_path_returns_false_when_already_current(self, tmp_path: Path) -> None:
        target = _target(tmp_path)
        with (
            patch.object(installer, "_ensure_ssh_tools_present"),
            patch.object(installer, "install_controller") as ic,
        ):
            ic.return_value = False
            assert installer.ensure_installed(target) is False

    def test_returns_true_when_install_happened(self, tmp_path: Path) -> None:
        target = _target(tmp_path)
        with (
            patch.object(installer, "_ensure_ssh_tools_present"),
            patch.object(installer, "install_controller") as ic,
        ):
            ic.return_value = True
            assert installer.ensure_installed(target) is True


class TestEnsureSshToolsPresent:
    def test_raises_when_missing(self) -> None:
        with (
            patch.object(installer.shutil, "which", return_value=None),
            pytest.raises(RuntimeError, match="not on PATH"),
        ):
            installer._ensure_ssh_tools_present()

    def test_passes_when_present(self) -> None:
        with patch.object(installer.shutil, "which", return_value="/usr/bin/ssh"):
            # Must not raise.
            installer._ensure_ssh_tools_present()


# ---------------------------------------------------------------------------
# Internal arg-builders
# ---------------------------------------------------------------------------


class TestArgBuilders:
    def test_identity_args_with_key(self, tmp_path: Path) -> None:
        target = _target(tmp_path)
        args = installer._identity_args(target)
        assert args[0] == "-i"
        assert args[1] == str(target.key_path)

    def test_identity_args_without_key(self) -> None:
        target = installer.SshTarget(
            host="fw", user="root", port=22, key_path=None, install_path="/x"
        )
        assert installer._identity_args(target) == []

    def test_ssh_args_includes_host(self, tmp_path: Path) -> None:
        target = _target(tmp_path)
        args = installer._ssh_args(target)
        assert args[0] == "ssh"
        assert "root@fw.lan" in args
        assert "BatchMode=yes" in args

    def test_scp_args_targets_remote_path(self, tmp_path: Path) -> None:
        target = _target(tmp_path)
        src = tmp_path / "x.php"
        src.write_text("d", encoding="utf-8")
        args = installer._scp_args(target, src, "/remote/path.php")
        assert args[0] == "scp"
        assert args[-1] == "root@fw.lan:/remote/path.php"

    def test_run_uses_shell_false(self) -> None:
        # Defensive: never run shell=True. The wrapper takes a list
        # and invokes subprocess.run(...).
        with patch("subprocess.run") as sp_run:
            sp_run.return_value = _completed()
            installer._run(["echo", "hi"])
        # subprocess.run defaults to shell=False; verify nothing
        # accidentally enabled it.
        assert sp_run.call_args.kwargs.get("shell", False) is False
