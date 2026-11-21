"""Tests for the k3s-cluster cluster DNS isolation (#1554).

Covers the OCI blueprint wiring, the ``k3s-dns`` role and playbook, the
``k3s-dns.sh`` after_apply script and the changes to ``k3s-post-terraform.sh``.
Addresses use RFC 5737 ranges and ``example.net``.
"""

import grp
import json
import os
import pwd
import re
import shutil
import subprocess
import textwrap
from pathlib import Path

import jinja2
import pytest
import yaml

from infrafoundry.core.config.blueprint_resolver import BlueprintResolver
from infrafoundry.core.config.package_loader import PackageLoader

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_ENVS = REPO_ROOT / "example-config" / "envs"
PACKAGE_DIR = EXAMPLE_ENVS / "oci-k3s" / "k3s-cluster"
BLUEPRINT = REPO_ROOT / "blueprints" / "k3s-cluster"
ROLE = BLUEPRINT / "roles" / "k3s-dns"
DNS_SCRIPT = BLUEPRINT / "scripts" / "oci" / "k3s-dns.sh"
POST_SCRIPT = BLUEPRINT / "scripts" / "oci" / "k3s-post-terraform.sh"

_FAKE_ANSIBLE = """#!/bin/sh
echo "$@" > "$RECORD_DIR/args"
echo "$ANSIBLE_ROLES_PATH" > "$RECORD_DIR/roles_path"
prev=""
for arg in "$@"; do
    case "$arg" in
        @*) cp "${arg#@}" "$RECORD_DIR/extra_vars.json" ;;
    esac
    [ "$prev" = "-i" ] && cp "$arg" "$RECORD_DIR/inventory.yml"
    prev="$arg"
done
exit "${FAKE_ANSIBLE_RC:-0}"
"""


@pytest.fixture
def loader() -> PackageLoader:
    """PackageLoader pointed at the real example-config envs/ directory."""
    return PackageLoader(EXAMPLE_ENVS, blueprint_resolver=BlueprintResolver(EXAMPLE_ENVS))


def _write_package(tmp_path: Path, extra_vars: str = "") -> tuple[Path, PackageLoader]:
    envs = tmp_path / "envs"
    pkg = envs / "test" / "k3s"
    pkg.mkdir(parents=True)
    (pkg / "infrafoundry.yml").write_text(
        textwrap.dedent(
            """\
            name: k3s
            description: "k3s dns test"
            blueprint: k3s-cluster
            provider: oci
            variables:
              cluster_name: k3s
              control_name: ctl
              image: "ocid1.image.oc1.iad.aaaaaaaa"
              ssh_public_key: "ssh-rsa AAAA"
              tailnet: "example.net"
              workers:
                - name: w0
                  ocpus: 1
                  memory_gb: 8
                - name: w1
                  ocpus: 1
                  memory_gb: 8
            """
        )
        + extra_vars
    )
    return pkg, PackageLoader(envs, blueprint_resolver=BlueprintResolver(envs))


# --- Blueprint wiring ---


def test_oci_dns_defaults(loader: PackageLoader) -> None:
    """The OCI defaults use the VCN resolver and derive the search domain."""
    _r, _e, variables = loader.load_package(PACKAGE_DIR, provider="oci", env_name="oci-k3s")

    assert variables["k3s_dns_nameservers"] == ["169.254.169.254"]
    assert variables["k3s_dns_search"] == []


def test_proxmox_blueprint_is_not_wired() -> None:
    """The Proxmox variant has no DNS inputs and no k3s-dns handler."""
    blueprint = yaml.safe_load((BLUEPRINT / "blueprint.yaml").read_text())
    proxmox = blueprint["providers"]["proxmox"]

    assert "k3s_dns_nameservers" not in {i["name"] for i in proxmox["inputs"]}
    assert "k3s-dns" not in {h["name"] for h in proxmox["events"].get("after_apply", [])}


def test_after_apply_env_for_the_example_package(loader: PackageLoader) -> None:
    """The k3s-dns handler gets every value through its env block."""
    _r, events, _v = loader.load_package(PACKAGE_DIR, provider="oci", env_name="oci-k3s")
    handler = next(h for h in events["after_apply"] if h["name"] == "k3s-dns")

    assert handler["name"] == "k3s-dns"
    assert handler["timeout"] == 900
    assert handler["continue_on_error"] is True
    assert handler["env"] == {
        "K3S_CONTROL_NAME": "k3s-control",
        "K3S_WORKER_NAMES": "k3s-worker-0,k3s-worker-1",
        "K3S_TAILNET": "your-tailnet.ts.net",
        "K3S_KNOWN_HOSTS": "",
        "K3S_DNS_NAMESERVERS": "169.254.169.254",
        "K3S_DNS_SEARCH": "",
        "K3S_VCN_DNS_LABEL": "k3svcn",
    }


def test_after_apply_env_for_an_override_package(tmp_path: Path) -> None:
    """Package overrides reach the handler env."""
    pkg, loader = _write_package(
        tmp_path,
        "  k3s_dns_nameservers: ['192.0.2.53', '192.0.2.54']\n"
        "  k3s_dns_search: ['a.example.net', 'b.example.net']\n"
        "  vcn_dns_label: lbl\n",
    )
    _r, events, _v = loader.load_package(pkg, provider="oci", env_name="test")

    handler = next(h for h in events["after_apply"] if h["name"] == "k3s-dns")
    assert handler["env"] == {
        "K3S_CONTROL_NAME": "ctl",
        "K3S_WORKER_NAMES": "w0,w1",
        "K3S_TAILNET": "example.net",
        "K3S_KNOWN_HOSTS": "",
        "K3S_DNS_NAMESERVERS": "192.0.2.53,192.0.2.54",
        "K3S_DNS_SEARCH": "a.example.net,b.example.net",
        "K3S_VCN_DNS_LABEL": "lbl",
    }


# --- Role templates ---


def _render_resolv(servers: list[str], search: list[str]) -> str:
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(ROLE / "templates"),
        undefined=jinja2.StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=False,
    )
    return env.get_template("resolv.conf.j2").render(
        k3s_dns_nameservers=servers, k3s_dns_search=search
    )


def test_resolv_conf_with_search_and_several_nameservers() -> None:
    """Every nameserver gets a line, then one search line."""
    out = _render_resolv(["192.0.2.1", "192.0.2.2"], ["a.example.net", "b.example.net"])

    assert "nameserver 192.0.2.1\nnameserver 192.0.2.2\n" in out
    assert "search a.example.net b.example.net\n" in out
    assert "Managed by InfraFoundry" in out


def test_resolv_conf_without_search_has_no_search_line() -> None:
    """An empty search list writes no search line."""
    out = _render_resolv(["192.0.2.1"], [])

    assert "nameserver 192.0.2.1" in out
    assert "search" not in out


def test_dropin_points_the_kubelet_at_the_resolv_conf() -> None:
    """The drop-in sets resolv-conf under config.yaml.d/."""
    tasks = (ROLE / "tasks" / "main.yml").read_text()

    assert "config.yaml.d/50-infrafoundry-dns.yaml" in tasks
    assert "resolv-conf: {{ k3s_dns_config_dir }}/resolv.conf" in tasks


# --- Static safety checks ---


def test_dns_playbook_never_uses_the_install_roles() -> None:
    """k3s-dns.yml only runs the k3s-dns role."""
    plays = yaml.safe_load((BLUEPRINT / "playbooks" / "k3s-dns.yml").read_text())
    used = {r for play in plays for r in play.get("roles", [])}

    assert used == {"k3s-dns"}
    text = (BLUEPRINT / "playbooks" / "k3s-dns.yml").read_text()
    assert "k3s-server" not in text
    assert "k3s-agent" not in text.replace("k3s-agent\n", "").replace(
        "k3s_dns_service: k3s-agent", ""
    )


def test_role_has_no_install_or_uninstall_steps() -> None:
    """The role never installs or removes k3s, nor touches rancher paths."""
    text = "\n".join(
        line
        for p in ROLE.rglob("*")
        if p.is_file() and p.suffix != ".md"
        for line in p.read_text().splitlines()
        if not line.lstrip().startswith("#")
    )
    for forbidden in ("get.k3s.io", "uninstall", "state: absent", "/var/lib/rancher", "rm -"):
        assert forbidden not in text, forbidden
    assert re.search(r"role:\s*k3s-(server|agent)", text) is None


def test_k3s_playbook_ends_with_the_dns_import() -> None:
    """On create the DNS play runs after the install plays."""
    plays = yaml.safe_load((BLUEPRINT / "playbooks" / "k3s.yml").read_text())

    assert plays[-1] == {"import_playbook": "k3s-dns.yml"}


def test_restarts_are_gated_on_a_change() -> None:
    """The service restart and CoreDNS restart only run on a change."""
    tasks = yaml.safe_load((ROLE / "tasks" / "main.yml").read_text())
    restart = next(t for t in tasks if t["name"].startswith("Restart k3s"))
    assert "k3s_dns_changed" in str(restart["when"])

    plays = yaml.safe_load((BLUEPRINT / "playbooks" / "k3s-dns.yml").read_text())
    coredns = [t for t in plays[-1]["tasks"] if "coredns" in t["name"].lower() and "when" in t]
    assert len(coredns) == 2
    assert all("k3s_dns_any_changed" in t["when"] for t in coredns)


def test_dns_script_is_executable_in_the_tree() -> None:
    """k3s-dns.sh has the executable bit set."""
    assert os.access(DNS_SCRIPT, os.X_OK)


# --- k3s-dns.sh ---


def _run_dns(
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
    # Keep real ansible-playbook off the PATH when the stub is absent.
    base_path = ":".join(
        p for p in os.environ["PATH"].split(":") if not (Path(p) / "ansible-playbook").exists()
    )
    env = {
        "PATH": f"{bin_dir}:{base_path}",
        "HOME": str(tmp_path),
        "RECORD_DIR": str(record),
        "INFRAFOUNDRY_BLUEPRINT_DIR": str(BLUEPRINT),
        "INFRAFOUNDRY_WARNINGS_FILE": str(tmp_path / "warnings.jsonl"),
        **env_extra,
    }
    result = subprocess.run(
        ["bash", str(DNS_SCRIPT)], env=env, capture_output=True, text=True, check=False
    )
    return result, record


_PINNED = (
    "ctl,ctl.example.net ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAItest;"
    "w0,w0.example.net ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAItest"
)

_BASE_ENV = {
    "K3S_CONTROL_NAME": "ctl",
    "K3S_WORKER_NAMES": "w0,w1",
    "K3S_TAILNET": "example.net",
    "K3S_KNOWN_HOSTS": _PINNED,
    "K3S_DNS_NAMESERVERS": "169.254.169.254",
    "K3S_DNS_SEARCH": "",
    "K3S_VCN_DNS_LABEL": "lbl",
}


def test_dns_script_runs_only_the_dns_playbook(tmp_path: Path) -> None:
    """Only k3s-dns.yml runs, with the right inventory and a derived search domain."""
    result, record = _run_dns(tmp_path, _BASE_ENV)

    assert result.returncode == 0, result.stderr + result.stdout
    args = (record / "args").read_text()
    assert args.strip().endswith(str(BLUEPRINT / "playbooks" / "k3s-dns.yml"))
    assert "k3s.yml" not in args.replace("k3s-dns.yml", "")
    inventory = yaml.safe_load((record / "inventory.yml").read_text())
    children = inventory["all"]["children"]
    assert children["k3s_control"]["hosts"]["ctl"]["ansible_host"] == "ctl.example.net"
    assert set(children["k3s_workers"]["hosts"]) == {"w0", "w1"}
    assert json.loads((record / "extra_vars.json").read_text()) == {
        "k3s_dns_nameservers": ["169.254.169.254"],
        "k3s_dns_search": ["lbl.oraclevcn.com"],
    }
    assert (record / "roles_path").read_text().strip() == str(BLUEPRINT / "roles")


def test_dns_script_explicit_search_overrides_the_derived_one(tmp_path: Path) -> None:
    """An explicit search list wins over the label default."""
    env = {**_BASE_ENV, "K3S_DNS_SEARCH": "a.example.net,b.example.net"}
    result, record = _run_dns(tmp_path, env)

    assert result.returncode == 0, result.stderr
    assert json.loads((record / "extra_vars.json").read_text())["k3s_dns_search"] == [
        "a.example.net",
        "b.example.net",
    ]


def test_dns_script_disabled_exits_zero_without_ansible(tmp_path: Path) -> None:
    """No nameservers: exit 0 and never reach ansible-playbook."""
    result, record = _run_dns(tmp_path, {**_BASE_ENV, "K3S_DNS_NAMESERVERS": ""})

    assert result.returncode == 0
    assert "disabled" in result.stdout
    assert not (record / "args").exists()


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("K3S_DNS_NAMESERVERS", "192.0.2.1\nnameserver 192.0.2.66"),
        ("K3S_DNS_NAMESERVERS", "not-an-ip"),
        ("K3S_DNS_NAMESERVERS", "192.0.2.1,192.0.2.2,192.0.2.3,192.0.2.4"),
        ("K3S_DNS_SEARCH", "evil.example.net\noptions ndots:1"),
        ("K3S_DNS_SEARCH", "bad domain.example.net"),
    ],
)
def test_dns_script_rejects_injected_values(tmp_path: Path, key: str, value: str) -> None:
    """Bad nameservers or search domains never reach ansible."""
    result, record = _run_dns(tmp_path, {**_BASE_ENV, key: value})

    assert result.returncode != 0
    assert "ERROR" in result.stderr
    assert not (record / "args").exists()


def test_dns_script_missing_ansible_exits_127(tmp_path: Path) -> None:
    """A missing ansible-playbook is exit 127."""
    result, _ = _run_dns(tmp_path, _BASE_ENV, ansible=False)

    assert result.returncode == 127


def test_dns_script_requires_a_control_name(tmp_path: Path) -> None:
    """Without K3S_CONTROL_NAME the script fails before ansible."""
    env = {k: v for k, v in _BASE_ENV.items() if k != "K3S_CONTROL_NAME"}
    result, record = _run_dns(tmp_path, env)

    assert result.returncode != 0
    assert "K3S_CONTROL_NAME" in result.stderr
    assert not (record / "args").exists()


def test_dns_script_playbook_failure_writes_a_warning(tmp_path: Path) -> None:
    """A failing playbook keeps its exit code and appends a JSONL warning."""
    result, _ = _run_dns(tmp_path, {**_BASE_ENV, "FAKE_ANSIBLE_RC": "4"})

    assert result.returncode == 4
    (line,) = (tmp_path / "warnings.jsonl").read_text().splitlines()
    warning = json.loads(line)
    assert warning["source"] == "k3s-dns"
    assert "coredns" in warning["message"]


# --- k3s-post-terraform.sh ---

_GOLDEN_INVENTORY = """\
all:
  children:
    k3s_control:
      hosts:
        ctl:
          ansible_host: ctl.example.net
          ansible_user: ansible
    k3s_workers:
      hosts:
        w1:
          ansible_host: w1.example.net
          ansible_user: ansible
    k3s_cluster:
      children:
        k3s_control: {}
        k3s_workers: {}
      vars:
        cluster_name: c
        k3s_version: ""
        k3s_server_args: ""
        k3s_oci_firewall_fix: true
        k3s_vcn_cidr: "192.0.2.0/24"
        kubeconfig_local_path: "KUBE"
"""


def _run_post(tmp_path: Path, package_vars: dict[str, object]) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    record = tmp_path / "record"
    record.mkdir()
    stubs = {
        "ssh": "#!/bin/sh\nexit 0\n",
        "ssh-add": "#!/bin/sh\necho key\n",
        "sleep": "#!/bin/sh\nexit 0\n",
        "ansible-playbook": _FAKE_ANSIBLE,
    }
    for name, body in stubs.items():
        stub = bin_dir / name
        stub.write_text(body)
        stub.chmod(0o755)
    env = {
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "HOME": str(tmp_path),
        "RECORD_DIR": str(record),
        "INFRAFOUNDRY_VAR_control_name": "ctl",
        "INFRAFOUNDRY_VAR_cluster_name": "c",
        "INFRAFOUNDRY_VAR_ssh_public_key": (
            "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAItest test@example.com"
        ),
        "INFRAFOUNDRY_VAR_tailnet": "example.net",
        "INFRAFOUNDRY_VAR_ssh_known_hosts": _PINNED,
        "INFRAFOUNDRY_VAR_kubeconfig_local_path": str(tmp_path / "kube.yaml"),
        "INFRAFOUNDRY_PACKAGE_VARS": json.dumps({"workers": [{"name": "w1"}], **package_vars}),
    }
    result = subprocess.run(
        ["bash", str(POST_SCRIPT)], env=env, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr + result.stdout
    return record


def test_post_terraform_inventory_is_byte_identical(tmp_path: Path) -> None:
    """Moving the writer into the shared lib did not change the on_create inventory."""
    record = _run_post(tmp_path, {})

    expected = _GOLDEN_INVENTORY.replace("KUBE", str(tmp_path / "kube.yaml"))
    assert (record / "inventory.yml").read_text() == expected


def test_post_terraform_passes_dns_vars_before_the_playbook(tmp_path: Path) -> None:
    """-e @file comes before the playbook, which stays the last argument."""
    record = _run_post(
        tmp_path,
        {"k3s_dns_nameservers": ["192.0.2.53"], "k3s_dns_search": [], "vcn_dns_label": "lbl"},
    )

    args = (record / "args").read_text().split()
    assert args[-1] == str(BLUEPRINT / "playbooks" / "k3s.yml")
    assert args[args.index("-e") + 1].startswith("@")
    assert json.loads((record / "extra_vars.json").read_text()) == {
        "k3s_dns_nameservers": ["192.0.2.53"],
        "k3s_dns_search": ["lbl.oraclevcn.com"],
    }


def test_post_terraform_without_dns_keys_disables_the_step(tmp_path: Path) -> None:
    """No DNS keys in the package vars means an empty nameserver list."""
    record = _run_post(tmp_path, {})

    assert json.loads((record / "extra_vars.json").read_text()) == {
        "k3s_dns_nameservers": [],
        "k3s_dns_search": [],
    }


# --- Real Ansible ---

needs_ansible = pytest.mark.skipif(shutil.which("ansible-playbook") is None, reason="no ansible")


def _role_playbook(tmp_path: Path, extra: str = "") -> tuple[Path, Path]:
    play = tmp_path / "play.yml"
    play.write_text(
        "- hosts: all\n  gather_facts: false\n  connection: local\n"
        "  vars:\n    k3s_dns_nameservers: ['192.0.2.53']\n    k3s_dns_search: [a.example.net]\n"
        f"{extra}  roles:\n    - k3s-dns\n"
    )
    inv = tmp_path / "inv.ini"
    inv.write_text("localhost ansible_connection=local\n")
    return play, inv


def _ansible(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    play, inv = _role_playbook(tmp_path)
    return subprocess.run(
        ["ansible-playbook", "-i", str(inv), str(play), *args],
        env={
            **os.environ,
            "ANSIBLE_ROLES_PATH": str(BLUEPRINT / "roles"),
            "ANSIBLE_LOCAL_TEMP": str(tmp_path / "ansible-tmp"),
            "ANSIBLE_HOME": str(tmp_path / "ansible-home"),
        },
        capture_output=True,
        text=True,
        check=False,
    )


@needs_ansible
def test_real_ansible_lists_the_dns_tasks(tmp_path: Path) -> None:
    """The role and the DNS playbook parse and list their tasks."""
    result = _ansible(tmp_path, "--list-tasks")
    assert result.returncode == 0, result.stderr + result.stdout
    assert "Write the cluster resolv.conf" in result.stdout

    listed = subprocess.run(
        [
            "ansible-playbook",
            "-i",
            str(tmp_path / "inv.ini"),
            str(BLUEPRINT / "playbooks" / "k3s-dns.yml"),
            "--list-tasks",
        ],
        env={
            **os.environ,
            "ANSIBLE_ROLES_PATH": str(BLUEPRINT / "roles"),
            "ANSIBLE_LOCAL_TEMP": str(tmp_path / "ansible-tmp"),
            "ANSIBLE_HOME": str(tmp_path / "ansible-home"),
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert listed.returncode == 0, listed.stderr + listed.stdout
    assert "Restart CoreDNS" in listed.stdout


@needs_ansible
def test_real_ansible_missing_marker_fails_without_installing(tmp_path: Path) -> None:
    """A missing k3s binary fails with the never-installs message and writes nothing."""
    config_dir = tmp_path / "rancher"
    result = _ansible(
        tmp_path,
        "-e",
        f"k3s_dns_install_marker={tmp_path / 'no-k3s'}",
        "-e",
        f"k3s_dns_config_dir={config_dir}",
    )

    assert result.returncode != 0
    assert "never installs k3s" in result.stdout + result.stderr
    assert not config_dir.exists()


@needs_ansible
def test_real_ansible_empty_nameservers_skip_the_role(tmp_path: Path) -> None:
    """An empty nameserver list ends the host before any file is written."""
    config_dir = tmp_path / "rancher"
    result = _ansible(
        tmp_path,
        "-e",
        '{"k3s_dns_nameservers": []}',
        "-e",
        f"k3s_dns_config_dir={config_dir}",
        "-e",
        f"k3s_dns_install_marker={tmp_path / 'no-k3s'}",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert not config_dir.exists()


@needs_ansible
def test_real_ansible_second_run_changes_nothing(tmp_path: Path) -> None:
    """With the files already in place nothing changes and the restart is skipped."""
    config_dir = tmp_path / "rancher"
    marker = tmp_path / "k3s"
    marker.write_text("")
    extra = [
        "-e",
        f"k3s_dns_install_marker={marker}",
        "-e",
        f"k3s_dns_config_dir={config_dir}",
        "-e",
        "k3s_dns_service=infrafoundry-test-nonexistent",
        "-e",
        f"k3s_dns_file_owner={pwd.getpwuid(os.getuid()).pw_name}",
        "-e",
        f"k3s_dns_file_group={grp.getgrgid(os.getgid()).gr_name}",
    ]
    config_dir.mkdir()
    (config_dir / "config.yaml.d").mkdir()
    (config_dir / "resolv.conf").write_text(_render_resolv(["192.0.2.53"], ["a.example.net"]))
    (config_dir / "config.yaml.d" / "50-infrafoundry-dns.yaml").write_text(
        f"# Managed by InfraFoundry (k3s-dns role)\nresolv-conf: {config_dir}/resolv.conf\n"
    )
    # Match the modes the role sets, so only content could count as a change.
    for path in (config_dir, config_dir / "config.yaml.d"):
        path.chmod(0o755)
    for path in (
        config_dir / "resolv.conf",
        config_dir / "config.yaml.d" / "50-infrafoundry-dns.yaml",
    ):
        path.chmod(0o644)
    result = _ansible(tmp_path, *extra)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "changed=0" in result.stdout


# --- Worker node name (#1556) ---


def test_worker_wait_uses_the_discovered_node_name_not_the_inventory_name() -> None:
    """The worker wait targets the registered node name, never inventory_hostname."""
    tasks = yaml.safe_load((ROLE / "tasks" / "main.yml").read_text())
    by_name = {task["name"]: task for task in tasks}
    wait = by_name["Wait for the node to be Ready (worker)"]
    assert "inventory_hostname" not in wait["ansible.builtin.command"]
    assert "k3s_dns_node_name.stdout" in wait["ansible.builtin.command"]
    lookup = by_name["Find the k3s node name (worker)"]
    assert lookup["register"] == "k3s_dns_node_name"
    assert "delegate_to" not in lookup
    assert lookup["when"] == wait["when"]


def _run_worker(tmp_path: Path, node_config: str | None) -> str:
    """Run the role as a worker against localhost; return the recorded k3s args."""
    config_dir = tmp_path / "rancher"
    (config_dir / "config.yaml.d").mkdir(parents=True)
    if node_config is not None:
        (config_dir / "config.yaml.d" / "10-node.yaml").write_text(node_config)
    stub = tmp_path / "k3s"
    stub.write_text('#!/bin/sh\necho "$@" >> "$RECORD_FILE"\n')
    stub.chmod(0o755)
    record = tmp_path / "record"
    play, inv = _role_playbook(tmp_path)
    result = subprocess.run(
        [
            "ansible-playbook",
            "-i",
            str(inv),
            str(play),
            "-e",
            f"k3s_dns_install_marker={stub}",
            "-e",
            f"k3s_dns_config_dir={config_dir}",
            "-e",
            "k3s_control_host=localhost",
            "-e",
            f"k3s_dns_file_owner={pwd.getpwuid(os.getuid()).pw_name}",
            "-e",
            f"k3s_dns_file_group={grp.getgrgid(os.getgid()).gr_name}",
            "--skip-tags",
            "k3s_dns_restart",
        ],
        env={
            **os.environ,
            "RECORD_FILE": str(record),
            "ANSIBLE_ROLES_PATH": str(BLUEPRINT / "roles"),
            "ANSIBLE_LOCAL_TEMP": str(tmp_path / "ansible-tmp"),
            "ANSIBLE_HOME": str(tmp_path / "ansible-home"),
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return record.read_text()


@needs_ansible
def test_real_ansible_worker_waits_on_the_hostname_not_the_inventory_name(tmp_path: Path) -> None:
    """Without a node-name setting the wait uses the machine hostname."""
    recorded = _run_worker(tmp_path, None)
    hostname = subprocess.run(["hostname"], capture_output=True, text=True, check=True).stdout
    assert f"node/{hostname.strip()} " in recorded


@needs_ansible
def test_real_ansible_worker_waits_on_a_configured_node_name(tmp_path: Path) -> None:
    """A node-name in config.yaml.d wins over the hostname and the inventory name."""
    recorded = _run_worker(tmp_path, 'node-name: "w0-vnic"\n')
    assert "node/w0-vnic " in recorded
    assert "node/localhost " not in recorded
