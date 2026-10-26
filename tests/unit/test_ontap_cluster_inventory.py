"""The inventory the ontap-cluster post-terraform script generates (#1049).

The script writes ``.generated-inventory.json`` and runs ``ansible-playbook``.
These tests run it with a stand-in ``ansible-playbook`` that only records its
arguments, then read the inventory it wrote.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BLUEPRINT_DIR = REPO_ROOT / "blueprints" / "ontap-cluster"
SCRIPT = BLUEPRINT_DIR / "scripts" / "ontap-post-terraform.sh"

PACKAGE_VARS = {
    "cluster_mgmt_ip": "192.0.2.10",
    "node01_target": "pve1",
    "node02_target": "pve2",
    "node01_vmid": 901,
    "node02_vmid": 902,
    "pve1_host": "192.0.2.1",
    "pve2_host": "192.0.2.2",
}


@pytest.fixture
def inventory(tmp_path: Path) -> dict[str, Any]:
    """Run the script and return the inventory it generated."""
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash is not available")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "ansible-playbook"
    fake.write_text('#!/bin/sh\necho "$@" > "$FAKE_ARGS"\n', encoding="utf-8")
    fake.chmod(0o755)
    package_dir = tmp_path / "package"
    package_dir.mkdir()

    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "INFRAFOUNDRY_PACKAGE_DIR": str(package_dir),
        "INFRAFOUNDRY_BLUEPRINT_DIR": str(BLUEPRINT_DIR),
        "INFRAFOUNDRY_PACKAGE_VARS": json.dumps(PACKAGE_VARS),
        "FAKE_ARGS": str(tmp_path / "args"),
    }
    subprocess.run([bash, str(SCRIPT)], env=env, check=True, capture_output=True, text=True)

    generated = package_dir / ".generated-inventory.json"
    assert (tmp_path / "args").read_text(encoding="utf-8").startswith(f"-i {generated} ")
    result: dict[str, Any] = json.loads(generated.read_text(encoding="utf-8"))
    return result


def test_cluster_host_runs_modules_under_the_playbook_python(inventory: dict[str, Any]) -> None:
    host = inventory["all"]["children"]["ontap_cluster"]["hosts"]["ontap-cluster"]

    assert host["ansible_connection"] == "local"
    assert host["ansible_python_interpreter"] == "{{ ansible_playbook_python }}"


def test_proxmox_hosts_keep_interpreter_discovery(inventory: dict[str, Any]) -> None:
    hosts = inventory["all"]["children"]["proxmox_hosts"]["hosts"]

    assert set(hosts) == {"pve1", "pve2"}
    assert all("ansible_python_interpreter" not in host for host in hosts.values())
