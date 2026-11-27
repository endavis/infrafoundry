"""The SSH installer for VM and instance targets: pinned keys, the jump hop, secrecy (#1682)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from infrafoundry.core.certs.install import CertificateTarget, resolve_target
from infrafoundry.core.certs.models import CertificateInstallError
from infrafoundry.core.certs.ssh_installer import RELOAD_FAILED, SshCertificateInstaller

from .fakes import PUBLIC, FakeRun, vm_resource, vm_target

pytestmark = pytest.mark.unit

CERT = "-----BEGIN CERTIFICATE-----\nLEAF\n-----END CERTIFICATE-----\n"
CHAIN = "-----BEGIN CERTIFICATE-----\nCHAIN\n-----END CERTIFICATE-----\n"
KEY = "-----BEGIN " + "PRIVATE KEY-----\nSENTINEL-NOT-A-REAL-KEY\n-----END " + "PRIVATE KEY-----\n"


def vm_target_for(**over: object) -> CertificateTarget:
    resource = vm_resource(**over)  # type: ignore[arg-type]
    return resolve_target(vm_target(resource), ["example.com"], [resource])


def _known_hosts_path(argv: list[str]) -> Path:
    option = next(a for a in argv if a.startswith("UserKnownHostsFile="))
    return Path(option.split("=", 1)[1])


def test_a_direct_pinned_install_uses_a_private_known_hosts_file_and_removes_it() -> None:
    seen: list[tuple[Path, int, str]] = []
    run = FakeRun()

    def spy(argv: list[str], **kwargs: Any) -> Any:
        path = _known_hosts_path(argv)
        seen.append((path, path.stat().st_mode & 0o777, path.read_text(encoding="utf-8")))
        return run(argv, **kwargs)

    SshCertificateInstaller(spy).install(vm_target_for(jumphost=None), CERT, CHAIN, KEY)
    path, mode, content = seen[0]
    assert mode == 0o600
    assert content == f"app-01,192.0.2.20 {PUBLIC}\n"
    assert not path.exists()
    argv = run.calls[0][0]
    for option in (
        "StrictHostKeyChecking=yes",
        "GlobalKnownHostsFile=/dev/null",
        "HostKeyAlias=app-01",
    ):
        assert option in argv
    assert "-i" not in argv
    assert "deploy@192.0.2.20" in argv


def test_the_known_hosts_file_is_removed_after_a_failure() -> None:
    paths: list[Path] = []
    run = FakeRun(returncode=255)

    def spy(argv: list[str], **kwargs: Any) -> Any:
        paths.append(_known_hosts_path(argv))
        return run(argv, **kwargs)

    with pytest.raises(CertificateInstallError):
        SshCertificateInstaller(spy).install(vm_target_for(jumphost=None), CERT, CHAIN, KEY)
    assert paths
    assert not any(p.exists() for p in paths)


def test_a_jump_install_checks_both_hops_strictly() -> None:
    run = FakeRun()
    SshCertificateInstaller(run).install(vm_target_for(), CERT, CHAIN, KEY)
    argv, kwargs = run.calls[0]
    assert argv[-2] == "jump.example.com"
    assert "-i" not in argv
    assert "StrictHostKeyChecking=yes" in argv
    script = argv[-1]
    assert "kh=$(mktemp)" in script
    assert "trap 'rm -f \"$kh\"' EXIT" in script
    assert 'UserKnownHostsFile="$kh"' in script
    assert "StrictHostKeyChecking=yes" in script
    assert "HostKeyAlias=app-01" in script
    assert "deploy@192.0.2.20" in script
    assert PUBLIC in script
    assert kwargs["input"] == CERT + CHAIN


def test_no_argv_ever_weakens_host_key_checking_or_carries_secrets() -> None:
    for over in ({}, {"jumphost": None}):
        run = FakeRun()
        SshCertificateInstaller(run).install(vm_target_for(**over), CERT, CHAIN, KEY)
        for argv, _ in run.calls:
            joined = " ".join(argv)
            for bad in ("StrictHostKeyChecking=no", "accept-new", "SENTINEL", "PRIVATE", "LEAF"):
                assert bad not in joined


def test_a_reload_failure_through_the_jump_hop_is_restored() -> None:
    run = FakeRun()
    run.responses = [(0, ""), (0, ""), (RELOAD_FAILED, "")]
    with pytest.raises(CertificateInstallError, match="previous certificate was restored"):
        SshCertificateInstaller(run).install(vm_target_for(), CERT, CHAIN, KEY)


def test_a_pinned_key_mismatch_names_host_keys() -> None:
    stderr = "Host key for app-01 has changed and you have requested strict checking."
    with pytest.raises(CertificateInstallError, match="secrets host-keys"):
        SshCertificateInstaller(FakeRun(returncode=255, stderr=stderr)).install(
            vm_target_for(jumphost=None), CERT, CHAIN, KEY
        )


def test_a_jump_hop_host_key_failure_keeps_the_known_hosts_hint() -> None:
    stderr = "Host key verification failed."
    with pytest.raises(CertificateInstallError, match=r"jump\.example\.com") as info:
        SshCertificateInstaller(FakeRun(returncode=255, stderr=stderr)).install(
            vm_target_for(), CERT, CHAIN, KEY
        )
    assert "known_hosts" in str(info.value)
