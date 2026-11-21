"""Tests for the OCI k3s login user bootstrap (#1575).

Covers the ``k3s-bootstrap`` role and playbook, the ``k3s-bootstrap.sh`` after_apply
handler, the lib helpers and the order of calls in ``k3s-post-terraform.sh``.
Keys and hosts are generic test values.
"""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from infrafoundry.core.config.blueprint_resolver import BlueprintResolver
from infrafoundry.core.config.package_loader import PackageLoader

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_ENVS = REPO_ROOT / "example-config" / "envs"
PACKAGE_DIR = EXAMPLE_ENVS / "oci-k3s" / "k3s-cluster"
BLUEPRINT = REPO_ROOT / "blueprints" / "k3s-cluster"
ROLE = BLUEPRINT / "roles" / "k3s-bootstrap"
PLAYBOOK = BLUEPRINT / "playbooks" / "k3s-bootstrap.yml"
BOOTSTRAP_SCRIPT = BLUEPRINT / "scripts" / "oci" / "k3s-bootstrap.sh"
POST_SCRIPT = BLUEPRINT / "scripts" / "oci" / "k3s-post-terraform.sh"
LIB = BLUEPRINT / "scripts" / "oci" / "k3s-lib.sh"

KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAItest test@example.com"

# Records every call as one numbered file set; ssh failures are per user.
_FAKE_ANSIBLE = """#!/bin/sh
n=$(cat "$RECORD_DIR/ansible_count" 2>/dev/null || echo 0)
n=$((n + 1))
echo "$n" > "$RECORD_DIR/ansible_count"
echo "$@" > "$RECORD_DIR/args$n"
echo "$ANSIBLE_ROLES_PATH" > "$RECORD_DIR/roles_path$n"
prev=""
for arg in "$@"; do
    case "$arg" in
        @*) cp "${arg#@}" "$RECORD_DIR/extra_vars$n.json" ;;
    esac
    [ "$prev" = "-i" ] && cp "$arg" "$RECORD_DIR/inventory$n.yml"
    prev="$arg"
done
exit "${FAKE_ANSIBLE_RC:-0}"
"""

_FAKE_SSH = """#!/bin/sh
for arg in "$@"; do
    case "$arg" in *@*) echo "$arg" >> "$RECORD_DIR/ssh_targets" ;; esac
done
case "$*" in
    *"$SSH_DENY_USER@"*)
        echo "tailscale: tailnet policy does not permit you to SSH to this node" >&2
        exit 255 ;;
esac
exit 0
"""


def _bin(tmp_path: Path, *, ansible: bool = True) -> tuple[Path, Path]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    record = tmp_path / "record"
    record.mkdir()
    stubs = {
        "ssh": _FAKE_SSH,
        "ssh-add": "#!/bin/sh\necho key\n",
        "sleep": "#!/bin/sh\nexit 0\n",
    }
    if ansible:
        stubs["ansible-playbook"] = _FAKE_ANSIBLE
    for name, body in stubs.items():
        stub = bin_dir / name
        stub.write_text(body)
        stub.chmod(0o755)
    return bin_dir, record


def _path(bin_dir: Path, *, ansible: bool = True) -> str:
    base = os.environ["PATH"]
    if not ansible:
        base = ":".join(p for p in base.split(":") if not (Path(p) / "ansible-playbook").exists())
    return f"{bin_dir}:{base}"


def _run_handler(
    tmp_path: Path, env_extra: dict[str, str], *, ansible: bool = True
) -> tuple[subprocess.CompletedProcess[str], Path]:
    bin_dir, record = _bin(tmp_path, ansible=ansible)
    env = {
        "PATH": _path(bin_dir, ansible=ansible),
        "HOME": str(tmp_path),
        "RECORD_DIR": str(record),
        "INFRAFOUNDRY_BLUEPRINT_DIR": str(BLUEPRINT),
        "INFRAFOUNDRY_WARNINGS_FILE": str(tmp_path / "warnings.jsonl"),
        **env_extra,
    }
    result = subprocess.run(
        ["bash", str(BOOTSTRAP_SCRIPT)], env=env, capture_output=True, text=True, check=False
    )
    return result, record


_HANDLER_ENV = {
    "K3S_CONTROL_NAME": "ctl",
    "K3S_WORKER_NAMES": "w0,w1",
    "K3S_TAILNET": "example.net",
    "K3S_SSH_PUBLIC_KEY": KEY,
}


def _run_post(
    tmp_path: Path, *, key: str = KEY, deny_user: str = "none"
) -> tuple[subprocess.CompletedProcess[str], Path]:
    bin_dir, record = _bin(tmp_path)
    env = {
        "PATH": _path(bin_dir),
        "HOME": str(tmp_path),
        "RECORD_DIR": str(record),
        "SSH_DENY_USER": deny_user,
        "INFRAFOUNDRY_VAR_control_name": "ctl",
        "INFRAFOUNDRY_VAR_cluster_name": "c",
        "INFRAFOUNDRY_VAR_ssh_public_key": key,
        "INFRAFOUNDRY_VAR_tailnet": "example.net",
        "INFRAFOUNDRY_VAR_kubeconfig_local_path": str(tmp_path / "kube.yaml"),
        "INFRAFOUNDRY_PACKAGE_VARS": json.dumps({"workers": [{"name": "w1"}]}),
    }
    result = subprocess.run(
        ["bash", str(POST_SCRIPT)], env=env, capture_output=True, text=True, check=False
    )
    return result, record


# --- Inventory user ---


def _inventory_users(tmp_path: Path, user_env: dict[str, str]) -> list[str]:
    out = tmp_path / "inv.yml"
    script = (
        f'source "{LIB}"\nTAILNET=example.net\nCONTROL_NAME=ctl\n'
        "CONTROL_HOST=ctl.example.net\nWORKER_NAMES=(w1)\n"
        f'write_k3s_inventory "{out}"\n'
    )
    env = {"PATH": os.environ["PATH"], **user_env}
    subprocess.run(["bash", "-c", script], env=env, check=True, capture_output=True)
    return re.findall(r"ansible_user: (\S+)", out.read_text())


def test_inventory_defaults_to_ansible(tmp_path: Path) -> None:
    """Every host logs in as ansible unless overridden."""
    assert _inventory_users(tmp_path, {}) == ["ansible", "ansible"]


def test_inventory_user_override(tmp_path: Path) -> None:
    """K3S_INVENTORY_USER overrides the login user (used by the bootstrap)."""
    assert _inventory_users(tmp_path, {"K3S_INVENTORY_USER": "ubuntu"}) == ["ubuntu", "ubuntu"]


# --- k3s-post-terraform.sh ---


def test_post_terraform_bootstraps_as_ubuntu_then_runs_k3s_as_ansible(tmp_path: Path) -> None:
    """Call 1 is the bootstrap playbook as ubuntu, call 2 is k3s.yml as ansible."""
    result, record = _run_post(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    assert (record / "ansible_count").read_text().strip() == "2"
    assert (record / "args1").read_text().strip().endswith(str(PLAYBOOK))
    assert (record / "args2").read_text().strip().endswith(str(BLUEPRINT / "playbooks" / "k3s.yml"))
    assert "ansible_user: ubuntu" in (record / "inventory1.yml").read_text()
    assert "ansible_user: ansible" not in (record / "inventory1.yml").read_text()
    assert "ansible_user: ansible" in (record / "inventory2.yml").read_text()
    assert json.loads((record / "extra_vars1.json").read_text()) == {
        "k3s_bootstrap_ssh_public_keys": [KEY]
    }
    assert (record / "roles_path1").read_text().strip() == str(BLUEPRINT / "roles")


def test_post_terraform_waits_as_ubuntu_then_as_ansible(tmp_path: Path) -> None:
    """Phase 1 connects as ubuntu, the wait after the bootstrap as ansible."""
    result, record = _run_post(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    targets = (record / "ssh_targets").read_text().split()
    users = [t.split("@")[0] for t in targets]
    assert users == ["ubuntu", "ubuntu", "ansible", "ansible"]


def test_post_terraform_policy_denial_for_ansible_stops_before_k3s(tmp_path: Path) -> None:
    """A tailnet policy that only allows ubuntu fails and names the ansible user."""
    result, record = _run_post(tmp_path, deny_user="ansible")

    assert result.returncode != 0
    assert "ansible" in result.stderr
    assert (record / "ansible_count").read_text().strip() == "1"
    assert not (record / "args2").exists()


@pytest.mark.parametrize("key", ["", "not-a-key", f"{KEY}\nssh-rsa injected", f"{KEY}\r"])
def test_post_terraform_rejects_a_bad_key_before_any_call(tmp_path: Path, key: str) -> None:
    """An empty or malformed key fails before ssh or ansible run."""
    result, record = _run_post(tmp_path, key=key.replace("\nssh-rsa injected", "\nbad line"))

    assert result.returncode != 0
    assert "ssh_public_key" in result.stderr
    assert not (record / "ssh_targets").exists()
    assert not (record / "ansible_count").exists()


# --- k3s-bootstrap.sh ---


def test_handler_script_is_executable_in_the_tree() -> None:
    """k3s-bootstrap.sh has the executable bit set."""
    assert os.access(BOOTSTRAP_SCRIPT, os.X_OK)


def test_handler_runs_only_the_bootstrap_playbook(tmp_path: Path) -> None:
    """The handler runs k3s-bootstrap.yml as ubuntu against every node."""
    result, record = _run_handler(tmp_path, _HANDLER_ENV)

    assert result.returncode == 0, result.stderr + result.stdout
    assert (record / "ansible_count").read_text().strip() == "1"
    assert (record / "args1").read_text().strip().endswith(str(PLAYBOOK))
    inventory = yaml.safe_load((record / "inventory1.yml").read_text())
    children = inventory["all"]["children"]
    assert children["k3s_control"]["hosts"]["ctl"]["ansible_host"] == "ctl.example.net"
    assert children["k3s_control"]["hosts"]["ctl"]["ansible_user"] == "ubuntu"
    assert set(children["k3s_workers"]["hosts"]) == {"w0", "w1"}
    assert json.loads((record / "extra_vars1.json").read_text()) == {
        "k3s_bootstrap_ssh_public_keys": [KEY]
    }
    assert (record / "roles_path1").read_text().strip() == str(BLUEPRINT / "roles")


def test_handler_missing_ansible_exits_127(tmp_path: Path) -> None:
    """A missing ansible-playbook is exit 127."""
    result, _ = _run_handler(tmp_path, _HANDLER_ENV, ansible=False)

    assert result.returncode == 127


def test_handler_requires_a_control_name(tmp_path: Path) -> None:
    """Without K3S_CONTROL_NAME the handler fails before ansible."""
    env = {k: v for k, v in _HANDLER_ENV.items() if k != "K3S_CONTROL_NAME"}
    result, record = _run_handler(tmp_path, env)

    assert result.returncode != 0
    assert "K3S_CONTROL_NAME" in result.stderr
    assert not (record / "ansible_count").exists()


def test_handler_rejects_a_bad_key(tmp_path: Path) -> None:
    """A malformed key never reaches ansible."""
    result, record = _run_handler(tmp_path, {**_HANDLER_ENV, "K3S_SSH_PUBLIC_KEY": "nope"})

    assert result.returncode != 0
    assert not (record / "ansible_count").exists()


def test_handler_playbook_failure_keeps_rc_and_writes_a_warning(tmp_path: Path) -> None:
    """A failing playbook keeps its exit code and appends one JSONL warning."""
    result, _ = _run_handler(tmp_path, {**_HANDLER_ENV, "FAKE_ANSIBLE_RC": "4"})

    assert result.returncode == 4
    (line,) = (tmp_path / "warnings.jsonl").read_text().splitlines()
    warning = json.loads(line)
    assert warning["source"] == "k3s-bootstrap"
    assert "ubuntu" in warning["message"]
    assert "ssh rule" in warning["message"]


# --- Blueprint wiring ---


def test_handler_is_first_and_carries_the_key_for_the_example_package() -> None:
    """k3s-bootstrap runs before k3s-dns and gets the key through env."""
    loader = PackageLoader(EXAMPLE_ENVS, blueprint_resolver=BlueprintResolver(EXAMPLE_ENVS))
    _r, events, variables = loader.load_package(PACKAGE_DIR, provider="oci", env_name="oci-k3s")
    names = [h["name"] for h in events["after_apply"]]
    handler = events["after_apply"][0]

    assert names.index("k3s-bootstrap") < names.index("k3s-dns")
    assert names.index("k3s-bootstrap") < names.index("verify-cluster")
    assert handler["continue_on_error"] is True
    assert handler["timeout"] == 600
    assert handler["env"]["K3S_SSH_PUBLIC_KEY"] == variables["ssh_public_key"]
    assert handler["env"]["K3S_CONTROL_NAME"] == "k3s-control"


def test_handler_env_for_an_override_package(tmp_path: Path) -> None:
    """An override package's key and nodes reach the handler env."""
    pkg = tmp_path / "envs" / "test" / "k3s"
    pkg.mkdir(parents=True)
    (pkg / "infrafoundry.yml").write_text(
        "name: k3s\ndescription: bootstrap test\nblueprint: k3s-cluster\nprovider: oci\n"
        "variables:\n  cluster_name: k3s\n  control_name: ctl\n"
        '  image: "ocid1.image.oc1.iad.aaaaaaaa"\n'
        f'  ssh_public_key: "{KEY}"\n  tailnet: "example.net"\n'
        "  workers:\n    - name: w0\n      ocpus: 1\n      memory_gb: 8\n"
    )
    envs = tmp_path / "envs"
    loader = PackageLoader(envs, blueprint_resolver=BlueprintResolver(envs))
    _r, events, _v = loader.load_package(pkg, provider="oci", env_name="test")

    assert events["after_apply"][0]["env"] == {
        "K3S_CONTROL_NAME": "ctl",
        "K3S_WORKER_NAMES": "w0",
        "K3S_TAILNET": "example.net",
        "K3S_SSH_PUBLIC_KEY": KEY,
    }


def test_proxmox_has_no_bootstrap_handler() -> None:
    """The Proxmox variant is unchanged."""
    blueprint = yaml.safe_load((BLUEPRINT / "blueprint.yaml").read_text())

    assert "k3s-bootstrap" not in yaml.safe_dump(blueprint["providers"]["proxmox"])
    assert "after_apply" not in blueprint["providers"]["proxmox"]["events"]


# --- Role safety (static) ---


def test_role_uses_only_safe_builtin_modules() -> None:
    """No service, command, shell or removal tasks; only the allowed builtins."""
    tasks = yaml.safe_load((ROLE / "tasks" / "main.yml").read_text())
    modules = {next(k for k in t if k.startswith("ansible.builtin.")) for t in tasks}

    assert modules == {
        "ansible.builtin.assert",
        "ansible.builtin.user",
        "ansible.builtin.file",
        "ansible.builtin.lineinfile",
        "ansible.builtin.copy",
    }
    assert "state: absent" not in (ROLE / "tasks" / "main.yml").read_text()


def test_role_validates_sudoers_and_keeps_authorized_keys_additive() -> None:
    """The sudoers drop-in is visudo-checked at 0440; keys are added, not replaced."""
    tasks = {t["name"]: t for t in yaml.safe_load((ROLE / "tasks" / "main.yml").read_text())}
    sudo = tasks["Allow passwordless sudo"]["ansible.builtin.copy"]
    keys = tasks["Authorize the SSH public keys"]["ansible.builtin.lineinfile"]
    ssh_dir = tasks["Create the .ssh directory"]["ansible.builtin.file"]

    assert sudo["validate"] == "/usr/sbin/visudo -cf %s"
    assert sudo["mode"] == "0440"
    assert "NOPASSWD:ALL" in sudo["content"]
    assert keys["mode"] == "0600"
    assert "regexp" not in keys
    assert ssh_dir["mode"] == "0700"


def test_playbook_targets_the_cluster_with_become() -> None:
    """The playbook runs the role on every node with become."""
    (play,) = yaml.safe_load(PLAYBOOK.read_text())

    assert play["hosts"] == "k3s_cluster"
    assert play["become"] is True
    assert play["gather_facts"] is False
    assert play["roles"] == ["k3s-bootstrap"]


# --- Real Ansible ---

needs_ansible = pytest.mark.skipif(shutil.which("ansible-playbook") is None, reason="no ansible")


@needs_ansible
def test_playbook_syntax_and_task_list(tmp_path: Path) -> None:
    """ansible accepts the playbook and lists the role's tasks."""
    inventory = tmp_path / "inv.yml"
    inventory.write_text("all:\n  children:\n    k3s_cluster:\n      hosts:\n        n1: {}\n")
    env = {**os.environ, "ANSIBLE_ROLES_PATH": str(BLUEPRINT / "roles")}
    for flag in ("--syntax-check", "--list-tasks"):
        result = subprocess.run(
            ["ansible-playbook", "-i", str(inventory), flag, str(PLAYBOOK)],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr + result.stdout
    assert "Allow passwordless sudo" in result.stdout
