"""Tests for blueprints/ontap-cluster/scripts/ontap-console-discover.py (#1140).

No real network: HTTP calls go to an in-process fake Console through a patched
API_URL and TOKEN_URL.
"""

import importlib.util
import json
import os
import subprocess
import sys
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
BLUEPRINT = ROOT / "blueprints" / "ontap-cluster"
SCRIPT = BLUEPRINT / "scripts" / "ontap-console-discover.py"
SECRET = "s3cr3t-value"
PASSWORD = "ontap-pa55"
TOKEN = "tok-abc-123"
AGENT = "agent1clients"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("ontap_console_discover", SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ontap_console_discover"] = mod
    spec.loader.exec_module(mod)
    return mod


disc: Any = _load()

FULL_VARS: dict[str, Any] = {
    "cluster_name": "lab",
    "cluster_mgmt_ip": "10.0.0.80",
    "ontap_password": PASSWORD,
    "console_client_id": "cid",
    "console_client_secret": SECRET,
    "console_agent_id": AGENT,
}


class FakeConsole:
    """Records requests and serves canned responses."""

    def __init__(self) -> None:
        self.systems: list[dict[str, Any]] = []
        self.accounts: list[dict[str, str]] = [{"accountPublicId": "acc-1", "accountName": "One"}]
        self.workspaces: list[dict[str, str]] = [
            {"workspacePublicId": "ws-1", "workspaceName": "Test"}
        ]
        self.post_status = 200
        self.requests: list[tuple[str, str, dict[str, str], dict[str, Any]]] = []


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
            headers = {k.lower(): v for k, v in self.headers.items()}
            state.requests.append((method, self.path, headers, body))
            path = self.path.split("?")[0]
            if path == "/oauth/token":
                self._reply(200, {"access_token": TOKEN})
            elif path == "/tenancy/account":
                self._reply(200, state.accounts)
            elif path == "/tenancy/account/acc-1/workspace":
                self._reply(200, state.workspaces)
            elif path == "/occm/api/onprem/working-environments" and method == "GET":
                self._reply(200, state.systems)
            elif path == "/occm/api/onprem/working-environments":
                if state.post_status != 200:
                    self._reply(state.post_status, {"message": f"bad password {PASSWORD}"})
                    return
                system = {"publicId": "OnPrem-1", "name": body["name"]}
                state.systems.append(system)
                self._reply(200, system)
            else:
                self._reply(404, {})

        def do_GET(self) -> None:
            self._handle("GET")

        def do_POST(self) -> None:
            self._handle("POST")

        def log_message(self, format: str, *args: Any) -> None:
            return

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    monkeypatch.setattr(disc, "TOKEN_URL", f"{base}/oauth/token")
    monkeypatch.setattr(disc, "API_URL", base)
    yield state
    server.shutdown()
    server.server_close()


def _posts(fake: FakeConsole) -> list[dict[str, Any]]:
    return [
        body
        for method, path, _, body in fake.requests
        if method == "POST" and path.startswith("/occm/api/onprem")
    ]


def test_load_config_skip_partial_full() -> None:
    assert disc.load_config({"cluster_mgmt_ip": "1.2.3.4"}) is None
    with pytest.raises(disc.DiscoveryError, match="console_client_secret, console_agent_id"):
        disc.load_config({"console_client_id": "x"})
    cfg = disc.load_config(FULL_VARS)
    assert cfg.system_name == "lab"
    assert cfg.cluster_user == "admin"
    assert cfg.agent_id == AGENT


def test_load_config_requires_cluster_password() -> None:
    with pytest.raises(disc.DiscoveryError, match="ontap_password"):
        disc.load_config({**FULL_VARS, "ontap_password": ""})


def test_choose_one() -> None:
    items = [{"id": "a", "n": "A"}, {"id": "b", "n": "B"}]
    assert disc.choose_one("x", items, "id", "n", "thing", "set_me") == "x"
    assert disc.choose_one("", items[:1], "id", "n", "thing", "set_me") == "a"
    with pytest.raises(disc.DiscoveryError, match=r"set set_me to one of: A \(a\), B \(b\)"):
        disc.choose_one("", items, "id", "n", "thing", "set_me")


def test_find_existing_matches_name_or_address() -> None:
    cfg = disc.load_config(FULL_VARS)
    by_name = {"name": "lab", "publicId": "p1"}
    by_ip = {"name": "other", "ontapClusterProperties": {"clusterAddress": "10.0.0.80"}}
    other = {"name": "other", "ontapClusterProperties": {"clusterAddress": "10.0.0.81"}}
    assert disc.find_existing([other, by_name], cfg) is by_name
    assert disc.find_existing([by_ip], cfg) is by_ip
    assert disc.find_existing([other, {"name": "x", "ontapClusterProperties": None}], cfg) is None


def test_build_discover_body() -> None:
    body = disc.build_discover_body(disc.load_config(FULL_VARS), "ws-1")
    assert body == {
        "name": "lab",
        "description": "ONTAP cluster lab (added by InfraFoundry)",
        "location": "ON_PREM",
        "clusterAddress": "10.0.0.80",
        "clusterUserName": "admin",
        "clusterPassword": PASSWORD,
        "tenantId": "ws-1",
    }


def test_discover_adds_cluster_through_the_agent(fake: FakeConsole) -> None:
    msg = disc.discover(disc.load_config(FULL_VARS))

    assert "added cluster 10.0.0.80" in msg
    assert "ws-1" in msg
    assert [b["tenantId"] for b in _posts(fake)] == ["ws-1"]
    onprem = [r for r in fake.requests if r[1].startswith("/occm/api/onprem")]
    assert onprem[0][1].endswith("?fields=ontapClusterProperties")
    for _, _, headers, _ in onprem:
        assert headers["x-agent-id"] == AGENT
        assert headers["authorization"] == f"Bearer {TOKEN}"


def test_discover_is_idempotent(fake: FakeConsole) -> None:
    fake.systems = [{"name": "lab", "publicId": "OnPrem-9"}]

    msg = disc.discover(disc.load_config(FULL_VARS))

    assert "already in the NetApp Console" in msg
    assert "OnPrem-9" in msg
    assert _posts(fake) == []


def test_configured_workspace_skips_lookup(fake: FakeConsole) -> None:
    disc.discover(disc.load_config({**FULL_VARS, "console_workspace_id": "ws-x"}))

    assert [b["tenantId"] for b in _posts(fake)] == ["ws-x"]
    assert not any(r[1].startswith("/tenancy") for r in fake.requests)


def test_ambiguous_workspace_fails_without_posting(fake: FakeConsole) -> None:
    fake.workspaces.append({"workspacePublicId": "ws-2", "workspaceName": "Prod"})

    with pytest.raises(disc.DiscoveryError, match="console_workspace_id"):
        disc.discover(disc.load_config(FULL_VARS))
    assert _posts(fake) == []


def _run_script(fake_base: str, package_vars: dict[str, Any]) -> subprocess.CompletedProcess[str]:
    """Run the script as a subprocess against the fake Console."""
    wrapper = (
        "import runpy, sys; sys.argv = [sys.argv[1]]; "
        "g = runpy.run_path(sys.argv[0], run_name='discover'); "
        f"g['TOKEN_URL'] = {fake_base + '/oauth/token'!r}; g['API_URL'] = {fake_base!r}; "
        "g['main'].__globals__.update(TOKEN_URL=g['TOKEN_URL'], API_URL=g['API_URL']); "
        "sys.exit(g['main']())"
    )
    env = {**os.environ, "INFRAFOUNDRY_PACKAGE_VARS": json.dumps(package_vars)}
    return subprocess.run(
        [sys.executable, "-c", wrapper, str(SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def test_main_skips_without_inputs() -> None:
    result = _run_script("http://127.0.0.1:9", {"cluster_mgmt_ip": "10.0.0.80"})
    assert result.returncode == 0
    assert "skipping" in result.stdout


def test_main_redacts_secrets_on_error(fake: FakeConsole) -> None:
    fake.post_status = 400
    result = _run_script(disc.API_URL, FULL_VARS)

    assert result.returncode == 1
    assert "HTTP 400" in result.stderr
    assert PASSWORD not in result.stderr + result.stdout
    assert SECRET not in result.stderr + result.stdout


def test_script_is_executable_and_wired_into_post_terraform() -> None:
    assert os.access(SCRIPT, os.X_OK)
    post = (BLUEPRINT / "scripts" / "ontap-post-terraform.sh").read_text()
    assert 'python3 "${BLUEPRINT_DIR}/scripts/ontap-console-discover.py"' in post


def test_blueprint_declares_optional_console_inputs() -> None:
    inputs = {
        i["name"]: i for i in yaml.safe_load((BLUEPRINT / "blueprint.yaml").read_text())["inputs"]
    }
    for name in (
        "console_client_id",
        "console_client_secret",
        "console_agent_id",
        "console_account_id",
        "console_workspace_id",
        "console_system_name",
    ):
        assert inputs[name]["default"] == ""
        assert not inputs[name].get("required")
    assert inputs["console_cluster_user"]["default"] == "admin"
