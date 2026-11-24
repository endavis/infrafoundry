"""A fake GL.iNet web API on 127.0.0.1 for the #1655 tests (a helper, not a test module).

The server speaks TLS 1.2+ with a throw-away certificate made by the ``openssl`` CLI. It
expects the login hash of a *published* crypt vector, written out as literals here, so
it does not use the code under test to decide whether a login is right.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import ssl
import subprocess
import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

USER = "root"
PASSWORD = "Hello world!"  # a published test vector, not a real credential
ALG = "5"
SALT = "saltstring"
CIPHER = "$5$saltstring$5B8vYYiY.CVt1RlTTf8KbXBH3hsxY/GNooZaBBGWEc5"
NONCE = "nonce-0123456789"
SID = "sid-fake-0123456789"


def expected_hash(method: str = "sha256") -> str:
    """Return the login hash the fake accepts (independent of the crypt module)."""
    text = f"{USER}:{CIPHER}:{NONCE}".encode()
    return hashlib.new(method, text, usedforsecurity=False).hexdigest()


@dataclass
class FakeGlinetState:
    """What the fake serves and what it saw."""

    alg: str = ALG
    hash_method: str | None = None
    check_replies: list[Any] = field(
        default_factory=lambda: [{"current_version": "4.8.7", "current_type": "release"}]
    )
    upgrade_reply: Any = field(default_factory=dict)
    status_replies: list[Any] = field(default_factory=list)
    down: bool = False
    requests: int = 0
    logins: int = 0
    logouts: int = 0
    calls: list[tuple[str, str, dict[str, Any]]] = field(default_factory=list)
    login_bodies: list[str] = field(default_factory=list)

    def next_check(self) -> Any:
        """Pop the next scripted ``check_firmware_online`` reply (the last one repeats)."""
        return self.check_replies.pop(0) if len(self.check_replies) > 1 else self.check_replies[0]


class _Handler(BaseHTTPRequestHandler):
    state: FakeGlinetState

    def _reply(self, payload: Any, raw: bytes | None = None) -> None:
        body = raw if raw is not None else json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        state = self.state
        state.requests += 1
        length = int(self.headers.get("Content-Length", "0"))
        request = json.loads(self.rfile.read(length))
        if state.down:
            self.close_connection = True
            return
        ident, method, params = request["id"], request["method"], request.get("params")
        if method == "challenge":
            result: dict[str, Any] = {"alg": state.alg, "salt": SALT, "nonce": NONCE}
            if state.hash_method:
                result["hash-method"] = state.hash_method
            self._reply({"jsonrpc": "2.0", "id": ident, "result": result})
        elif method == "login":
            state.logins += 1
            state.login_bodies.append(json.dumps(params))
            good = expected_hash(state.hash_method or "sha256")
            if params.get("username") == USER and params.get("hash") == good:
                self._reply({"jsonrpc": "2.0", "id": ident, "result": {"sid": SID}})
            else:
                error = {"code": -32000, "message": "Access denied"}
                self._reply({"jsonrpc": "2.0", "id": ident, "error": error})
        elif method == "logout":
            state.logouts += 1
            self._reply({"jsonrpc": "2.0", "id": ident, "result": {}})
        elif method == "call":
            self._call(ident, params)
        elif method == "garbage":
            self._reply(None, raw=b"<html>not json</html>")
        else:
            self._reply({"jsonrpc": "2.0", "id": ident, "error": {"code": -32601}})

    def _call(self, ident: int, params: list[Any]) -> None:
        state = self.state
        sid, module, method, args = params
        if sid != SID:
            self._reply({"jsonrpc": "2.0", "id": ident, "error": {"code": -32000}})
            return
        state.calls.append((module, method, args))
        if method == "check_firmware_online":
            result: Any = state.next_check()
        elif method == "upgrade_online":
            result = state.upgrade_reply
        elif method == "get_online_upgrade_status":
            result = state.status_replies.pop(0) if state.status_replies else []
        elif method == "boom":
            self._reply({"jsonrpc": "2.0", "id": ident, "error": {"code": -1, "message": "bad"}})
            return
        else:
            result = {}
        self._reply({"jsonrpc": "2.0", "id": ident, "result": result})

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
class ServedGlinet:
    """A running fake router."""

    port: int
    fingerprint: str
    other_fingerprint: str
    state: FakeGlinetState


@pytest.fixture
def served_glinet(tmp_path: Path) -> Iterator[ServedGlinet]:
    """A local TLS 1.2+ fake router: port, its pin, another certificate's pin, its state."""
    if shutil.which("openssl") is None:
        pytest.skip("openssl CLI not available")
    cert, key = _cert(tmp_path, "router")
    other, _ = _cert(tmp_path, "other")
    state = FakeGlinetState()
    handler = type("Handler", (_Handler,), {"state": state})
    server = _QuietServer(("127.0.0.1", 0), handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(str(cert), str(key))
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield ServedGlinet(
        int(server.server_address[1]), fingerprint_of(cert), fingerprint_of(other), state
    )
    server.shutdown()
    server.server_close()
