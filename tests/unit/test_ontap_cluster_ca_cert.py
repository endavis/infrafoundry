"""``ontap_ca_cert`` turns on certificate verification for every ONTAP call (#1645).

Structural checks over the blueprint's playbooks and roles, plus real Ansible
runs of the shared group vars, the missing-file check and the probe role
against a local TLS server.
"""

from __future__ import annotations

import json
import os
import shutil
import ssl
import subprocess
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
import yaml

from infrafoundry.core.config.blueprint_resolver import BlueprintResolver

REPO_ROOT = Path(__file__).resolve().parents[2]
BLUEPRINT = REPO_ROOT / "blueprints" / "ontap-cluster"
PLAYBOOKS = sorted(BLUEPRINT.glob("ontap-sim-*.yml"))
TASK_FILES = sorted((BLUEPRINT / "roles").glob("*/tasks/*.yml"))
VALIDATE = "{{ ontap_validate_certs }}"
PASSWORD = "S3cret-pw-1645"
ROLES = ("ontap-cluster-probe", "ontap-post-cluster", "ontap-console-restore")


def _load(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _walk(tasks: list[dict[str, Any]]) -> Iterator[dict[str, Any]]:
    """Yield every task, recursing into block, rescue and always."""
    for task in tasks:
        yield task
        for key in ("block", "rescue", "always"):
            yield from _walk(task.get(key) or [])


def _all_tasks() -> Iterator[tuple[Path, dict[str, Any]]]:
    for path in TASK_FILES:
        yield from ((path, t) for t in _walk(_load(path)))
    for path in PLAYBOOKS:
        for play in _load(path):
            for key in ("pre_tasks", "tasks", "post_tasks"):
                yield from ((path, t) for t in _walk(play.get(key) or []))


def _play(name: str, play_name: str) -> dict[str, Any]:
    return next(p for p in _load(BLUEPRINT / name) if p["name"] == play_name)


@pytest.mark.unit
class TestBlueprintInput:
    """The input is declared once, empty by default."""

    def test_declared_in_resolver(self) -> None:
        """The resolver lists the input with an empty default."""
        resolved = BlueprintResolver(REPO_ROOT / "example-config" / "envs").resolve("ontap-cluster")
        assert "ontap_ca_cert" in resolved["input_names"]
        assert resolved["defaults"]["ontap_ca_cert"] == ""

    def test_declared_once_with_description(self) -> None:
        """The raw manifest declares it exactly once, described."""
        inputs = _load(BLUEPRINT / "blueprint.yaml")["inputs"]
        matches = [i for i in inputs if i.get("name") == "ontap_ca_cert"]
        assert len(matches) == 1
        assert matches[0].get("description")


@pytest.mark.unit
class TestEveryCallSite:
    """No call hard-codes verification off, and each one can take the CA."""

    def test_no_hard_coded_validate_certs_false(self) -> None:
        """A text scan finds no ``validate_certs: false`` in the blueprint's YAML."""
        for path in [*PLAYBOOKS, *TASK_FILES]:
            for line in path.read_text(encoding="utf-8").splitlines():
                code = line.split("#", 1)[0].replace(" ", "")
                assert "validate_certs:false" not in code, f"{path.name}: {line}"

    def test_uri_tasks_take_the_ca(self) -> None:
        """Every https ``uri`` task validates through the group var and passes ca_path."""
        seen = 0
        for path, task in _all_tasks():
            args = task.get("ansible.builtin.uri")
            if not args or not str(args["url"]).startswith("https://"):
                continue
            seen += 1
            assert args.get("validate_certs") == VALIDATE, f"{path.name}: {task['name']}"
            assert "ontap_ca_cert" in str(args.get("ca_path")), f"{path.name}: {task['name']}"
        assert seen >= 8

    def test_netapp_tasks_use_the_group_var(self) -> None:
        """Every netapp module call, plus the shared anchor, validates through the group var."""
        for path, task in _all_tasks():
            for key, args in task.items():
                if key.startswith("netapp.ontap.") and isinstance(args, dict):
                    assert args.get("validate_certs") == VALIDATE, f"{path.name}: {task['name']}"
        conn = next(
            t
            for t in _walk(_load(BLUEPRINT / "roles/ontap-post-cluster/tasks/main.yml"))
            if t["name"] == "Set ONTAP connection facts"
        )
        assert conn["ansible.builtin.set_fact"]["ontap_connection"]["validate_certs"] == VALIDATE

    def test_netapp_tasks_get_the_ca_environment(self) -> None:
        """The post-cluster play and the console-restore halt carry the environment."""
        play = _play(
            "ontap-sim-cluster-setup.yml", "Configure ONTAP cluster (aggregates, SVMs, LIFs)"
        )
        assert "ontap_tls_environment" in str(play["environment"])
        assert "ontap_validate_certs" not in play["roles"][0]["vars"]
        halt = next(
            t
            for t in _walk(_load(BLUEPRINT / "roles/ontap-console-restore/tasks/main.yml"))
            if str(t["name"]).startswith("Halt ONTAP node")
        )
        assert "ontap_tls_environment" in str(halt["environment"])

    @pytest.mark.parametrize("role", ROLES)
    def test_role_defaults_keep_verification_off(self, role: str) -> None:
        """Standalone, each role still skips verification and has no CA."""
        defaults = _load(BLUEPRINT / "roles" / role / "defaults" / "main.yml")
        assert defaults["ontap_validate_certs"] is False
        assert defaults["ontap_ca_cert"] == ""


@pytest.mark.unit
class TestPreflightOrdering:
    """A missing CA file stops the run, without displacing the existing first checks."""

    @pytest.mark.parametrize(
        "name", ["ontap-sim-cluster-setup.yml", "ontap-sim-console-restore.yml"]
    )
    def test_localhost_play_asserts_ca_second(self, name: str) -> None:
        """The password assert stays first; the CA-file assert follows it."""
        play = _load(BLUEPRINT / name)[0]
        assert "ontap_password" in str(play["tasks"][0])
        assert "ontap_ca_cert" in str(play["tasks"][1]["ansible.builtin.assert"])

    def test_serial_setup_asserts_before_the_probe(self) -> None:
        """The probe stays the first play; its pre_tasks hold the CA-file assert."""
        play = _load(BLUEPRINT / "ontap-sim-serial-setup.yml")[0]
        assert play["roles"][0]["role"] == "ontap-cluster-probe"
        assert "ontap_ca_cert" in str(play["pre_tasks"][0]["ansible.builtin.assert"])


needs_ansible = pytest.mark.skipif(
    shutil.which("ansible-playbook") is None or shutil.which("openssl") is None,
    reason="needs ansible-playbook and openssl",
)


def _env(tmp_path: Path, **extra: str) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("INFRAFOUNDRY_VAR_")}
    return {
        **env,
        "ANSIBLE_CONFIG": str(BLUEPRINT / "ansible.cfg"),
        "ANSIBLE_ROLES_PATH": str(BLUEPRINT / "roles"),
        "ANSIBLE_FILTER_PLUGINS": str(BLUEPRINT / "filter_plugins"),
        "ANSIBLE_LOCAL_TEMP": str(tmp_path / "ansible-tmp"),
        "ANSIBLE_HOME": str(tmp_path / "ansible-home"),
        "HOME": str(tmp_path),
        **extra,
    }


def _run(tmp_path: Path, play_body: str, **env: str) -> subprocess.CompletedProcess[str]:
    """Run a tmp playbook with the blueprint's group_vars beside it."""
    shutil.copytree(BLUEPRINT / "group_vars", tmp_path / "group_vars", dirs_exist_ok=True)
    (tmp_path / "play.yml").write_text(play_body)
    (tmp_path / "inv.ini").write_text("other ansible_connection=local\n")
    return subprocess.run(
        ["ansible-playbook", "-i", str(tmp_path / "inv.ini"), str(tmp_path / "play.yml")],
        env=_env(tmp_path, **env),
        capture_output=True,
        text=True,
        check=False,
        cwd=tmp_path,
    )


@pytest.mark.unit
@needs_ansible
class TestGroupVars:
    """The shared group vars resolve for the localhost play."""

    PLAY = (
        "- hosts: localhost\n  gather_facts: false\n  connection: local\n  tasks:\n"
        "    - ansible.builtin.debug:\n"
        "        msg: 'V={{ ontap_validate_certs }} C={{ ontap_ca_cert }}"
        " E={{ ontap_tls_environment | to_json }}"
        " R={{ ontap_tls_environment.REQUESTS_CA_BUNDLE | default("
        ") }}"
        " S={{ ontap_tls_environment.SSL_CERT_FILE | default("
        ") }}'\n"
    )

    def test_unset_keeps_verification_off(self, tmp_path: Path) -> None:
        """No input: not validating, no CA, empty environment."""
        result = _run(tmp_path, self.PLAY)
        out = result.stdout + result.stderr
        assert result.returncode == 0, out
        assert "V=False C= E={}" in out

    def test_set_turns_verification_on(self, tmp_path: Path) -> None:
        """A ``~`` path is expanded and fills both environment variables."""
        result = _run(tmp_path, self.PLAY, INFRAFOUNDRY_VAR_ontap_ca_cert="~/x.pem")
        out = result.stdout + result.stderr
        assert result.returncode == 0, out
        ca = str(tmp_path / "x.pem")
        assert "V=True" in out
        assert f"C={ca}" in out
        assert f"R={ca}" in out
        assert f"S={ca}" in out

    def test_missing_file_stops_the_run(self, tmp_path: Path) -> None:
        """The blueprint's own assert fails and names the input."""
        check = _load(BLUEPRINT / "ontap-sim-cluster-setup.yml")[0]["tasks"][1]
        play = yaml.safe_dump(
            [
                {
                    "hosts": "localhost",
                    "gather_facts": False,
                    "connection": "local",
                    "tasks": [check],
                }
            ]
        )
        result = _run(tmp_path, play, INFRAFOUNDRY_VAR_ontap_ca_cert=str(tmp_path / "missing.pem"))
        out = result.stdout + result.stderr
        assert result.returncode != 0
        assert "ontap_ca_cert" in out


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


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        body = json.dumps({"name": "ontap-sim", "records": []}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        return


@pytest.fixture
def served(tmp_path: Path) -> Iterator[tuple[int, Path, Path]]:
    """A local HTTPS server: ``(port, its certificate, another certificate)``."""
    if shutil.which("openssl") is None:
        pytest.skip("openssl CLI not available")
    cert, key = _cert(tmp_path, "cluster")
    other, _ = _cert(tmp_path, "other")
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(str(cert), str(key))
    server.socket = ctx.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield int(server.server_address[1]), cert, other
    server.shutdown()
    server.server_close()


@pytest.mark.unit
@needs_ansible
class TestProbeAgainstTlsServer:
    """The probe role verifies a real certificate against the configured CA."""

    @staticmethod
    def _play(port: int) -> str:
        return (
            "- hosts: other\n  gather_facts: false\n  connection: local\n"
            "  roles:\n    - role: ontap-cluster-probe\n"
            f"      vars:\n        ontap_cluster_mgmt_ip: 127.0.0.1:{port}\n"
            f"        ontap_admin_password: {PASSWORD}\n"
            "        ontap_cluster_name: ontap-sim\n"
            "  post_tasks:\n    - ansible.builtin.debug:\n"
            "        msg: 'exists={{ ontap_cluster_exists }}'\n"
        )

    def test_no_ca_leaves_verification_off(self, tmp_path: Path, served: Any) -> None:
        """Unchanged behaviour: a self-signed server is accepted."""
        port, _, _ = served
        result = _run(tmp_path, self._play(port))
        out = result.stdout + result.stderr
        assert result.returncode == 0, out
        assert "exists=True" in out

    def test_matching_ca_is_accepted(self, tmp_path: Path, served: Any) -> None:
        """The served certificate as the CA verifies."""
        port, cert, _ = served
        result = _run(tmp_path, self._play(port), INFRAFOUNDRY_VAR_ontap_ca_cert=str(cert))
        out = result.stdout + result.stderr
        assert result.returncode == 0, out
        assert "exists=True" in out

    def test_other_ca_stops_with_the_certificate_reason(self, tmp_path: Path, served: Any) -> None:
        """A CA that does not trust the server fails the run, without the password."""
        port, _, other = served
        result = _run(tmp_path, self._play(port), INFRAFOUNDRY_VAR_ontap_ca_cert=str(other))
        out = result.stdout + result.stderr
        assert result.returncode != 0
        assert "ontap_ca_cert" in out
        assert PASSWORD not in out
