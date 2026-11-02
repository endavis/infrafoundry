"""Tests for blueprints/ontap-cluster/scripts/ontap-aiqum-register.py (#1225).

No real network: HTTP calls go to an in-process fake AIQUM over plain http, with
the script's ``Config.scheme`` set to ``http``.
"""

import base64
import dataclasses
import importlib.util
import json
import os
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
import yaml

ROOT = Path(__file__).resolve().parents[2]
BLUEPRINT = ROOT / "blueprints" / "ontap-cluster"
SCRIPTS = BLUEPRINT / "scripts"
SCRIPT = SCRIPTS / "ontap-aiqum-register.py"
ADMIN_PW = "aiqum-pa55"
ONTAP_PW = "ontap-pa55"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("ontap_aiqum_register", SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ontap_aiqum_register"] = mod
    spec.loader.exec_module(mod)
    return mod


aq: Any = _load()

FULL_VARS: dict[str, Any] = {
    "cluster_name": "lab",
    "cluster_mgmt_ip": "172.21.0.80",
    "ontap_password": ONTAP_PW,
    "aiqum_address": "aiqum.example",
    "aiqum_admin_password": ADMIN_PW,
}


class FakeAIQUM:
    """Records requests and serves canned responses."""

    def __init__(self) -> None:
        self.clusters: list[dict[str, Any]] = []
        self.post_status = 201
        self.requests: list[tuple[str, str, dict[str, str], dict[str, Any]]] = []


@pytest.fixture
def fake() -> Iterator[tuple[FakeAIQUM, str]]:
    state = FakeAIQUM()

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
            base = "/api/admin/datasources/clusters"
            if self.path == base and method == "GET":
                self._reply(200, {"records": state.clusters, "num_records": len(state.clusters)})
            elif self.path == base and method == "POST":
                if state.post_status >= 400 and state.post_status != 409:
                    self._reply(state.post_status, {"error": f"bad password {ONTAP_PW}"})
                else:
                    self._reply(state.post_status, {})
            elif self.path.startswith(base + "/") and method == "DELETE":
                key = self.path.rsplit("/", 1)[1]
                state.clusters = [c for c in state.clusters if c.get("key") != key]
                self._reply(200, {})
            else:
                self._reply(404, {})

        def do_GET(self) -> None:
            self._handle("GET")

        def do_POST(self) -> None:
            self._handle("POST")

        def do_DELETE(self) -> None:
            self._handle("DELETE")

        def log_message(self, format: str, *args: Any) -> None:
            return

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield state, f"127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def _cfg(address: str, **extra: Any) -> Any:
    cfg = aq.load_config({**FULL_VARS, "aiqum_address": address, **extra})
    return dataclasses.replace(cfg, scheme="http")


def _calls(state: FakeAIQUM, method: str) -> list[tuple[str, dict[str, str], dict[str, Any]]]:
    return [(p, h, b) for m, p, h, b in state.requests if m == method]


def test_load_config_skip_partial_defaults() -> None:
    assert aq.load_config({"cluster_mgmt_ip": "1.2.3.4"}) is None
    with pytest.raises(aq.AIQUMError, match="aiqum_admin_password"):
        aq.load_config({"aiqum_address": "x"})
    with pytest.raises(aq.AIQUMError, match="aiqum_address"):
        aq.load_config({"aiqum_admin_password": "x"})
    cfg = aq.load_config(FULL_VARS)
    assert cfg.admin_user == "umadmin"
    assert cfg.cluster_user == "admin"
    assert cfg.cluster_name == "lab"


@pytest.mark.parametrize("missing", ["cluster_mgmt_ip", "ontap_password"])
def test_load_config_requires_cluster_details(missing: str) -> None:
    with pytest.raises(aq.AIQUMError, match=missing):
        aq.load_config({**FULL_VARS, missing: ""})


def test_build_add_body() -> None:
    cfg = aq.load_config({**FULL_VARS, "aiqum_cluster_user": "svc"})
    assert aq.build_add_body(cfg) == {
        "address": "172.21.0.80",
        "username": "svc",
        "password": ONTAP_PW,
        "port": 443,
        "protocol": "https",
    }


def test_find_matching_by_address_or_name() -> None:
    cfg = aq.load_config(FULL_VARS)
    by_ip = {"address": "172.21.0.80", "key": "k1"}
    by_name = {"address": "172.21.0.99", "name": "lab", "key": "k2"}
    other = {"address": "172.21.0.5", "name": "x", "key": "k3"}
    assert aq.find_matching([by_ip, by_name, other], cfg) == [by_ip, by_name]


def test_register_posts_with_basic_auth(fake: tuple[FakeAIQUM, str]) -> None:
    state, address = fake

    msg = aq.register(_cfg(address))

    assert "added cluster 172.21.0.80" in msg
    ((path, headers, body),) = _calls(state, "POST")
    assert path == "/api/admin/datasources/clusters"
    expected = base64.b64encode(f"umadmin:{ADMIN_PW}".encode()).decode()
    assert headers["authorization"] == f"Basic {expected}"
    assert body["address"] == "172.21.0.80"
    assert body["password"] == ONTAP_PW


def test_register_is_noop_when_present(fake: tuple[FakeAIQUM, str]) -> None:
    state, address = fake
    state.clusters = [{"address": "172.21.0.80", "name": "lab", "key": "k1"}]

    msg = aq.register(_cfg(address))

    assert "nothing to do" in msg
    assert _calls(state, "POST") == []


def test_register_treats_409_as_ok(fake: tuple[FakeAIQUM, str]) -> None:
    state, address = fake
    state.post_status = 409

    assert "already exists" in aq.register(_cfg(address))


def test_remove_deletes_only_matching(fake: tuple[FakeAIQUM, str]) -> None:
    state, address = fake
    state.clusters = [
        {"address": "172.21.0.80", "name": "a", "key": "k1"},
        {"address": "172.21.0.99", "name": "lab", "key": "k2"},
        {"address": "172.21.0.5", "name": "other", "key": "k3"},
    ]

    msg = aq.remove(_cfg(address))

    assert "k1" in msg and "k2" in msg
    assert [p for p, _, _ in _calls(state, "DELETE")] == [
        "/api/admin/datasources/clusters/k1",
        "/api/admin/datasources/clusters/k2",
    ]
    assert [c["key"] for c in state.clusters] == ["k3"]


def test_remove_with_nothing_to_remove(fake: tuple[FakeAIQUM, str]) -> None:
    state, address = fake
    state.clusters = [{"address": "172.21.0.5", "name": "other", "key": "k3"}]

    assert "nothing to do" in aq.remove(_cfg(address))
    assert _calls(state, "DELETE") == []


def test_unreachable_aiqum_raises() -> None:
    with pytest.raises(aq.AIQUMError, match="cannot reach"):
        aq.list_clusters(_cfg("127.0.0.1:9"))


def _run(package_vars: dict[str, Any] | None, *args: str) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if k != "INFRAFOUNDRY_PACKAGE_VARS"}
    if package_vars is not None:
        env["INFRAFOUNDRY_PACKAGE_VARS"] = json.dumps(package_vars)
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], capture_output=True, text=True, env=env, check=False
    )


def test_main_without_package_vars_fails() -> None:
    result = _run(None)
    assert result.returncode == 1
    assert "INFRAFOUNDRY_PACKAGE_VARS" in result.stderr


@pytest.mark.parametrize("args", [(), ("--remove",)])
def test_main_skips_without_inputs(args: tuple[str, ...]) -> None:
    result = _run({"cluster_mgmt_ip": "172.21.0.80"}, *args)
    assert result.returncode == 0
    assert "skipping" in result.stdout


def test_main_error_output_is_redacted(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def boom(cfg: Any) -> str:
        raise aq.AIQUMError(f"HTTP 500: {ADMIN_PW} and {ONTAP_PW}")

    monkeypatch.setenv("INFRAFOUNDRY_PACKAGE_VARS", json.dumps(FULL_VARS))
    monkeypatch.setattr(aq, "remove", boom)

    assert aq.main(["--remove"]) == 1
    err = capsys.readouterr().err
    assert "ERROR: AIQUM removal" in err
    assert ADMIN_PW not in err and ONTAP_PW not in err


def test_make_ssl_context_verifies_by_default() -> None:
    cfg = aq.load_config(FULL_VARS)
    assert cfg.tls_insecure is False
    ctx = aq.make_ssl_context(cfg)
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    assert ctx.check_hostname is True


def test_make_ssl_context_uses_ca_cert() -> None:
    certifi = pytest.importorskip("certifi")
    cfg = aq.load_config({**FULL_VARS, "aiqum_ca_cert": certifi.where()})
    ctx = aq.make_ssl_context(cfg)
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    assert ctx.check_hostname is True
    assert ctx.cert_store_stats()["x509_ca"] > 0


def test_make_ssl_context_rejects_unreadable_ca_cert(tmp_path: Path) -> None:
    cfg = aq.load_config({**FULL_VARS, "aiqum_ca_cert": str(tmp_path / "missing.pem")})
    with pytest.raises(aq.AIQUMError, match="aiqum_ca_cert"):
        aq.make_ssl_context(cfg)


@pytest.mark.parametrize("value", ["true", "True", "1", "yes"])
def test_make_ssl_context_insecure_only_on_opt_in(value: str) -> None:
    cfg = aq.load_config({**FULL_VARS, "aiqum_tls_insecure": value})
    ctx = aq.make_ssl_context(cfg)
    assert ctx.verify_mode == ssl.CERT_NONE
    assert ctx.check_hostname is False


@pytest.mark.parametrize("value", ["", "false", "no", "0"])
def test_make_ssl_context_not_insecure_otherwise(value: str) -> None:
    cfg = aq.load_config({**FULL_VARS, "aiqum_tls_insecure": value})
    assert aq.make_ssl_context(cfg).verify_mode == ssl.CERT_REQUIRED


def test_scripts_are_executable() -> None:
    assert os.access(SCRIPT, os.X_OK)
    assert os.access(SCRIPTS / "ontap-destroy-cleanup.sh", os.X_OK)


def test_wiring_in_shell_scripts() -> None:
    post = (SCRIPTS / "ontap-post-terraform.sh").read_text()
    assert 'python3 "${BLUEPRINT_DIR}/scripts/ontap-aiqum-register.py"' in post
    assert post.index("ontap-console-discover.py") < post.index("ontap-aiqum-register.py")
    cleanup = (SCRIPTS / "ontap-destroy-cleanup.sh").read_text()
    assert 'ontap-console-discover.py" --remove' in cleanup
    assert 'ontap-aiqum-register.py" --remove' in cleanup


def test_cleanup_script_skips_without_inputs(tmp_path: Path) -> None:
    env = {
        **os.environ,
        "INFRAFOUNDRY_BLUEPRINT_DIR": str(BLUEPRINT),
        "INFRAFOUNDRY_PACKAGE_VARS": json.dumps({"cluster_mgmt_ip": "172.21.0.80"}),
    }
    result = subprocess.run(
        ["bash", str(SCRIPTS / "ontap-destroy-cleanup.sh")],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "no console_* inputs set, skipping" in result.stdout
    assert "no aiqum_* inputs set, skipping" in result.stdout


def test_cleanup_script_exits_nonzero_when_a_removal_fails() -> None:
    env = {
        **os.environ,
        "INFRAFOUNDRY_BLUEPRINT_DIR": str(BLUEPRINT),
        "INFRAFOUNDRY_PACKAGE_VARS": json.dumps({"aiqum_address": "x"}),
    }
    result = subprocess.run(
        ["bash", str(SCRIPTS / "ontap-destroy-cleanup.sh")],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert result.returncode == 1
    assert "delete the data source by hand" in result.stderr


def test_blueprint_declares_aiqum_inputs_and_destroy_event() -> None:
    bp = yaml.safe_load((BLUEPRINT / "blueprint.yaml").read_text())
    inputs = {i["name"]: i for i in bp["inputs"]}
    assert inputs["aiqum_address"]["default"] == ""
    assert inputs["aiqum_admin_user"]["default"] == "umadmin"
    assert inputs["aiqum_admin_password"]["default"] == ""
    assert "secret" in inputs["aiqum_admin_password"]["description"]
    assert inputs["aiqum_cluster_user"]["default"] == "admin"
    (create,) = bp["events"]["on_create"]
    (destroy,) = bp["events"]["on_destroy"]
    assert destroy["script"] == "scripts/ontap-destroy-cleanup.sh"
    assert destroy["continue_on_error"] is True
    assert destroy["requires"] == create["requires"]
