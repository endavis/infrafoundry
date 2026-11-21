"""Static checks that shipped k3s roles and scripts keep the kubeconfig owner-only (#1577)."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

BLUEPRINT = Path(__file__).resolve().parents[2] / "blueprints" / "k3s-cluster"
SERVER_TASKS = BLUEPRINT / "roles" / "k3s-server" / "tasks" / "main.yml"


def _tasks() -> list[dict[str, object]]:
    loaded = yaml.safe_load(SERVER_TASKS.read_text())
    assert isinstance(loaded, list)
    return loaded


def test_server_config_writes_owner_only_kubeconfig_mode() -> None:
    """The k3s config.yaml written by the server role sets mode 0600."""
    task = next(t for t in _tasks() if t.get("name") == "Write k3s config.yaml")
    content = task["copy"]["content"]  # type: ignore[index]
    assert 'write-kubeconfig-mode: "0600"' in content
    assert "0644" not in content


def test_no_shipped_file_sets_a_readable_kubeconfig_mode() -> None:
    """No k3s role, playbook or script sets a group- or world-readable kubeconfig mode."""
    for path in BLUEPRINT.rglob("*"):
        if not path.is_file() or path.suffix not in {".yml", ".yaml", ".sh"}:
            continue
        text = path.read_text()
        assert 'write-kubeconfig-mode: "0644"' not in text, path
        assert "write-kubeconfig-mode 644" not in text, path


def test_local_kubeconfig_copy_is_enforced_to_0600() -> None:
    """A localhost task sets mode 0600 on the fetched kubeconfig, after the fetch."""
    tasks = _tasks()
    names = [t.get("name") for t in tasks]
    fetch_idx = names.index("Fetch kubeconfig from control node")
    task = next(t for t in tasks if t.get("name") == "Restrict the local kubeconfig to its owner")
    assert names.index(task["name"]) > fetch_idx
    assert task["delegate_to"] == "localhost"
    assert task["file"]["mode"] == "0600"  # type: ignore[index]


# --- after_apply handler for existing clusters ---


ROLE = BLUEPRINT / "roles" / "k3s-kubeconfig-mode"
PLAYBOOK = BLUEPRINT / "playbooks" / "k3s-kubeconfig-mode.yml"
HANDLER = BLUEPRINT / "scripts" / "oci" / "k3s-kubeconfig-mode.sh"

_FAKE_ANSIBLE = """#!/bin/sh
echo "$@" > "$RECORD_DIR/args"
prev=""
for arg in "$@"; do
    [ "$prev" = "-i" ] && cp "$arg" "$RECORD_DIR/inventory.yml"
    prev="$arg"
done
exit "${FAKE_ANSIBLE_RC:-0}"
"""

_HANDLER_ENV = {
    "K3S_CONTROL_NAME": "ctl",
    "K3S_WORKER_NAMES": "w0,w1",
    "K3S_TAILNET": "example.net",
}


def _run_handler(
    tmp_path: Path, env_extra: dict[str, str], *, ansible: bool = True
) -> tuple[subprocess.CompletedProcess[str], Path]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    record = tmp_path / "record"
    record.mkdir()
    if ansible:
        stub = bin_dir / "ansible-playbook"
        stub.write_text(_FAKE_ANSIBLE)
        stub.chmod(0o755)
    path = os.environ["PATH"]
    if not ansible:
        path = ":".join(p for p in path.split(":") if not (Path(p) / "ansible-playbook").exists())
    env = {
        "PATH": f"{bin_dir}:{path}",
        "HOME": str(tmp_path),
        "RECORD_DIR": str(record),
        "INFRAFOUNDRY_BLUEPRINT_DIR": str(BLUEPRINT),
        "INFRAFOUNDRY_WARNINGS_FILE": str(tmp_path / "warnings.jsonl"),
        **env_extra,
    }
    result = subprocess.run(
        ["bash", str(HANDLER)], env=env, capture_output=True, text=True, check=False
    )
    return result, record


def test_handler_is_executable_in_the_tree() -> None:
    """k3s-kubeconfig-mode.sh has the executable bit set."""
    assert os.access(HANDLER, os.X_OK)


def test_handler_runs_the_playbook_as_the_ansible_user(tmp_path: Path) -> None:
    """The handler runs only its playbook against an inventory using the login user."""
    result, record = _run_handler(tmp_path, _HANDLER_ENV)

    assert result.returncode == 0, result.stderr + result.stdout
    assert (record / "args").read_text().strip().endswith(str(PLAYBOOK))
    children = yaml.safe_load((record / "inventory.yml").read_text())["all"]["children"]
    control = children["k3s_control"]["hosts"]["ctl"]
    assert control["ansible_host"] == "ctl.example.net"
    assert control["ansible_user"] == "ansible"


def test_handler_missing_ansible_exits_127(tmp_path: Path) -> None:
    """A missing ansible-playbook is exit 127."""
    result, _ = _run_handler(tmp_path, _HANDLER_ENV, ansible=False)

    assert result.returncode == 127


def test_handler_requires_a_control_name(tmp_path: Path) -> None:
    """Without K3S_CONTROL_NAME the handler fails before ansible."""
    result, record = _run_handler(tmp_path, {**_HANDLER_ENV, "K3S_CONTROL_NAME": ""})

    assert result.returncode != 0
    assert not (record / "args").exists()


def test_handler_failure_keeps_rc_and_writes_a_warning(tmp_path: Path) -> None:
    """A failing playbook keeps its exit code and appends one JSONL warning."""
    result, _ = _run_handler(tmp_path, {**_HANDLER_ENV, "FAKE_ANSIBLE_RC": "4"})

    assert result.returncode == 4
    (line,) = (tmp_path / "warnings.jsonl").read_text().splitlines()
    assert json.loads(line)["source"] == "k3s-kubeconfig-mode"


def test_handler_is_wired_after_bootstrap_and_continues_on_error() -> None:
    """The handler runs after k3s-bootstrap, with continue_on_error and node env."""
    blueprint = yaml.safe_load((BLUEPRINT / "blueprint.yaml").read_text())
    handlers = blueprint["providers"]["oci"]["events"]["after_apply"]
    names = [h["name"] for h in handlers]

    assert names.index("k3s-kubeconfig-mode") > names.index("k3s-bootstrap")
    handler = handlers[names.index("k3s-kubeconfig-mode")]
    assert handler["script"] == "scripts/oci/k3s-kubeconfig-mode.sh"
    assert handler["continue_on_error"] is True
    assert set(handler["env"]) == {"K3S_CONTROL_NAME", "K3S_WORKER_NAMES", "K3S_TAILNET"}


def test_role_only_edits_the_mode_setting_and_file_mode() -> None:
    """The role edits one config line and a file mode; nothing is started or run."""
    tasks = yaml.safe_load((ROLE / "tasks" / "main.yml").read_text())
    modules = [next(k for k in t if k.startswith("ansible.builtin.")) for t in tasks]

    assert modules == [
        "ansible.builtin.lineinfile",
        "ansible.builtin.stat",
        "ansible.builtin.file",
    ]
    line = tasks[0]["ansible.builtin.lineinfile"]
    assert line["regexp"] == "^write-kubeconfig-mode:"
    assert line["path"].endswith("/config.yaml")
    file_task = tasks[2]["ansible.builtin.file"]
    assert file_task["path"].endswith("/k3s.yaml")
    assert file_task["mode"] == "{{ k3s_kubeconfig_mode }}"
    defaults = yaml.safe_load((ROLE / "defaults" / "main.yml").read_text())
    assert defaults["k3s_kubeconfig_mode"] == "0600"


def test_playbook_targets_only_the_control_plane_with_become() -> None:
    """The playbook runs the role on the control plane as root."""
    (play,) = yaml.safe_load(PLAYBOOK.read_text())

    assert play["hosts"] == "k3s_control"
    assert play["become"] is True
    assert play["roles"] == ["k3s-kubeconfig-mode"]


@pytest.mark.skipif(shutil.which("ansible-playbook") is None, reason="no ansible")
def test_playbook_syntax_check(tmp_path: Path) -> None:
    """ansible accepts the playbook."""
    inventory = tmp_path / "inv.yml"
    inventory.write_text("all:\n  children:\n    k3s_control:\n      hosts:\n        n1: {}\n")
    env = {**os.environ, "ANSIBLE_ROLES_PATH": str(BLUEPRINT / "roles")}
    result = subprocess.run(
        ["ansible-playbook", "-i", str(inventory), "--syntax-check", str(PLAYBOOK)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr + result.stdout
