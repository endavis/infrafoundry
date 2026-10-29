"""Tests for blueprints/console-connector/scripts/console-connector-register.py (#1140).

No real network: HTTP calls go to an in-process fake server through patched
module constants.
"""

import importlib.util
import json
import os
import shutil
import ssl
import subprocess
import sys
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "blueprints"
    / "console-connector"
    / "scripts"
    / "console-connector-register.py"
)
SECRET = "s3cr3t-value"
TOKEN = "tok-abc-123"
PIN = "-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----\n"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("console_connector_register", SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["console_connector_register"] = mod
    spec.loader.exec_module(mod)
    return mod


reg: Any = _load()

FULL_VARS: dict[str, Any] = {
    "ip_address": "10.0.0.5",
    "vm_name": "agent1",
    "console_client_id": "cid",
    "console_client_secret": SECRET,
    "console_admin_email": "a@example.com",
}


class FakeConsole:
    """Records requests and serves canned responses."""

    def __init__(self) -> None:
        self.is_setup = False
        self.account = ""
        self.accounts: list[dict[str, str]] = [{"accountPublicId": "acc-1", "accountName": "One"}]
        self.init_status = 200
        self.requests: list[tuple[str, str, str, dict[str, Any]]] = []


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeConsole]:
    state = FakeConsole()

    class Handler(BaseHTTPRequestHandler):
        def _reply(self, status: int, payload: Any) -> None:
            data = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _handle(self, method: str) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length) or b"{}")
            auth = self.headers.get("Authorization", "")
            state.requests.append((method, self.path, auth, body))
            if self.path == "/oauth/token":
                self._reply(200, {"access_token": TOKEN})
            elif self.path == "/tenancy/account":
                self._reply(200, state.accounts)
            elif self.path == "/occm/api/occm/system/support-services":
                self._reply(
                    200,
                    {
                        "setupInfo": {"isSetup": state.is_setup},
                        "tenancyServiceInformation": {"accountId": state.account},
                    },
                )
            elif self.path == "/occm/api/occm/setup-portal/init":
                if state.init_status != 200:
                    self._reply(
                        state.init_status,
                        {
                            "error": "Bad Request",
                            "message": "User is not associated as admin to the tenancy "
                            "account acc-1",
                        },
                    )
                    return
                state.is_setup = True
                state.account = body["tenancyAccountId"]
                self._reply(200, {})
            else:
                self._reply(404, {})

        def do_GET(self) -> None:
            self._handle("GET")

        def do_POST(self) -> None:
            self._handle("POST")

        def log_message(self, format: str, *args: Any) -> None:
            return

    server = HTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    monkeypatch.setattr(reg, "TOKEN_URL", f"{base}/oauth/token")
    monkeypatch.setattr(reg, "ACCOUNTS_URL", f"{base}/tenancy/account")
    monkeypatch.setattr(reg, "AGENT_URL_TEMPLATE", base + "/occm/api/occm")
    monkeypatch.setattr(reg, "pinned_context", lambda pem: None)
    yield state
    server.shutdown()
    server.server_close()


def test_load_config_skip_partial_full() -> None:
    assert reg.load_config({"ip_address": "1.2.3.4"}) is None
    with pytest.raises(reg.RegistrationError, match="console_client_secret"):
        reg.load_config({"ip_address": "1.2.3.4", "console_client_id": "x"})
    cfg = reg.load_config(FULL_VARS)
    assert cfg.company == "agent1"
    assert cfg.site == "default"


def test_parse_setup_status() -> None:
    assert reg.parse_setup_status({}) == (False, "")
    payload = {"setupInfo": {"isSetup": True}, "tenancyServiceInformation": {"accountId": "a"}}
    assert reg.parse_setup_status(payload) == (True, "a")


def test_choose_account() -> None:
    assert reg.choose_account("given", []) == "given"
    assert reg.choose_account("", [{"accountPublicId": "x"}]) == "x"
    two = [
        {"accountPublicId": "x", "accountName": "X"},
        {"accountPublicId": "y", "accountName": "Y"},
    ]
    with pytest.raises(reg.RegistrationError, match=r"x.*y"):
        reg.choose_account("", two)


def test_body_hint_and_redact() -> None:
    cfg = reg.load_config(FULL_VARS)
    assert reg.build_register_body(cfg, "acc") == {
        "adminUser": {"email": "a@example.com"},
        "company": "agent1",
        "site": "default",
        "tenancyAccountId": "acc",
    }
    assert "admin role" in reg.explain_error("User is not associated as admin to x")
    assert reg.explain_error("other") == "other"
    assert SECRET not in reg.redact(f"x {SECRET} y", [SECRET])


def test_happy_path(fake: FakeConsole) -> None:
    cfg = reg.load_config(FULL_VARS)
    assert reg.register(cfg, PIN) == "registered"
    init = next(r for r in fake.requests if r[1].endswith("/setup-portal/init"))
    assert init[2] == f"Bearer {TOKEN}"
    assert init[3]["tenancyAccountId"] == "acc-1"
    assert fake.account == "acc-1"


def test_already_registered_fetches_no_token(fake: FakeConsole) -> None:
    fake.is_setup = True
    assert reg.register(reg.load_config(FULL_VARS), PIN) == "already-registered"
    assert [r[1] for r in fake.requests] == ["/occm/api/occm/system/support-services"]


def test_admin_error_gets_hint(fake: FakeConsole) -> None:
    fake.init_status = 400
    with pytest.raises(reg.RegistrationError, match="admin role"):
        reg.register(reg.load_config(FULL_VARS), PIN)


def test_main_skip_makes_no_call(
    fake: FakeConsole, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("INFRAFOUNDRY_PACKAGE_VARS", json.dumps({"ip_address": "1.2.3.4"}))
    assert reg.main() == 0
    assert fake.requests == []
    assert "skipped" in capsys.readouterr().out


def test_main_never_prints_secret_or_token(
    tmp_path: Path,
    fake: FakeConsole,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("INFRAFOUNDRY_PACKAGE_VARS", json.dumps(FULL_VARS))
    pin_file = tmp_path / "pin.pem"
    pin_file.write_text(PIN)
    assert reg.main(["--agent-cert", str(pin_file)]) == 0
    out = capsys.readouterr()
    assert SECRET not in out.out + out.err
    assert TOKEN not in out.out + out.err


def test_subprocess_without_vars_fails() -> None:
    env = {k: v for k, v in os.environ.items() if k != "INFRAFOUNDRY_PACKAGE_VARS"}
    result = subprocess.run(
        [sys.executable, str(SCRIPT)], env=env, capture_output=True, text=True, check=False
    )
    assert result.returncode == 1
    assert "INFRAFOUNDRY_PACKAGE_VARS" in result.stderr


def test_subprocess_skip() -> None:
    env = {**os.environ, "INFRAFOUNDRY_PACKAGE_VARS": json.dumps({"ip_address": "1.2.3.4"})}
    result = subprocess.run(
        [sys.executable, str(SCRIPT)], env=env, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0


def _gen_cert(tmp_path: Path, name: str) -> tuple[Path, Path]:
    cert, key = tmp_path / f"{name}.pem", tmp_path / f"{name}.key"
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
            f"/CN={name}",
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
def tls_agent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, Path]]:
    if shutil.which("openssl") is None:
        pytest.skip("openssl CLI not available to generate test certificates")
    served, served_key = _gen_cert(tmp_path, "served")
    other, _ = _gen_cert(tmp_path, "other")
    hits: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def _reply(self) -> None:
            hits.append(f"{self.command} {self.path} {self.headers.get('Authorization', '')}")
            data = b"{}"
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:
            self._reply()

        def do_POST(self) -> None:
            self.rfile.read(int(self.headers.get("Content-Length") or 0))
            self._reply()

        def log_message(self, format: str, *args: Any) -> None:
            return

    server = HTTPServer(("127.0.0.1", 0), Handler)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(str(served), str(served_key))
    server.socket = ctx.wrap_socket(server.socket, server_side=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_address[1]
    yield {"served": served, "other": other, "port": Path(str(port)), "hits": Path()}
    server.shutdown()
    server.server_close()


def test_pinned_call_matches_and_mismatch_is_refused(
    tls_agent: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    url = f"https://127.0.0.1:{tls_agent['port']}/x"
    good = tls_agent["served"].read_text()
    bad = tls_agent["other"].read_text()
    assert reg._request(url, method="POST", body={}, token="t", pin=good) == {}
    with pytest.raises(reg.RegistrationError, match="cannot reach"):
        reg._request(url, method="POST", body={}, token="t", pin=bad)
    # The status GET is pinned too: a different certificate is refused.
    cfg = reg.load_config(FULL_VARS)
    assert cfg is not None
    monkeypatch.setattr(reg, "AGENT_URL_TEMPLATE", f"https://127.0.0.1:{tls_agent['port']}")
    with pytest.raises(reg.RegistrationError, match="cannot reach"):
        reg.get_status(cfg, bad)


def test_pin_must_be_a_certificate(tmp_path: Path) -> None:
    with pytest.raises(reg.RegistrationError):
        reg.load_pin("")
    with pytest.raises(reg.RegistrationError, match="cannot read"):
        reg.load_pin(str(tmp_path / "missing.pem"))
    empty = tmp_path / "empty.pem"
    empty.write_text("")
    with pytest.raises(reg.RegistrationError, match="not a PEM"):
        reg.load_pin(str(empty))


def test_main_without_pin_fails_closed(
    fake: FakeConsole, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("INFRAFOUNDRY_PACKAGE_VARS", json.dumps(FULL_VARS))
    assert reg.main([]) == 1
    assert "--agent-cert" in capsys.readouterr().err
    assert fake.requests == []


def test_post_script_fetches_cert_over_ssh_and_passes_path() -> None:
    text = (SCRIPT.parent / "console-connector-post-terraform.sh").read_text()
    assert 'remote_cmd "${ip_address}" "openssl s_client' in text
    assert '--agent-cert "$AGENT_CERT"' in text
    assert "mktemp" in text and 'rm -f "$WAIT_ERR" "$CURL_ERR" "$AGENT_CERT"' in text
