"""Tests for blueprints/aiqum/scripts/aiqum-cert-export.py (#1648).

A local TLS server with a throwaway self-signed certificate stands in for AIQUM. The
helper is stdlib only and runs on the VM's Python 3.9, so it is loaded by path.
"""

from __future__ import annotations

import ast
import importlib.util
import os
import shutil
import socket
import ssl
import subprocess
import sys
import threading
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "blueprints" / "aiqum" / "scripts" / "aiqum-cert-export.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("aiqum_cert_export", SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["aiqum_cert_export"] = mod
    spec.loader.exec_module(mod)
    return mod


ce: Any = _load()


def _gen_cert(directory: Path, name: str) -> tuple[Path, Path]:
    cert, key = directory / f"{name}.pem", directory / f"{name}.key"
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "1",
            "-subj",
            f"/CN={name}.example",
            "-keyout",
            str(key),
            "-out",
            str(cert),
        ],
        check=True,
        capture_output=True,
    )
    return cert, key


@pytest.fixture
def certs(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Two generated certificates: ``(served cert, its key, another cert)``."""
    if shutil.which("openssl") is None:
        pytest.skip("openssl CLI not available to generate test certificates")
    cert, key = _gen_cert(tmp_path, "aiqum")
    other, _ = _gen_cert(tmp_path, "other")
    return cert, key, other


@pytest.fixture
def tls_server(certs: tuple[Path, Path, Path]) -> Iterator[int]:
    """A local TLS server presenting the first certificate; yields its port."""
    cert, key, _ = certs
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(str(cert), str(key))
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(5)
    stop = threading.Event()

    def serve() -> None:
        while not stop.is_set():
            try:
                conn, _addr = listener.accept()
            except OSError:
                return
            try:
                with ctx.wrap_socket(conn, server_side=True):
                    pass
            except (OSError, ssl.SSLError):
                pass

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    yield int(listener.getsockname()[1])
    stop.set()
    listener.close()


def _der(cert: Path) -> bytes:
    return ssl.PEM_cert_to_DER_cert(cert.read_text(encoding="ascii"))


def test_client_context_refuses_protocols_older_than_tls12() -> None:
    ctx = ce.client_context()
    assert ctx.minimum_version == ssl.TLSVersion.TLSv1_2
    assert ctx.verify_mode == ssl.CERT_NONE
    assert ctx.check_hostname is False


def test_fetch_der_returns_the_served_certificate(
    certs: tuple[Path, Path, Path], tls_server: int
) -> None:
    assert ce.fetch_der("127.0.0.1", tls_server) == _der(certs[0])


def test_served_cert_output_round_trips(
    certs: tuple[Path, Path, Path], tls_server: int, capsys: pytest.CaptureFixture[str]
) -> None:
    assert ce.main(["served-cert", "127.0.0.1", str(tls_server)]) == 0

    printed = capsys.readouterr().out
    assert ce.parse_pem(printed) == _der(certs[0])


def test_export_writes_the_pem_when_copies_match(
    certs: tuple[Path, Path, Path], tls_server: int, tmp_path: Path
) -> None:
    pem_file = tmp_path / "served.pem"
    pem_file.write_text(certs[0].read_text())
    out = tmp_path / "nested" / "dir" / "aiqum-https.pem"

    code = ce.main(
        [
            *["export", "--pem-file", str(pem_file), "--host", "127.0.0.1"],
            *["--port", str(tls_server), "--out", str(out)],
        ]
    )

    assert code == 0
    text = out.read_text()
    assert text.endswith("-----END CERTIFICATE-----\n")
    assert ce.parse_pem(text) == _der(certs[0])
    assert (out.stat().st_mode & 0o777) == 0o644
    assert [p.name for p in out.parent.iterdir()] == ["aiqum-https.pem"]


def test_export_mismatch_exits_1_names_both_fingerprints_and_keeps_out(
    certs: tuple[Path, Path, Path],
    tls_server: int,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    pem_file = tmp_path / "served.pem"
    pem_file.write_text(certs[2].read_text())
    out = tmp_path / "aiqum-https.pem"
    argv = ["export", "--pem-file", str(pem_file), "--host", "127.0.0.1"]
    argv += ["--port", str(tls_server), "--out", str(out)]

    assert ce.main(argv) == 1
    err = capsys.readouterr().err
    assert ce.fingerprint(_der(certs[0])) in err
    assert ce.fingerprint(_der(certs[2])) in err
    assert "differs" in err
    assert not out.exists()

    out.write_text("previous\n")
    assert ce.main(argv) == 1
    assert out.read_text() == "previous\n"


def test_parse_pem_accepts_one_certificate(certs: tuple[Path, Path, Path]) -> None:
    assert ce.parse_pem(certs[0].read_text()) == _der(certs[0])


@pytest.mark.parametrize("text", ["", "not a certificate", "-----BEGIN CERTIFICATE-----\nxx\n"])
def test_parse_pem_rejects_bad_input(text: str) -> None:
    with pytest.raises(ce.ExportError):
        ce.parse_pem(text)


def test_parse_pem_rejects_two_certificates(certs: tuple[Path, Path, Path]) -> None:
    with pytest.raises(ce.ExportError, match="exactly one"):
        ce.parse_pem(certs[0].read_text() + certs[2].read_text())


@pytest.mark.parametrize("value", ["", "   ", "relative.pem", "./x.pem"])
def test_resolve_out_rejects_empty_and_relative(value: str) -> None:
    with pytest.raises(ce.ExportError):
        ce.resolve_out(value)


def test_resolve_out_expands_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    assert ce.resolve_out("~/aiqum.pem") == tmp_path / "aiqum.pem"
    assert ce.resolve_out("/srv/config/aiqum.pem") == Path("/srv/config/aiqum.pem")


def test_write_failure_leaves_the_target_and_removes_the_temp_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = tmp_path / "aiqum.pem"
    out.write_text("previous\n")

    def boom(*_args: Any, **_kwargs: Any) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", boom)

    with pytest.raises(OSError, match="disk full"):
        ce.write_atomic(out, "new")

    assert out.read_text() == "previous\n"
    assert [p.name for p in tmp_path.iterdir()] == ["aiqum.pem"]


def test_fingerprint_format() -> None:
    value = ce.fingerprint(b"abc")
    parts = value.split(":")
    assert len(parts) == 32
    assert all(len(p) == 2 and p == p.upper() for p in parts)


def test_main_unreachable_port_returns_1(capsys: pytest.CaptureFixture[str]) -> None:
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()

    assert ce.main(["served-cert", "127.0.0.1", str(port)]) == 1

    err = capsys.readouterr().err
    assert err.startswith("ERROR: cannot fetch the certificate from 127.0.0.1")


def test_main_missing_pem_file_returns_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    argv = ["export", "--pem-file", str(tmp_path / "missing.pem"), "--host", "127.0.0.1"]
    argv += ["--out", str(tmp_path / "out.pem")]

    assert ce.main(argv) == 1
    assert "ERROR:" in capsys.readouterr().err


def test_helper_runs_from_stdin_like_on_the_vm(
    certs: tuple[Path, Path, Path], tls_server: int
) -> None:
    """``python3 - served-cert HOST PORT`` with the file on stdin, as Phase 4b pipes it."""
    result = subprocess.run(
        [sys.executable, "-", "served-cert", "127.0.0.1", str(tls_server)],
        input=SCRIPT.read_text(),
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )

    assert result.returncode == 0, result.stderr
    assert ce.parse_pem(result.stdout) == _der(certs[0])


def test_helper_is_python39_compatible() -> None:
    """The VM runs Python 3.9: no ``match``, no 3.10-only calls, annotations deferred."""
    text = SCRIPT.read_text()
    assert "from __future__ import annotations" in text
    assert "get_server_certificate" not in text
    tree = ast.parse(text, feature_version=(3, 9))
    assert not [n for n in ast.walk(tree) if isinstance(n, ast.Match)]
