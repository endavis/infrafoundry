"""Tests for the host key store: ssh-keygen, ssh-keyscan and sops calls (#1581)."""

from __future__ import annotations

import json
import stat
import subprocess
from pathlib import Path
from typing import Any

import pytest

from infrafoundry.core.exceptions import SecretError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.ssh_host_key_store import (
    HostKeyAction,
    ensure_secrets_file,
    fingerprint,
    generate_keypair,
    plan_actions,
    scan_public_key,
    write_entry,
)

PUBLIC = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIExampleSentinelPublicKey0"
SENTINEL_PRIVATE = (
    "-----BEGIN OPENSSH " + "PRIVATE KEY-----\n"
    "SENTINEL-NOT-A-REAL-KEY\n"
    "-----END OPENSSH " + "PRIVATE KEY-----\n"
)


class FakeRun:
    """Record calls and return canned results."""

    def __init__(self, stdout: str = "", returncode: int = 0, stderr: str = "") -> None:
        self.calls: list[tuple[list[str], dict[str, Any]]] = []
        self.stdout = stdout
        self.returncode = returncode
        self.stderr = stderr
        self.raises: BaseException | None = None

    def __call__(self, argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        self.calls.append((argv, kwargs))
        if self.raises is not None:
            raise self.raises
        return subprocess.CompletedProcess(argv, self.returncode, self.stdout, self.stderr)


class TestGenerate:
    def test_runs_ssh_keygen_with_no_secret_on_argv(self) -> None:
        seen: dict[str, Any] = {}

        def run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            key = Path(argv[argv.index("-f") + 1])
            seen["argv"] = argv
            seen["dir_mode"] = stat.S_IMODE(key.parent.stat().st_mode)
            key.write_text(SENTINEL_PRIVATE, encoding="utf-8")
            (key.parent / "key.pub").write_text(PUBLIC + " vm-01\n", encoding="utf-8")
            seen["dir"] = key.parent
            return subprocess.CompletedProcess(argv, 0, "", "")

        private, public = generate_keypair("vm-01", run)

        assert private == SENTINEL_PRIVATE
        assert public == PUBLIC
        argv = seen["argv"]
        assert argv[:2] == ["ssh-keygen", "-q"]
        assert argv[argv.index("-t") : argv.index("-t") + 2] == ["-t", "ed25519"]
        assert "SENTINEL" not in " ".join(argv)
        assert seen["dir_mode"] == 0o700
        assert not seen["dir"].exists()

    def test_failure_has_no_key_material(self) -> None:
        with pytest.raises(SecretError, match="exit 1"):
            generate_keypair("vm-01", FakeRun(returncode=1, stderr="boom"))

    def test_missing_output_files(self) -> None:
        with pytest.raises(SecretError, match="no key pair"):
            generate_keypair("vm-01", FakeRun())


class TestScan:
    LINE = f"192.0.2.10 {PUBLIC}\n"

    def test_local(self) -> None:
        run = FakeRun(stdout="# 192.0.2.10:22 SSH-2.0-OpenSSH\n" + self.LINE)
        assert scan_public_key("192.0.2.10", None, run) == PUBLIC
        argv, _ = run.calls[0]
        assert argv == ["ssh-keyscan", "-T", "10", "-t", "ed25519", "192.0.2.10"]

    def test_via_jumphost_is_strict_and_quotes_the_address(self) -> None:
        run = FakeRun(stdout=self.LINE)
        assert scan_public_key("host name;id", "ansible@jump.example", run) == PUBLIC
        argv, _ = run.calls[0]
        assert argv[0] == "ssh"
        assert "StrictHostKeyChecking=yes" in argv
        assert "BatchMode=yes" in argv
        assert "UserKnownHostsFile=/dev/null" not in " ".join(argv)
        assert argv[-2] == "ansible@jump.example"
        assert argv[-1].endswith("'host name;id'")

    def test_refuses_a_jumphost_that_looks_like_an_option(self) -> None:
        with pytest.raises(SecretError, match="invalid jumphost"):
            scan_public_key("192.0.2.10", "-oProxyCommand=x", FakeRun(stdout=self.LINE))

    @pytest.mark.parametrize(
        "stdout",
        [
            "",
            "# only a comment\n",
            f"192.0.2.10 {PUBLIC}\n" * 2,
            "192.0.2.10 ssh-rsa AAAA\n",
            "garbage\n",
        ],
    )
    def test_rejects_zero_many_or_malformed(self, stdout: str) -> None:
        with pytest.raises(SecretError):
            scan_public_key("192.0.2.10", None, FakeRun(stdout=stdout))

    def test_timeout(self) -> None:
        run = FakeRun()
        run.raises = subprocess.TimeoutExpired(["ssh-keyscan"], 60)
        with pytest.raises(SecretError, match="timed out"):
            scan_public_key("192.0.2.10", None, run)

    def test_failure(self) -> None:
        with pytest.raises(SecretError, match=r"exit 255\): refused"):
            scan_public_key("192.0.2.10", "j", FakeRun(returncode=255, stderr="refused\n"))

    def test_missing_program(self) -> None:
        run = FakeRun()
        run.raises = FileNotFoundError(2, "No such file or directory")
        with pytest.raises(SecretError, match="could not run"):
            scan_public_key("192.0.2.10", None, run)


class TestFingerprint:
    def test_reads_the_second_field(self) -> None:
        run = FakeRun(stdout="256 SHA256:abc vm-01 (ED25519)\n")
        assert fingerprint(PUBLIC, run) == "SHA256:abc"
        argv, kwargs = run.calls[0]
        assert argv == ["ssh-keygen", "-lf", "-"]
        assert kwargs["input"] == PUBLIC + "\n"

    def test_empty_output(self) -> None:
        with pytest.raises(SecretError):
            fingerprint(PUBLIC, FakeRun(stdout=""))


class TestSopsFile:
    def test_ensure_runs_only_when_missing(self, tmp_path: Path) -> None:
        path = tmp_path / "pkg" / "secrets.yaml"
        run = FakeRun(stdout="encrypted: true\n")

        assert ensure_secrets_file(path, tmp_path, run) is True
        assert path.read_text() == "encrypted: true\n"
        argv, kwargs = run.calls[0]
        assert argv[:4] == ["sops", "--encrypt", "--filename-override", str(path)]
        assert kwargs["input"] == "variables: {}\n"
        assert kwargs["cwd"] == str(tmp_path)

        assert ensure_secrets_file(path, tmp_path, run) is False
        assert len(run.calls) == 1

    def test_write_entry_uses_stdin_for_the_value(self, tmp_path: Path) -> None:
        path = tmp_path / "secrets.yaml"
        run = FakeRun()
        entry = {"ed25519_private": SENTINEL_PRIVATE, "ed25519_public": PUBLIC}

        write_entry(path, "vm-01", entry, run)

        argv, kwargs = run.calls[0]
        assert argv == [
            "sops",
            "set",
            "--value-stdin",
            str(path),
            '["variables"]["ssh_host_keys"]["vm-01"]',
        ]
        assert "SENTINEL" not in " ".join(argv)
        assert json.loads(kwargs["input"]) == entry

    @pytest.mark.parametrize("name", ['a"]["b', "a b", "", "a.b"])
    def test_write_entry_rejects_names_that_could_alter_the_path(
        self, tmp_path: Path, name: str
    ) -> None:
        run = FakeRun()
        with pytest.raises(SecretError):
            write_entry(tmp_path / "s.yaml", name, {}, run)
        assert not run.calls

    def test_sops_failure_has_no_value(self, tmp_path: Path) -> None:
        run = FakeRun(returncode=128, stderr="no matching creation rules\n")
        with pytest.raises(SecretError) as err:
            write_entry(tmp_path / "s.yaml", "vm-01", {"ed25519_private": SENTINEL_PRIVATE}, run)
        assert "SENTINEL" not in str(err.value)


def _resource(name: str, secrets: dict[str, Any] | None = None) -> ResourceConfig:
    return ResourceConfig(
        name=name,
        type="vm",
        provider="proxmox",
        config={"ssh_host_key": {"address": "192.0.2.10"}},
        package_name="demo",
        package_path="proxmox/demo",
        package_secrets=secrets,
    )


def _recorded(name: str) -> dict[str, Any]:
    return {"ssh_host_keys": {name: {"ed25519_public": PUBLIC}}}


class TestPlan:
    @pytest.mark.parametrize(
        ("recorded", "state", "regenerate", "expected"),
        [
            (False, False, (), HostKeyAction.GENERATE),
            (False, True, (), HostKeyAction.PIN),
            (False, None, (), HostKeyAction.REFUSE),
            (True, False, (), HostKeyAction.SKIP),
            (True, True, (), HostKeyAction.SKIP),
            (True, None, (), HostKeyAction.SKIP),
            (True, False, ("vm",), HostKeyAction.GENERATE),
            (True, True, ("vm",), HostKeyAction.REFUSE),
            (True, None, ("vm",), HostKeyAction.REFUSE),
            (False, False, ("vm",), HostKeyAction.GENERATE),
            (False, True, ("vm",), HostKeyAction.PIN),
        ],
    )
    def test_matrix(
        self,
        recorded: bool,
        state: bool | None,
        regenerate: tuple[str, ...],
        expected: HostKeyAction,
    ) -> None:
        resource = _resource("vm", _recorded("vm") if recorded else {})
        (planned,) = plan_actions([resource], lambda _r: state, regenerate)
        assert planned.action is expected
        assert planned.resource is resource

    def test_refusals_explain_themselves(self) -> None:
        resource = _resource("vm", _recorded("vm"))
        (planned,) = plan_actions([resource], lambda _r: True, ["vm"])
        assert "deployed" in planned.reason
