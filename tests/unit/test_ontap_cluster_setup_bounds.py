"""Bounds on the ontap-cluster-setup expect runs (#1173).

The expect scripts talk to the VM serial socket through ``socat``. A stuck
console used to hold the run (and the socket) far past the handler timeout, so
the role now caps each run with an in-script deadline, a ``timeout`` wrapper
and a stale-socat cleanup. These tests pin that wiring offline.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

import pytest
import yaml
from jinja2 import Environment, FileSystemLoader

REPO_ROOT = Path(__file__).resolve().parents[2]
BLUEPRINT_DIR = REPO_ROOT / "blueprints" / "ontap-cluster"
ROLE_DIR = BLUEPRINT_DIR / "roles" / "ontap-cluster-setup"
TEMPLATE_DIR = ROLE_DIR / "templates"
TASKS_FILE = ROLE_DIR / "tasks" / "main.yml"
DEFAULTS_FILE = ROLE_DIR / "defaults" / "main.yml"
MANIFEST = BLUEPRINT_DIR / "blueprint.yaml"


def _render(name: str, **context: Any) -> str:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        keep_trailing_newline=True,
        autoescape=False,
    )
    return env.get_template(name).render(**context)


@pytest.fixture(scope="module")
def defaults() -> dict[str, Any]:
    """Role defaults."""
    data = yaml.safe_load(DEFAULTS_FILE.read_text())
    assert isinstance(data, dict)
    return data


@pytest.fixture(scope="module")
def tasks() -> list[dict[str, Any]]:
    """Role tasks."""
    data = yaml.safe_load(TASKS_FILE.read_text())
    assert isinstance(data, list)
    return data


@pytest.mark.unit
class TestDeadlines:
    """The deadline defaults fit under the handler timeout."""

    def test_deadlines_are_ints(self, defaults: dict[str, Any]) -> None:
        assert isinstance(defaults["ontap_setup_deadline"], int)
        assert isinstance(defaults["ontap_join_deadline"], int)

    def test_deadline_exceeds_per_prompt_timeout(self, defaults: dict[str, Any]) -> None:
        assert defaults["ontap_setup_deadline"] > defaults["ontap_setup_timeout"]
        assert defaults["ontap_join_deadline"] > defaults["ontap_join_timeout"]

    def test_deadlines_fit_in_handler_timeout(self, defaults: dict[str, Any]) -> None:
        manifest = yaml.safe_load(MANIFEST.read_text())
        handler = next(
            h for h in manifest["events"]["on_create"] if h["name"] == "ontap-cluster-setup"
        )
        # +60 is the margin added to the ``timeout`` wrapper in tasks/main.yml.
        total = (defaults["ontap_setup_deadline"] + 60) + (defaults["ontap_join_deadline"] + 60)
        assert total < handler["timeout"]


@pytest.mark.unit
class TestTasks:
    """Tasks wrap each expect run and clear stale socat first."""

    @pytest.mark.parametrize("marker", ["Run cluster create", "Run cluster join"])
    def test_run_task_uses_timeout_wrapper(self, tasks: list[dict[str, Any]], marker: str) -> None:
        task = next(t for t in tasks if t["name"].startswith(marker))
        assert task["ansible.builtin.command"]["cmd"].startswith("timeout --kill-after=")

    @pytest.mark.parametrize("marker", ["Run cluster create", "Run cluster join"])
    def test_pkill_precedes_run_task(self, tasks: list[dict[str, Any]], marker: str) -> None:
        idx = next(i for i, t in enumerate(tasks) if t["name"].startswith(marker))
        run, kill = tasks[idx], tasks[idx - 1]
        assert kill["name"] == "Kill stale socat on the serial socket"
        assert kill["when"] == run["when"]
        assert 1 in _allowed_rcs(kill["failed_when"])
        argv = kill["ansible.builtin.command"]["argv"]
        assert argv[0] == "pkill"
        assert "UNIX-CONNECT:/var/run/qemu-server/{{ ontap_vmid }}" in argv[-1]
        assert argv[-1].startswith("^socat ")
        assert argv[-1].endswith("$")

    def test_no_jinja_tags_in_task_comments(self) -> None:
        for line in TASKS_FILE.read_text().splitlines():
            if line.lstrip().startswith("#"):
                assert "{{" not in line
                assert "{%" not in line


def _allowed_rcs(failed_when: str) -> list[int]:
    """Parse ``x.rc not in [0, 1]`` into the allowed rc list."""
    inner = failed_when.split("not in", 1)[1].strip().strip("[]")
    return [int(p) for p in inner.split(",")]


@pytest.mark.unit
class TestTemplates:
    """Both expect templates carry the deadline and the socat cleanup."""

    @pytest.mark.parametrize(
        ("name", "var", "ms"),
        [
            ("cluster-create.exp.j2", "ontap_setup_deadline", 90000),
            ("cluster-join.exp.j2", "ontap_join_deadline", 90000),
        ],
    )
    def test_deadline_and_cleanup(self, name: str, var: str, ms: int) -> None:
        text = _render(
            name,
            ontap_vmid=220,
            ontap_setup_timeout=60,
            ontap_join_timeout=60,
            ontap_setup_deadline=90,
            ontap_join_deadline=90,
            ontap_cluster_name="c",
            ontap_password="p",
            ontap_cluster_mgmt_ip="1.1.1.1",
            ontap_cluster_mgmt_mask="255.255.255.0",
            ontap_cluster_mgmt_gateway="1.1.1.2",
            ontap_node_mgmt_ip="1.1.1.3",
            ontap_node_mgmt_mask="255.255.255.0",
            ontap_node_mgmt_gateway="1.1.1.2",
            ontap_cluster_join_ip="1.1.1.1",
        )
        assert f"after {ms} " in text
        assert "exit -onexit" in text
        assert "exp_pid" in text
        assert text.index("spawn socat") < text.index("exp_pid")
        assert text.index("spawn socat") < text.index(f"after {ms} ")
        assert var  # parametrised for readability


@pytest.mark.unit
@pytest.mark.skipif(shutil.which("expect") is None, reason="expect not installed")
def test_deadline_kills_expect_and_socat(tmp_path: Path) -> None:
    """The deadline ends the run with an error and takes socat down with it."""
    vmid = 900000 + uuid.uuid4().int % 90000
    text = _render(
        "cluster-create.exp.j2",
        ontap_vmid=vmid,
        ontap_setup_timeout=600,
        ontap_setup_deadline=2,
        ontap_cluster_name="c",
        ontap_password="p",
        ontap_cluster_mgmt_ip="1.1.1.1",
        ontap_cluster_mgmt_mask="255.255.255.0",
        ontap_cluster_mgmt_gateway="1.1.1.2",
        ontap_node_mgmt_ip="1.1.1.3",
        ontap_node_mgmt_mask="255.255.255.0",
        ontap_node_mgmt_gateway="1.1.1.2",
    )
    script = tmp_path / "create.exp"
    script.write_text(text)

    bindir = tmp_path / "bin"
    bindir.mkdir()
    pid_file = tmp_path / "socat.pid"
    fake = bindir / "socat"
    fake.write_text(f"#!/bin/sh\necho $$ > {pid_file}\nexec sleep 300\n")
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)

    env = dict(os.environ)
    env["PATH"] = f"{bindir}{os.pathsep}{env['PATH']}"
    start = time.monotonic()
    try:
        proc = subprocess.run(  # nosec B603 B607
            ["expect", "-f", str(script)],
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )
    finally:
        for log in Path("/tmp").glob(f"ontap-cluster-create-{vmid}-*.log"):  # nosec B108
            log.unlink(missing_ok=True)

    assert time.monotonic() - start < 15
    assert proc.returncode != 0
    assert "ERROR:" in proc.stdout + proc.stderr
    pid = int(pid_file.read_text().strip())
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and Path(f"/proc/{pid}").exists():
        stat_text = Path(f"/proc/{pid}/stat").read_text() if Path(f"/proc/{pid}").exists() else ""
        if stat_text and stat_text.rsplit(")", 1)[1].split()[0] == "Z":
            break
        time.sleep(0.05)
    if Path(f"/proc/{pid}/stat").exists():
        assert Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0] == "Z"
