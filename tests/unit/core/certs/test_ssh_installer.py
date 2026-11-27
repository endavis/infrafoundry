"""The SSH installer: argv, stdin, the remote script, rollback and secrecy."""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

import pytest

from infrafoundry.core.certs.install import CertificateTarget, resolve_target
from infrafoundry.core.certs.models import CertificateInstallError
from infrafoundry.core.certs.ssh_installer import (
    NEW_SUFFIX,
    RELOAD_FAILED,
    SshCertificateInstaller,
)

from .fakes import FakeRun, certificate_resource, host_resource

pytestmark = pytest.mark.unit

CERT = "-----BEGIN CERTIFICATE-----\nLEAF\n-----END CERTIFICATE-----\n"
CHAIN = "-----BEGIN CERTIFICATE-----\nCHAIN\n-----END CERTIFICATE-----\n"
KEY = "-----BEGIN " + "PRIVATE KEY-----\nSENTINEL-NOT-A-REAL-KEY\n-----END " + "PRIVATE KEY-----\n"


def target(**over: object) -> CertificateTarget:
    resource = certificate_resource()
    resource.config["target"].update(over)
    return resolve_target(
        resource.config["target"], ["example.com"], [host_resource(ssh_private_key_file="id_x")]
    )


def install(run: FakeRun, **over: object) -> None:
    SshCertificateInstaller(run).install(target(**over), CERT, CHAIN, KEY)


def test_files_are_written_over_stdin_then_moved_in_one_call() -> None:
    run = FakeRun()
    install(run)
    writes, final = run.calls[:2], run.calls[2]
    assert len(run.calls) == 3
    assert writes[0][1]["input"] == CERT + CHAIN
    assert writes[1][1]["input"] == KEY
    assert final[1]["input"] is None
    assert f"/etc/ssl/infrafoundry/proxy.key{NEW_SUFFIX}" in writes[1][0][-1]
    assert "umask 077" in writes[1][0][-1]


def test_ssh_is_strict_batch_and_never_prompts() -> None:
    run = FakeRun()
    install(run)
    argv = run.calls[0][0]
    assert argv[0] == "ssh"
    for option in ("BatchMode=yes", "StrictHostKeyChecking=yes", "ConnectTimeout=10"):
        assert option in argv
    assert argv[argv.index("-p") + 1] == "2222"
    assert argv[argv.index("-i") + 1] == "id_x"
    assert "deploy@192.0.2.10" in argv
    assert "StrictHostKeyChecking=no" not in argv


def test_no_key_material_is_ever_on_a_command_line() -> None:
    run = FakeRun()
    install(run)
    for argv, _ in run.calls:
        joined = " ".join(argv)
        assert "SENTINEL" not in joined
        assert "PRIVATE" not in joined
        assert "LEAF" not in joined


def test_the_final_script_backs_up_owns_moves_and_reloads() -> None:
    run = FakeRun()
    install(run, owner="caddy", group="caddy", key_mode="0640", sudo=True)
    final = run.calls[2][0][-1]
    assert final.startswith("sudo -n sh -c ")
    assert "chown caddy:caddy" in final
    assert "chmod 0640" in final
    assert (
        "cp -p /etc/ssl/infrafoundry/proxy.key /etc/ssl/infrafoundry/proxy.key.infrafoundry-bak"
        in final
    )
    assert (
        "mv -f /etc/ssl/infrafoundry/proxy.key.infrafoundry-new /etc/ssl/infrafoundry/proxy.key"
        in final
    )
    assert "if ! systemctl reload caddy; then" in final
    assert "rollback" in final


def test_the_reload_is_an_argv_never_a_shell_string() -> None:
    run = FakeRun()
    install(run, reload=["systemctl", "reload", "a b; touch /x"])
    script = shlex.split(run.calls[2][0][-1])[-1]
    assert "if ! systemctl reload 'a b; touch /x'; then" in script


def test_without_a_reload_command_there_is_no_reload_block() -> None:
    run = FakeRun()
    install(run, reload=[])
    assert "if !" not in run.calls[2][0][-1]


def test_a_reload_failure_reports_the_restore_and_removes_the_new_files() -> None:
    run = FakeRun()
    run.responses = [(0, ""), (0, ""), (RELOAD_FAILED, "infrafoundry-reload-failed\n"), (0, "")]
    with pytest.raises(CertificateInstallError, match="previous certificate was restored"):
        install(run)
    cleanup = run.calls[-1][0][-1]
    assert shlex.split(cleanup)[-1].startswith("rm -f ")
    assert NEW_SUFFIX in cleanup


def test_a_write_failure_stops_before_touching_the_live_files() -> None:
    run = FakeRun()
    run.responses = [(0, ""), (1, "Permission denied\n"), (0, "")]
    with pytest.raises(CertificateInstallError, match=r"writing /etc/ssl/infrafoundry/proxy\.key"):
        install(run)
    assert len(run.calls) == 3
    assert "mv -f" not in " ".join(c[0][-1] for c in run.calls)


def test_a_host_key_failure_explains_how_to_record_the_key() -> None:
    run = FakeRun(
        returncode=255,
        stderr="Host key verification failed.\n",
    )
    with pytest.raises(CertificateInstallError) as caught:
        install(run)
    assert "192.0.2.10" in str(caught.value)


def test_errors_never_carry_key_material() -> None:
    run = FakeRun(returncode=1, stderr=f"oops\n{KEY}")
    with pytest.raises(CertificateInstallError) as caught:
        install(run)
    assert "SENTINEL" not in str(caught.value)
    assert "PRIVATE" not in str(caught.value)


def test_a_timeout_and_a_missing_ssh_are_install_errors() -> None:
    run = FakeRun()
    run.raises = subprocess.TimeoutExpired("ssh", 90)
    with pytest.raises(CertificateInstallError, match="timed out"):
        install(run)
    run.raises = FileNotFoundError(2, "No such file or directory")
    with pytest.raises(CertificateInstallError, match="could not run ssh"):
        install(run)


def test_a_target_without_an_endpoint_is_refused() -> None:
    bare = CertificateTarget(provider="host", resource="x", key_path="/k", cert_path="/c")
    with pytest.raises(CertificateInstallError, match="no SSH endpoint"):
        SshCertificateInstaller(FakeRun()).install(bare, CERT, CHAIN, KEY)


def test_both_cert_and_fullchain_paths_are_written() -> None:
    run = FakeRun()
    install(run, cert_path="/etc/ssl/infrafoundry/proxy.crt")
    assert [c[1]["input"] for c in run.calls[:3]] == [CERT, CERT + CHAIN, KEY]


def _run_script(tmp_path: Path, reload: tuple[str, ...]) -> tuple[int, str, Path, Path]:
    """Run the real remote script locally with files under ``tmp_path`` (no ssh, no sudo)."""
    import getpass
    import grp
    import os

    from infrafoundry.core.certs.ssh_installer import _files, _finalize_script

    cert, key = tmp_path / "live.crt", tmp_path / "live.key"
    cert.write_text("OLD-CERT")
    key.write_text("OLD-KEY")
    target = CertificateTarget(
        provider="host",
        resource="proxy-01",
        key_path=str(key),
        cert_path=str(cert),
        owner=getpass.getuser(),
        group=grp.getgrgid(os.getgid()).gr_name,
        cert_mode="0644",
        key_mode="0600",
        reload=reload,
    )
    files = _files(target, "NEW-CERT", "", "NEW-KEY")
    for path, content, _ in files:
        Path(path + NEW_SUFFIX).write_text(content, encoding="utf-8")
    result = subprocess.run(
        ["sh", "-c", _finalize_script(target, files)], capture_output=True, text=True, check=False
    )
    return result.returncode, result.stderr, cert, key


def test_the_remote_script_installs_and_cleans_up(tmp_path: Path) -> None:
    code, _, cert, key = _run_script(tmp_path, ("true",))
    assert code == 0
    assert (cert.read_text(), key.read_text()) == ("NEW-CERT", "NEW-KEY")
    assert oct(key.stat().st_mode & 0o777) == "0o600"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["live.crt", "live.key"]


def test_the_remote_script_restores_the_old_files_when_the_reload_fails(tmp_path: Path) -> None:
    code, stderr, cert, key = _run_script(tmp_path, ("false",))
    assert code == RELOAD_FAILED
    assert "infrafoundry-reload-failed" in stderr
    assert (cert.read_text(), key.read_text()) == ("OLD-CERT", "OLD-KEY")
    assert sorted(p.name for p in tmp_path.iterdir()) == ["live.crt", "live.key"]


def test_the_remote_script_removes_files_that_did_not_exist_before(tmp_path: Path) -> None:
    from infrafoundry.core.certs.ssh_installer import _files, _finalize_script

    key = tmp_path / "fresh.key"
    target = CertificateTarget(
        provider="host", resource="x", key_path=str(key), reload=("false",), key_mode="0600"
    )
    files = _files(target, "C", "", "NEW-KEY")
    Path(str(key) + NEW_SUFFIX).write_text("NEW-KEY", encoding="utf-8")
    import getpass

    target = CertificateTarget(**{**target.__dict__, "owner": getpass.getuser(), "group": _group()})
    result = subprocess.run(
        ["sh", "-c", _finalize_script(target, files)], capture_output=True, text=True, check=False
    )
    assert result.returncode == RELOAD_FAILED
    assert list(tmp_path.iterdir()) == []


def _group() -> str:
    import grp
    import os

    return grp.getgrgid(os.getgid()).gr_name
