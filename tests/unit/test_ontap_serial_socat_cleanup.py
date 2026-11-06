"""Stale-socat cleanup in the ontap-serial-setup and ontap-console-restore roles (#1280).

Both roles spawn ``socat`` against the VM serial socket from an expect script,
like ontap-cluster-setup (#1173). These tests pin, offline, that each expect
script records the socat pid and kills it on exit, and that each role clears a
stale socat on this VM's socket before the wrapper that spawns it is launched.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from jinja2 import Environment, FileSystemLoader

REPO_ROOT = Path(__file__).resolve().parents[2]
ROLES_DIR = REPO_ROOT / "blueprints" / "ontap-cluster" / "roles"

CASES = [
    ("ontap-serial-setup", "serial-setup.exp.j2", False),
    ("ontap-console-restore", "console-restore.exp.j2", True),
]


def _render(role: str, name: str) -> str:
    env = Environment(
        loader=FileSystemLoader(str(ROLES_DIR / role / "templates")),
        keep_trailing_newline=True,
        autoescape=False,
    )
    return env.get_template(name).render(
        ontap_vmid=220,
        ontap_loader_timeout=60,
        ontap_serial_number="1234",
        ontap_sysid="5678",
    )


def _flatten(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Flatten ``block`` tasks into execution order."""
    flat: list[dict[str, Any]] = []
    for task in tasks:
        if "block" in task:
            flat.extend(_flatten(task["block"]))
        else:
            flat.append(task)
    return flat


def _load_tasks(role: str) -> list[dict[str, Any]]:
    path = ROLES_DIR / role / "tasks" / "main.yml"
    data = yaml.safe_load(path.read_text())
    assert isinstance(data, list)
    return _flatten(data)


@pytest.mark.unit
@pytest.mark.parametrize(("role", "template", "_block"), CASES)
def test_expect_script_kills_socat_on_exit(role: str, template: str, _block: bool) -> None:
    text = _render(role, template)
    assert "set socat_pid [exp_pid]" in text
    assert "exit -onexit { catch { exec kill $::socat_pid } }" in text
    assert text.index("spawn socat") < text.index("exp_pid")


@pytest.mark.unit
@pytest.mark.parametrize(("role", "template", "_block"), CASES)
def test_pkill_task_precedes_wrapper_launch(role: str, template: str, _block: bool) -> None:
    tasks = _load_tasks(role)
    names = [t["name"] for t in tasks]
    kill_idx = names.index("Kill stale socat on the serial socket")
    launch_idx = next(i for i, n in enumerate(names) if n.startswith("Launch wrapper script"))
    assert kill_idx < launch_idx

    kill = tasks[kill_idx]
    argv = kill["ansible.builtin.command"]["argv"]
    assert argv[:2] == ["pkill", "-f"]
    assert argv[2] == "^socat .*UNIX-CONNECT:/var/run/qemu-server/{{ ontap_vmid }}\\.serial0$"
    assert kill["failed_when"] == "stale_socat.rc not in [0, 1]"


@pytest.mark.unit
@pytest.mark.parametrize(("role", "template", "_block"), CASES)
def test_no_jinja_tags_in_task_comments(role: str, template: str, _block: bool) -> None:
    path = ROLES_DIR / role / "tasks" / "main.yml"
    for line in path.read_text().splitlines():
        if line.lstrip().startswith("#"):
            assert "{{" not in line
            assert "{%" not in line
