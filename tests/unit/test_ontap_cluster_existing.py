"""A re-run must not touch a cluster that already exists (#1643).

Covers the REST-probe filters, the playbook and role wiring, the console guard
in the expect templates, and a real Ansible run of the probe role.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import socket
import stat
import subprocess
import sys
import uuid
from pathlib import Path
from types import ModuleType
from typing import Any, ClassVar

import pytest
import yaml
from jinja2 import Environment, FileSystemLoader

REPO_ROOT = Path(__file__).resolve().parents[2]
BLUEPRINT = REPO_ROOT / "blueprints" / "ontap-cluster"
PLUGIN = BLUEPRINT / "filter_plugins" / "ontap_cluster_state.py"
PROBE_ROLE = BLUEPRINT / "roles" / "ontap-cluster-probe"
TEMPLATE_DIR = BLUEPRINT / "roles" / "ontap-cluster-setup" / "templates"
PASSWORD = "S3cret-pw-1643"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("ontap_cluster_state", PLUGIN)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ontap_cluster_state"] = mod
    spec.loader.exec_module(mod)
    return mod


plugin: Any = _load()


def _plays(name: str) -> list[dict[str, Any]]:
    data = yaml.safe_load((BLUEPRINT / name).read_text())
    assert isinstance(data, list)
    return data


def _tasks(role: str) -> list[dict[str, Any]]:
    data = yaml.safe_load((BLUEPRINT / "roles" / role / "tasks" / "main.yml").read_text())
    assert isinstance(data, list)
    return data


@pytest.mark.unit
class TestClusterState:
    """ontap_cluster_state classifies the probe answer."""

    @pytest.mark.parametrize(
        "msg",
        [
            "Request failed: <urlopen error [Errno 111] Connection refused>",
            "<urlopen error [Errno 113] No route to host>",
            "<urlopen error [Errno 101] Network is unreachable>",
            "<urlopen error [Errno 113] Host is unreachable>",
            "<urlopen error timed out>",
        ],
    )
    def test_nothing_answers_is_absent(self, msg: str) -> None:
        """Connect-level failures mean no cluster there yet."""
        out = plugin.ontap_cluster_state({"status": -1, "msg": msg}, "c")
        assert out["state"] == "absent"

    @pytest.mark.parametrize(
        "msg",
        [
            "<urlopen error [SSL: WRONG_VERSION_NUMBER]>",
            "Connection closed before a valid response",
        ],
    )
    def test_other_transport_errors_conflict(self, msg: str) -> None:
        """Anything unconfirmable stops the run."""
        assert plugin.ontap_cluster_state({"status": -1, "msg": msg}, "c")["state"] == "conflict"

    @pytest.mark.parametrize(
        "msg",
        [
            "<urlopen error [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed>",
            "Failed to validate the SSL certificate: certificate verify failed",
        ],
    )
    def test_untrusted_certificate_names_the_ca_input(self, msg: str) -> None:
        """A failed certificate check is its own conflict, naming ontap_ca_cert (#1645)."""
        out = plugin.ontap_cluster_state({"status": -1, "msg": msg}, "c")
        assert out["state"] == "conflict"
        assert "ontap_ca_cert" in out["reason"]
        assert "unexpectedly" not in out["reason"]

    def test_matching_name_is_present(self) -> None:
        """The configured cluster answering means it exists."""
        out = plugin.ontap_cluster_state({"status": 200, "json": {"name": "c"}}, "c")
        assert out["state"] == "present"

    def test_other_name_conflicts_and_names_both(self) -> None:
        """A different cluster at the address is a conflict naming both."""
        out = plugin.ontap_cluster_state({"status": 200, "json": {"name": "other"}}, "c")
        assert out["state"] == "conflict"
        assert "other" in out["reason"] and "c" in out["reason"]

    @pytest.mark.parametrize("body", [None, {}, {"name": ""}, "text"])
    def test_no_name_conflicts(self, body: Any) -> None:
        """A 200 without a cluster name cannot be confirmed."""
        out = plugin.ontap_cluster_state({"status": 200, "json": body}, "c")
        assert out["state"] == "conflict"

    @pytest.mark.parametrize("status", [401, 403])
    def test_auth_failure_conflicts_mentioning_password(self, status: int) -> None:
        """Something answers but rejects the password."""
        out = plugin.ontap_cluster_state({"status": status}, "c")
        assert out["state"] == "conflict"
        assert "password" in out["reason"]

    @pytest.mark.parametrize("status", [404, 500])
    def test_other_http_conflicts(self, status: int) -> None:
        """Other HTTP codes are conflicts."""
        assert plugin.ontap_cluster_state({"status": status}, "c")["state"] == "conflict"

    @pytest.mark.parametrize(
        "probe",
        [
            {"status": 401, "url": "https://192.0.2.10/api/cluster"},
            {"status": 200, "json": {"name": "x"}},
            {"status": -1, "msg": "weird failure"},
            {"status": 500},
        ],
    )
    def test_reason_never_holds_the_password(self, probe: dict[str, Any]) -> None:
        """Reasons carry no credentials."""
        assert PASSWORD not in plugin.ontap_cluster_state(probe, "c")["reason"]


@pytest.mark.unit
class TestNodeHasMgmtIp:
    """ontap_node_has_mgmt_ip matches node management addresses."""

    RECORDS: ClassVar[list[dict[str, Any]]] = [
        {"name": "n1", "management_interfaces": [{"ip": {"address": "192.0.2.1"}}]},
        {"name": "n2", "management_interfaces": [{"ip": {"address": "192.0.2.2"}}]},
    ]

    def test_found(self) -> None:
        """A member address is found."""
        assert plugin.ontap_node_has_mgmt_ip(self.RECORDS, "192.0.2.2") is True

    def test_missing(self) -> None:
        """A non-member address is not."""
        assert plugin.ontap_node_has_mgmt_ip(self.RECORDS, "192.0.2.9") is False

    @pytest.mark.parametrize("records", [None, [], [{"name": "n1"}]])
    def test_empty_or_bare_records(self, records: Any) -> None:
        """No records or no interfaces means not joined."""
        assert plugin.ontap_node_has_mgmt_ip(records, "192.0.2.2") is False

    def test_filter_module_exposes_both(self) -> None:
        """Ansible gets both filters."""
        assert set(plugin.FilterModule().filters()) == {
            "ontap_cluster_state",
            "ontap_node_has_mgmt_ip",
        }


def _role_entry(play: dict[str, Any], role: str) -> dict[str, Any]:
    (entry,) = [r for r in play["roles"] if r["role"] == role]
    result: dict[str, Any] = entry
    return result


@pytest.mark.unit
class TestPlaybookWiring:
    """The playbooks probe first and skip what exists."""

    def test_cluster_setup_probe_after_password_assert(self) -> None:
        """plays[0] stays the password assert; the probe is plays[1]."""
        plays = _plays("ontap-sim-cluster-setup.yml")
        assert plays[0]["hosts"] == "localhost"
        assert plays[1]["hosts"] == "ontap_cluster"
        assert plays[1]["connection"] == "local"
        assert _role_entry(plays[1], "ontap-cluster-probe")

    def test_cluster_setup_skips(self) -> None:
        """Create and join are guarded by the probe facts."""
        plays = _plays("ontap-sim-cluster-setup.yml")
        create = next(p for p in plays if p["name"].startswith("Create ONTAP cluster"))
        join = next(p for p in plays if p["name"].startswith("Join ONTAP node 02"))
        assert "ontap_cluster_exists" in _role_entry(create, "ontap-cluster-setup")["when"]
        assert "ontap_node02_joined" in _role_entry(join, "ontap-cluster-setup")["when"]
        assert "ontap_cluster_name" in _role_entry(join, "ontap-cluster-setup")["vars"]

    def test_serial_setup_probes_first_and_skips(self) -> None:
        """Serial setup probes before the VMs are touched."""
        plays = _plays("ontap-sim-serial-setup.yml")
        assert _role_entry(plays[0], "ontap-cluster-probe")
        n1 = next(p for p in plays if "node 01" in p["name"])
        n2 = next(p for p in plays if "node 02" in p["name"])
        assert "ontap_cluster_exists" in _role_entry(n1, "ontap-serial-setup")["when"]
        assert "ontap_node02_joined" in _role_entry(n2, "ontap-serial-setup")["when"]

    def test_ansible_cfg_names_filter_plugins(self) -> None:
        """The plugin directory is configured."""
        assert "filter_plugins" in (BLUEPRINT / "ansible.cfg").read_text()


@pytest.mark.unit
class TestProbeRole:
    """The probe role's tasks."""

    def test_uri_is_tolerant_and_authenticated(self) -> None:
        """The probe never fails the task itself and checks certs per var."""
        task = _tasks("ontap-cluster-probe")[0]
        uri = task["ansible.builtin.uri"]
        assert task["failed_when"] is False
        assert uri["force_basic_auth"] is True
        assert "ontap_validate_certs" in str(uri["validate_certs"])
        assert "timeout" in uri

    def test_assert_precedes_nodes_query_which_needs_present(self) -> None:
        """Conflict stops before the nodes query, which only runs when present."""
        tasks = _tasks("ontap-cluster-probe")
        names = [t["name"] for t in tasks]
        assert names.index("Refuse to touch an unknown cluster") < names.index("List cluster nodes")
        nodes = tasks[names.index("List cluster nodes")]
        assert "present" in nodes["when"]


def _render(name: str, **extra: Any) -> str:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)), keep_trailing_newline=True, autoescape=False
    )
    ctx: dict[str, Any] = {
        "ontap_vmid": 1,
        "ontap_setup_timeout": 600,
        "ontap_setup_deadline": 20,
        "ontap_join_timeout": 300,
        "ontap_join_deadline": 20,
        "ontap_cluster_name": "c",
        "ontap_password": "p",
        "ontap_cluster_mgmt_ip": "1.1.1.1",
        "ontap_cluster_mgmt_mask": "255.255.255.0",
        "ontap_cluster_mgmt_gateway": "1.1.1.2",
        "ontap_node_mgmt_ip": "1.1.1.3",
        "ontap_node_mgmt_mask": "255.255.255.0",
        "ontap_node_mgmt_gateway": "1.1.1.2",
        "ontap_cluster_join_ip": "1.1.1.4",
    }
    ctx.update(extra)
    return env.get_template(name).render(**ctx)


@pytest.mark.unit
@pytest.mark.parametrize("name", ["cluster-create.exp.j2", "cluster-join.exp.j2"])
def test_every_generic_prompt_branch_has_a_guard_before_it(name: str) -> None:
    """Each bare '::>' branch is preceded by the named-cluster refusal."""
    text = _render(name)
    guard = '-ex "c::>" {'
    generic = '"::>" {'
    assert text.count(guard) == text.count(generic) == 3
    pos = 0
    for _ in range(3):
        g = text.index(guard, pos)
        b = text.index(generic, g)
        assert g < b
        assert "exit 1" in text[g:b]
        pos = b + 1


def _run_expect(tmp_path: Path, prompt: str, name: str) -> tuple[str, str, int]:
    vmid = 900000 + uuid.uuid4().int % 90000
    script = tmp_path / "s.exp"
    script.write_text(_render(name, ontap_vmid=vmid, ontap_setup_deadline=4))
    bindir = tmp_path / "bin"
    bindir.mkdir()
    rec = tmp_path / "rec"
    fake = bindir / "socat"
    fake.write_text(f"#!/bin/sh\nprintf '{prompt}'\ncat > {rec}\n")
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    env = {**os.environ, "PATH": f"{bindir}{os.pathsep}{os.environ['PATH']}"}
    try:
        proc = subprocess.run(  # fixed test argv, no shell
            ["expect", "-f", str(script)],
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
            check=False,
        )
    finally:
        for log in Path("/tmp").glob(f"ontap-cluster-*-{vmid}-*.log"):  # test path literal
            log.unlink(missing_ok=True)
    return proc.stdout + proc.stderr, rec.read_text() if rec.exists() else "", proc.returncode


@pytest.mark.unit
@pytest.mark.skipif(shutil.which("expect") is None, reason="no expect")
@pytest.mark.parametrize("name", ["cluster-create.exp.j2", "cluster-join.exp.j2"])
class TestConsoleGuardBehaviour:
    """The expect scripts against a fake console."""

    def test_named_prompt_refuses(self, tmp_path: Path, name: str) -> None:
        """A prompt carrying the cluster name exits non-zero, sending no setup."""
        out, sent, code = _run_expect(tmp_path, "c::> ", name)
        assert code != 0
        assert "ERROR:" in out and "already in cluster" in out
        assert "cluster setup" not in sent

    def test_bare_prompt_still_runs_setup(self, tmp_path: Path, name: str) -> None:
        """A fresh node's bare prompt still gets 'cluster setup' (first create)."""
        _, sent, _ = _run_expect(tmp_path, "::> ", name)
        assert "cluster setup" in sent


@pytest.mark.unit
@pytest.mark.skipif(shutil.which("ansible-playbook") is None, reason="no ansible")
class TestRealAnsible:
    """Run the real Ansible against the role and playbooks."""

    @staticmethod
    def _env(tmp_path: Path, **extra: str) -> dict[str, str]:
        return {
            **os.environ,
            "ANSIBLE_CONFIG": str(BLUEPRINT / "ansible.cfg"),
            "ANSIBLE_ROLES_PATH": str(BLUEPRINT / "roles"),
            "ANSIBLE_FILTER_PLUGINS": str(BLUEPRINT / "filter_plugins"),
            "ANSIBLE_LOCAL_TEMP": str(tmp_path / "ansible-tmp"),
            "ANSIBLE_HOME": str(tmp_path / "ansible-home"),
            **extra,
        }

    def test_closed_port_means_nothing_exists(self, tmp_path: Path) -> None:
        """Nothing listening classifies as absent, with both facts false."""
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        play = tmp_path / "play.yml"
        play.write_text(
            "- hosts: all\n  gather_facts: false\n  connection: local\n"
            "  roles:\n    - role: ontap-cluster-probe\n"
            f"      vars:\n        ontap_cluster_mgmt_ip: 127.0.0.1:{port}\n"
            f"        ontap_admin_password: {PASSWORD}\n"
            "  post_tasks:\n    - ansible.builtin.debug:\n"
            "        msg: 'exists={{ ontap_cluster_exists }} joined={{ ontap_node02_joined }}'\n"
        )
        inv = tmp_path / "inv.ini"
        inv.write_text("localhost ansible_connection=local\n")
        result = subprocess.run(
            ["ansible-playbook", "-i", str(inv), str(play)],
            env=self._env(tmp_path),
            capture_output=True,
            text=True,
            check=False,
        )
        out = result.stdout + result.stderr
        assert result.returncode == 0, out
        assert "exists=False joined=False" in out
        assert PASSWORD not in out

    @pytest.mark.parametrize("name", ["ontap-sim-cluster-setup.yml", "ontap-sim-serial-setup.yml"])
    def test_syntax_check(self, tmp_path: Path, name: str) -> None:
        """Both edited playbooks still parse."""
        inv = tmp_path / "inv.ini"
        inv.write_text("localhost ansible_connection=local\n")
        env = self._env(
            tmp_path,
            INFRAFOUNDRY_VAR_node01_target="localhost",
            INFRAFOUNDRY_VAR_node02_target="localhost",
        )
        result = subprocess.run(
            ["ansible-playbook", "-i", str(inv), str(BLUEPRINT / name), "--syntax-check"],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
