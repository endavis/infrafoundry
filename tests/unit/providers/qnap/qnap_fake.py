"""A fake QNAP switch web API on 127.0.0.1 (a helper, not a test module).

The server speaks TLS 1.2+ with a throw-away certificate made by the ``openssl`` CLI. It
expects the base64 form of an ASCII password written out as a literal, so it does not use
the code under test to decide whether a login is right. Values are documentation values.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import ssl
import subprocess
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

USER = "admin-example"
PASSWORD = "Passw0rd-example"  # not a real credential
PASSWORD_B64 = "UGFzc3cwcmQtZXhhbXBsZQ=="  # base64 of PASSWORD, written out independently
TOKEN = "token-fake-0123456789"
RENEWED_TOKEN = "token-renewed-9876543210"


def _ok(result: Any) -> dict[str, Any]:
    return {"error_code": 200, "error_message": "OK", "result": result}


@dataclass
class FakeQnapState:
    """What the fake serves and what it saw."""

    results: dict[str, Any] = field(
        default_factory=lambda: {
            "about": {"Hostname": "sw-example", "Model": "QSW-M-example", "Product": "QSW-M"},
            "live": None,
            "firmware/info": {"version": "2.5.0", "buildNumber": "20250101"},
            "firmware/status": {"progress": "none"},
            "firmware/condition": {"anomaly": False, "message": ""},
            "firmware/update/check": {"newer": True, "version": "2.6.0", "buildNumber": "1"},
            "firmware/update/live": {},
            "dns/server": [{"key": "1", "val": {"IpAddress": "192.0.2.53", "State": "up"}}],
            "system/info": {"hostname": "sw-example", "mac": "02:00:00:00:00:01"},
        }
    )
    raw: dict[str, bytes] = field(default_factory=dict)
    """Raw reply bodies by path (override ``results``)."""
    envelopes: dict[str, dict[str, Any]] = field(default_factory=dict)
    """Complete envelopes by path (override ``results``)."""
    delays: dict[str, float] = field(default_factory=dict)
    requests: list[tuple[str, str, str | None, Any]] = field(default_factory=list)
    """``(method, path, Authorization header, decoded body)`` per request."""
    logins: int = 0
    logouts: int = 0

    def paths(self) -> list[str]:
        """Return the request paths in order."""
        return [path for _, path, _, _ in self.requests]


class _Handler(BaseHTTPRequestHandler):
    state: FakeQnapState

    def _send(self, body: bytes, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle(self, method: str) -> None:
        state = self.state
        length = int(self.headers.get("Content-Length", "0"))
        text = self.rfile.read(length) if length else b""
        body = json.loads(text) if text else None
        path = self.path
        state.requests.append((method, path, self.headers.get("Authorization"), body))
        key = path.removeprefix("/api/v1/").removeprefix("/api/")
        if key in state.delays:
            time.sleep(state.delays[key])
        if key in state.raw:
            self._send(state.raw[key])
            return
        if key in state.envelopes:
            self._send(json.dumps(state.envelopes[key]).encode())
            return
        if path == "/api/v1/users/login" and method == "POST":
            state.logins += 1
            if body and body.get("username") == USER and body.get("password") == PASSWORD_B64:
                self._send(json.dumps(_ok(TOKEN)).encode())
            else:
                refused = {"error_code": 400, "error_message": "Invalid", "result": None}
                self._send(json.dumps(refused).encode())
            return
        if path == "/api/v1/users/login" and method == "GET":
            if self.headers.get("Authorization") == f"Bearer {TOKEN}":
                self._send(json.dumps(_ok(RENEWED_TOKEN)).encode())
            else:
                self._send(b"{}", status=401)
            return
        if path == "/api/v1/users/exit":
            state.logouts += 1
            self._send(json.dumps(_ok(None)).encode())
            return
        if key in state.results:
            authed = key in ("about", "live") or self.headers.get("Authorization") in (
                f"Bearer {TOKEN}",
                f"Bearer {RENEWED_TOKEN}",
            )
            if not authed:
                unauthorized = {"error_code": 401, "error_message": "x", "result": None}
                self._send(json.dumps(unauthorized).encode(), status=401)
                return
            self._send(json.dumps(_ok(state.results[key])).encode())
            return
        self._send(json.dumps({"error_code": 404, "error_message": "x", "result": None}).encode())

    def do_GET(self) -> None:
        self._handle("GET")

    def do_POST(self) -> None:
        self._handle("POST")

    def log_message(self, format: str, *args: Any) -> None:
        return


class _QuietServer(ThreadingHTTPServer):
    """Mismatched-pin clients drop the connection mid-handshake; keep that out of the output."""

    def handle_error(self, request: Any, client_address: Any) -> None:
        return


def _cert(directory: Path, name: str) -> tuple[Path, Path]:
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
            "-addext",
            "subjectAltName=IP:127.0.0.1",
            "-keyout",
            str(key),
            "-out",
            str(cert),
        ],
        check=True,
        capture_output=True,
    )
    return cert, key


def fingerprint_of(cert: Path) -> str:
    """Return the SHA-256 of a PEM certificate's DER form, as 64 lowercase hex characters."""
    der = ssl.PEM_cert_to_DER_cert(cert.read_text(encoding="ascii"))
    return hashlib.sha256(der).hexdigest()


@dataclass
class ServedQnap:
    """A running fake switch."""

    port: int
    fingerprint: str
    other_fingerprint: str
    state: FakeQnapState
    server: ThreadingHTTPServer

    @property
    def api_url(self) -> str:
        """Base URL of the fake."""
        return f"https://127.0.0.1:{self.port}"

    def stop(self) -> None:
        """Stop serving (later connections are refused)."""
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def served_qnap(tmp_path: Path) -> Iterator[ServedQnap]:
    """A local TLS 1.2+ fake switch: port, its pin, another certificate's pin, its state."""
    if shutil.which("openssl") is None:
        pytest.skip("openssl CLI not available")
    cert, key = _cert(tmp_path, "switch")
    other, _ = _cert(tmp_path, "other")
    state = FakeQnapState()
    handler = type("Handler", (_Handler,), {"state": state})
    server = _QuietServer(("127.0.0.1", 0), handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(str(cert), str(key))
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    served = ServedQnap(
        int(server.server_address[1]), fingerprint_of(cert), fingerprint_of(other), state, server
    )
    yield served
    try:
        server.shutdown()
        server.server_close()
    except OSError:  # pragma: no cover  # already stopped by the test
        pass
