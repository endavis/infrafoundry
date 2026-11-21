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

_PINNED = (
    "ctl,ctl.example.net ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAItest;"
    "w0,w0.example.net ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAItest"
)

_HANDLER_ENV = {
    "K3S_CONTROL_NAME": "ctl",
    "K3S_WORKER_NAMES": "w0,w1",
    "K3S_TAILNET": "example.net",
    "K3S_KNOWN_HOSTS": _PINNED,
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
    assert set(handler["env"]) == {
        "K3S_CONTROL_NAME",
        "K3S_WORKER_NAMES",
        "K3S_TAILNET",
        "K3S_KNOWN_HOSTS",
    }


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


# --- Proxmox variant: after_apply handler and node script (#1578) ---


PVE_DIR = BLUEPRINT / "scripts" / "proxmox"
PVE_HANDLER = PVE_DIR / "k3s-kubeconfig-mode.sh"
PVE_NODE = PVE_DIR / "k3s-kubeconfig-mode-node.sh"

_FAKE_SSH = """#!/bin/sh
printf '%s\\n' "$*" >> "$RECORD_DIR/ssh_calls"
n=$(wc -l < "$RECORD_DIR/ssh_calls")
cat > "$RECORD_DIR/stdin.$n"
if [ -s "$RECORD_DIR/stdin.$n" ]; then cp "$RECORD_DIR/stdin.$n" "$RECORD_DIR/stdin"; fi
case "$*" in *mktemp*) echo /tmp/staged-known-hosts ;; esac
exit "${FAKE_SSH_RC:-0}"
"""

_FAKE_SYSTEMCTL = """#!/bin/sh
printf '%s\\n' "$*" >> "$RECORD_DIR/systemctl_calls"
"""

_KNOWN_HOSTS = "k3s-server,192.0.2.80 ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIExampleSentinelKey0"
_PVE_ENV = {
    "K3S_SERVER_IP": "192.0.2.80",
    "K3S_SERVER_NAME": "k3s-server",
    "K3S_JUMPHOST": "",
    "K3S_KNOWN_HOSTS": _KNOWN_HOSTS,
}


def _stub_env(tmp_path: Path, extra: dict[str, str] | None = None) -> dict[str, str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    record = tmp_path / "record"
    record.mkdir(exist_ok=True)
    for name, body in (("ssh", _FAKE_SSH), ("systemctl", _FAKE_SYSTEMCTL)):
        stub = bin_dir / name
        stub.write_text(body)
        stub.chmod(0o755)
    return {
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "HOME": str(tmp_path),
        "RECORD_DIR": str(record),
        "INFRAFOUNDRY_BLUEPRINT_DIR": str(BLUEPRINT),
        "INFRAFOUNDRY_WARNINGS_FILE": str(tmp_path / "warnings.jsonl"),
        **(extra or {}),
    }


def _run_pve_handler(
    tmp_path: Path, extra: dict[str, str]
) -> tuple[subprocess.CompletedProcess[str], Path]:
    env = _stub_env(tmp_path, extra)
    result = subprocess.run(
        ["bash", str(PVE_HANDLER)], env=env, capture_output=True, text=True, check=False
    )
    return result, Path(env["RECORD_DIR"])


def test_pve_scripts_have_the_expected_modes() -> None:
    """The handler and node script are executable; the sourced library is not."""
    assert os.access(PVE_HANDLER, os.X_OK)
    assert os.access(PVE_NODE, os.X_OK)
    assert not os.access(PVE_DIR / "k3s-lib.sh", os.X_OK)


def test_pve_install_script_sources_the_library() -> None:
    """The install script sources k3s-lib.sh instead of defining the ssh helpers."""
    text = (PVE_DIR / "k3s-post-terraform.sh").read_text()
    assert "scripts/proxmox/k3s-lib.sh" in text
    assert "remote_root_cmd()" not in text
    assert "remote_root_cmd()" in (PVE_DIR / "k3s-lib.sh").read_text()


def test_pve_handler_requires_a_server_ip(tmp_path: Path) -> None:
    """Without K3S_SERVER_IP the handler fails before ssh."""
    result, record = _run_pve_handler(tmp_path, {**_PVE_ENV, "K3S_SERVER_IP": ""})

    assert result.returncode != 0
    assert not (record / "ssh_calls").exists()


def test_pve_handler_direct_mode_pipes_the_node_script(tmp_path: Path) -> None:
    """Direct mode makes one ssh call to ansible@ip with sudo and bash -s."""
    result, record = _run_pve_handler(tmp_path, _PVE_ENV)

    assert result.returncode == 0, result.stderr + result.stdout
    (call,) = (record / "ssh_calls").read_text().splitlines()
    assert "ansible@192.0.2.80" in call
    assert "sudo" in call
    assert "bash -s" in call
    assert "StrictHostKeyChecking=yes" in call
    assert "GlobalKnownHostsFile=/dev/null" in call
    assert "StrictHostKeyChecking=no" not in call
    assert (record / "stdin").read_text() == PVE_NODE.read_text()


def test_pve_handler_jumphost_mode_pipes_the_node_script(tmp_path: Path) -> None:
    """Jumphost mode stages the pinned keys, makes the call, then removes the staged file."""
    result, record = _run_pve_handler(tmp_path, {**_PVE_ENV, "K3S_JUMPHOST": "jump.example"})

    assert result.returncode == 0, result.stderr + result.stdout
    stage, call, cleanup = (record / "ssh_calls").read_text().splitlines()
    # Staging: strict hop to the jumphost with the operator's known_hosts; the pinned
    # lines (one per ";" part) arrive on stdin.
    assert "StrictHostKeyChecking=yes" in stage
    assert "jump.example" in stage
    assert (record / "stdin.1").read_text() == _KNOWN_HOSTS + "\n"
    # The call: the jumphost hop is strict, the inner hop uses the staged file.
    assert "jump.example" in call.split(" ssh ")[0]
    assert "StrictHostKeyChecking=yes" in call.split(" ssh ")[0]
    assert "UserKnownHostsFile=/tmp/staged-known-hosts" in call
    assert "ansible@192.0.2.80" in call
    assert "sudo" in call
    assert "bash -s" in call
    assert (record / "stdin.2").read_text() == PVE_NODE.read_text()
    assert "rm -f '/tmp/staged-known-hosts'" in cleanup


def test_pve_handler_requires_pinned_host_keys(tmp_path: Path) -> None:
    """Without pinned host keys the handler fails before any ssh."""
    result, record = _run_pve_handler(tmp_path, {**_PVE_ENV, "K3S_KNOWN_HOSTS": ""})

    assert result.returncode != 0
    assert "foundry secrets host-keys" in result.stderr
    assert not (record / "ssh_calls").exists()


@pytest.mark.parametrize(
    "extra",
    [{"K3S_SERVER_IP": "192.0.2.80; id"}, {"K3S_JUMPHOST": "jump.example $(id)"}],
)
def test_pve_handler_rejects_invalid_values(tmp_path: Path, extra: dict[str, str]) -> None:
    """Values spliced into ssh command strings are validated before any ssh."""
    result, record = _run_pve_handler(tmp_path, {**_PVE_ENV, **extra})

    assert result.returncode != 0
    assert "invalid" in result.stderr
    assert not (record / "ssh_calls").exists()


def test_pve_handler_failure_keeps_rc_and_writes_a_warning(tmp_path: Path) -> None:
    """A failing ssh keeps its exit code and appends one JSONL warning."""
    result, _ = _run_pve_handler(tmp_path, {**_PVE_ENV, "FAKE_SSH_RC": "7"})

    assert result.returncode == 7
    (line,) = (tmp_path / "warnings.jsonl").read_text().splitlines()
    assert json.loads(line)["source"] == "k3s-kubeconfig-mode"


def _run_node(
    tmp_path: Path,
    unit: str | None = None,
    config: str | None = None,
    kubeconfig: int | None = None,
) -> tuple[subprocess.CompletedProcess[str], Path, Path, Path]:
    env = _stub_env(tmp_path)
    cfg_dir = tmp_path / "k3s"
    cfg_dir.mkdir(exist_ok=True)
    unit_file = tmp_path / "k3s.service"
    if unit is not None:
        unit_file.write_text(unit)
    if config is not None:
        (cfg_dir / "config.yaml").write_text(config)
    if kubeconfig is not None:
        (cfg_dir / "k3s.yaml").write_text("kind: Config\n")
        (cfg_dir / "k3s.yaml").chmod(kubeconfig)
    result = subprocess.run(
        ["bash", str(PVE_NODE), str(cfg_dir), str(unit_file)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return result, cfg_dir, unit_file, Path(env["RECORD_DIR"])


def _systemctl_calls(record: Path) -> list[str]:
    log = record / "systemctl_calls"
    return log.read_text().splitlines() if log.exists() else []


_UNIT_644 = (
    "[Service]\nExecStart=/usr/local/bin/k3s \\\n    server \\\n"
    "    '--write-kubeconfig-mode' \\\n    '644' \\\n    '--disable' \\\n    'traefik' \\\n"
)
_UNIT_600 = _UNIT_644.replace("'644'", "'600'")
_LINE = 'write-kubeconfig-mode: "0600"\n'


def test_node_creates_an_absent_config(tmp_path: Path) -> None:
    """An absent config.yaml is created with the owner-only line."""
    result, cfg_dir, _, _ = _run_node(tmp_path)

    assert result.returncode == 0, result.stderr
    assert (cfg_dir / "config.yaml").read_text() == _LINE


def test_node_replaces_a_readable_config_line_only(tmp_path: Path) -> None:
    """A 0644 line is replaced; every other line is unchanged."""
    before = 'a: 1\nwrite-kubeconfig-mode: "0644"\nb: 2\n'
    result, cfg_dir, _, _ = _run_node(tmp_path, config=before)

    assert result.returncode == 0, result.stderr
    assert (cfg_dir / "config.yaml").read_text() == f"a: 1\n{_LINE}b: 2\n"


def test_node_appends_cleanly_without_a_trailing_newline(tmp_path: Path) -> None:
    """A missing key is appended on its own line when the file lacks a final newline."""
    result, cfg_dir, _, _ = _run_node(tmp_path, config="a: 1")

    assert result.returncode == 0, result.stderr
    assert (cfg_dir / "config.yaml").read_text() == f"a: 1\n{_LINE}"


def test_node_rewrites_the_installer_unit_format(tmp_path: Path) -> None:
    """The installer's two-line flag form becomes 600, with one daemon-reload."""
    result, _, unit, record = _run_node(tmp_path, unit=_UNIT_644)

    assert result.returncode == 0, result.stderr
    assert unit.read_text() == _UNIT_600
    assert _systemctl_calls(record) == ["daemon-reload"]


def test_node_rewrites_the_equals_unit_format(tmp_path: Path) -> None:
    """The --flag=value form becomes 600."""
    before = "ExecStart=/usr/local/bin/k3s server '--write-kubeconfig-mode=644'\n"
    result, _, unit, record = _run_node(tmp_path, unit=before)

    assert result.returncode == 0, result.stderr
    assert "'--write-kubeconfig-mode=600'" in unit.read_text()
    assert _systemctl_calls(record) == ["daemon-reload"]


def test_node_leaves_a_600_unit_alone(tmp_path: Path) -> None:
    """A unit already at 600 is unchanged and systemctl does not run."""
    result, _, unit, record = _run_node(tmp_path, unit=_UNIT_600)

    assert result.returncode == 0, result.stderr
    assert unit.read_text() == _UNIT_600
    assert _systemctl_calls(record) == []


def test_node_without_a_unit_succeeds(tmp_path: Path) -> None:
    """With no unit file the script exits 0 and runs no systemctl."""
    result, _, _, record = _run_node(tmp_path)

    assert result.returncode == 0, result.stderr
    assert _systemctl_calls(record) == []


def test_node_fails_on_an_unrecognised_unit_form(tmp_path: Path) -> None:
    """A non-600 flag the script cannot rewrite fails loudly."""
    before = "ExecStart=/usr/local/bin/k3s server --write-kubeconfig-mode 644\n"
    result, _, _, _ = _run_node(tmp_path, unit=before)

    assert result.returncode == 3
    assert "write-kubeconfig-mode" in result.stderr


def test_node_restricts_an_existing_kubeconfig(tmp_path: Path) -> None:
    """A 0644 k3s.yaml becomes 0600."""
    result, cfg_dir, _, _ = _run_node(tmp_path, kubeconfig=0o644)

    assert result.returncode == 0, result.stderr
    assert (cfg_dir / "k3s.yaml").stat().st_mode & 0o777 == 0o600


def test_node_second_run_changes_nothing_and_never_restarts(tmp_path: Path) -> None:
    """A second run is byte-identical with no extra systemctl; no restart/stop/start ever."""
    _, cfg_dir, unit, record = _run_node(
        tmp_path, unit=_UNIT_644, config="a: 1\n", kubeconfig=0o644
    )
    snapshot = ((cfg_dir / "config.yaml").read_text(), unit.read_text())
    result, _, _, _ = _run_node(tmp_path)

    assert result.returncode == 0, result.stderr
    assert ((cfg_dir / "config.yaml").read_text(), unit.read_text()) == snapshot
    calls = _systemctl_calls(record)
    assert calls == ["daemon-reload"]
    assert not {"restart", "stop", "start"} & {word for c in calls for word in c.split()}


def test_pve_handler_is_wired_after_apply_with_continue_on_error() -> None:
    """The Proxmox handler is an after_apply script with continue_on_error and 4 env keys."""
    blueprint = yaml.safe_load((BLUEPRINT / "blueprint.yaml").read_text())
    (handler,) = blueprint["providers"]["proxmox"]["events"]["after_apply"]

    assert handler["script"] == "scripts/proxmox/k3s-kubeconfig-mode.sh"
    assert handler["continue_on_error"] is True
    assert set(handler["env"]) == {
        "K3S_SERVER_NAME",
        "K3S_SERVER_IP",
        "K3S_JUMPHOST",
        "K3S_KNOWN_HOSTS",
    }
