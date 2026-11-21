"""Pinned SSH host keys in the Proxmox blueprints and their scripts (#1581).

Renders the example packages to check that every VM opts in, then runs the post-terraform
scripts with a stubbed ``ssh`` to check that VM connections use only the pinned
``known_hosts`` file, that the jumphost hop stays strict, and that a missing, malformed or
mismatched key stops the script at once.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import pytest

from infrafoundry.core.config.blueprint_resolver import BlueprintResolver
from infrafoundry.core.config.package_loader import PackageLoader

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_ENVS = REPO_ROOT / "example-config" / "envs"
BLUEPRINTS = REPO_ROOT / "blueprints"
AIQUM_SCRIPT = BLUEPRINTS / "aiqum" / "scripts" / "aiqum-post-terraform.sh"
CC_SCRIPT = BLUEPRINTS / "console-connector" / "scripts" / "console-connector-post-terraform.sh"
K3S_DIR = BLUEPRINTS / "k3s-cluster" / "scripts" / "proxmox"
K3S_SCRIPT = K3S_DIR / "k3s-post-terraform.sh"

PUBLIC_A = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIExampleSentinelPublicKey0"
PUBLIC_B = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIExampleSentinelPublicKey1"
KNOWN_HOSTS_LINES = [f"vm-01,192.0.2.10 {PUBLIC_A}", f"vm-02,192.0.2.11 {PUBLIC_B}"]
KNOWN_HOSTS = ";".join(KNOWN_HOSTS_LINES)


@pytest.fixture
def loader() -> PackageLoader:
    """PackageLoader pointed at the real example-config envs/ directory."""
    return PackageLoader(EXAMPLE_ENVS, blueprint_resolver=BlueprintResolver(EXAMPLE_ENVS))


class TestRenderedResources:
    def test_aiqum_vm_opts_in(self, loader: PackageLoader) -> None:
        resources, _e, variables = loader.load_package(
            EXAMPLE_ENVS / "dev" / "proxmox" / "aiqum", provider="proxmox", env_name="dev"
        )
        (vm,) = [r for r in resources if r.type == "vm"]
        assert vm.config["ssh_host_key"] == {"address": variables["ip_address"]}

    def test_console_connector_vm_opts_in(self, loader: PackageLoader) -> None:
        resources, _e, variables = loader.load_package(
            EXAMPLE_ENVS / "dev" / "proxmox" / "console-connector",
            provider="proxmox",
            env_name="dev",
        )
        (vm,) = [r for r in resources if r.type == "vm"]
        assert vm.config["ssh_host_key"] == {"address": variables["ip_address"]}

    def test_k3s_server_and_every_agent_opt_in(self, loader: PackageLoader) -> None:
        resources, _e, variables = loader.load_package(
            EXAMPLE_ENVS / "dev" / "proxmox" / "k3s-cluster", provider="proxmox", env_name="dev"
        )
        addresses = {
            r.name: r.config["ssh_host_key"]["address"] for r in resources if r.type == "vm"
        }
        expected = {variables["server_name"]: variables["server_ip"]}
        expected.update({a["name"]: a["ip"] for a in variables["agents"]})
        assert len(expected) > 1
        assert addresses == expected

    def test_oci_k3s_control_and_every_worker_opt_in(self, loader: PackageLoader) -> None:
        resources, _e, variables = loader.load_package(
            EXAMPLE_ENVS / "oci-k3s" / "k3s-cluster", provider="oci", env_name="oci-k3s"
        )
        addresses = {
            r.name: r.config["ssh_host_key"]["address"] for r in resources if r.type == "instance"
        }
        tailnet = variables["tailnet"]
        names = [variables["control_name"], *(w["name"] for w in variables["workers"])]
        assert len(names) > 1
        assert addresses == {n: f"{n}.{tailnet}" for n in names}
        assert variables["ssh_known_hosts"] == ""

    def test_known_hosts_is_empty_until_keys_are_recorded(self, loader: PackageLoader) -> None:
        _r, _e, variables = loader.load_package(
            EXAMPLE_ENVS / "dev" / "proxmox" / "aiqum", provider="proxmox", env_name="dev"
        )
        assert variables["ssh_known_hosts"] == ""


OCI_DIR = BLUEPRINTS / "k3s-cluster" / "scripts" / "oci"
ALL_SCRIPTS = [
    AIQUM_SCRIPT,
    CC_SCRIPT,
    *sorted(K3S_DIR.glob("*.sh")),
    *sorted(OCI_DIR.glob("*.sh")),
]


@pytest.mark.parametrize("script", ALL_SCRIPTS, ids=lambda p: p.name)
def test_scripts_do_not_disable_host_key_checking(script: Path) -> None:
    text = script.read_text(encoding="utf-8")
    assert "StrictHostKeyChecking=no" not in text
    assert "UserKnownHostsFile=/dev/null" not in text
    assert "ANSIBLE_HOST_KEY_CHECKING=False" not in text


_SSH_STUB = """#!/bin/sh
printf '%s\\n' "$*" >> "$RECORD/ssh_calls"
n=$(wc -l < "$RECORD/ssh_calls")
for a in "$@"; do
    case "$a" in
    UserKnownHostsFile=*)
        f="${a#UserKnownHostsFile=}"
        if [ -f "$f" ]; then cp "$f" "$RECORD/used_known_hosts.$n"; fi ;;
    esac
done
case "$*" in
*mktemp*) cat > "$RECORD/staged"; echo /tmp/staged-hk ;;
*"echo ok"*|*"echo ready"*)
    if [ -z "$FAKE_SSH_OK" ]; then echo "Host key verification failed." >&2; exit 255; fi ;;
esac
"""


def _run(
    script: Path, tmp_path: Path, env_extra: dict[str, str]
) -> tuple[subprocess.CompletedProcess[str], Path]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    record = tmp_path / "record"
    record.mkdir()
    for name, body in {
        "ssh": _SSH_STUB,
        "scp": "#!/bin/sh\nexit 0\n",
        "ssh-add": "#!/bin/sh\necho key\n",
        "sleep": "#!/bin/sh\nexit 0\n",
    }.items():
        stub = bin_dir / name
        stub.write_text(body)
        stub.chmod(0o755)
    env = {
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "HOME": str(tmp_path),
        "RECORD": str(record),
        "TMPDIR": str(tmp_path),
        **env_extra,
    }
    result = subprocess.run(
        ["bash", str(script)], env=env, capture_output=True, text=True, check=False, timeout=60
    )
    return result, record


def _calls(record: Path) -> list[str]:
    path = record / "ssh_calls"
    return path.read_text().splitlines() if path.exists() else []


def _vm_script_env(script: Path, **overrides: str) -> dict[str, str]:
    variables = {
        "vm_name": "vm-01",
        "ip_address": "192.0.2.10",
        "ssh_user": "ansible",
        "jumphost": "",
        "ssh_known_hosts": KNOWN_HOSTS,
        "aiqum_url_base": "https://web.example.com/aiqum",
        "console_agent_url_base": "https://web.example.com/cc",
        "console_agent_installer": "installer",
        "console_agent_sha256": "0" * 64,
        **overrides,
    }
    return {"INFRAFOUNDRY_PACKAGE_VARS": json.dumps(variables)}


VM_SCRIPTS = [
    pytest.param(AIQUM_SCRIPT, id="aiqum"),
    pytest.param(CC_SCRIPT, id="console-connector"),
]


@pytest.mark.parametrize("script", VM_SCRIPTS)
class TestVmScripts:
    def test_direct_connection_uses_only_the_pinned_file(
        self, script: Path, tmp_path: Path
    ) -> None:
        result, record = _run(script, tmp_path, _vm_script_env(script))

        (call, *_) = _calls(record)
        assert "StrictHostKeyChecking=yes" in call
        assert "GlobalKnownHostsFile=/dev/null" in call
        assert re.search(r"UserKnownHostsFile=\S+", call)
        assert "ansible@192.0.2.10" in call
        assert (record / "used_known_hosts.1").read_text().splitlines() == KNOWN_HOSTS_LINES
        assert result.returncode == 1

    def test_jumphost_hop_is_strict_and_inner_hop_uses_the_staged_file(
        self, script: Path, tmp_path: Path
    ) -> None:
        env = _vm_script_env(script, jumphost="ansible@jump.example")

        result, record = _run(script, tmp_path, env)

        stage, call, cleanup = _calls(record)
        assert "StrictHostKeyChecking=yes" in stage
        assert "ansible@jump.example" in stage
        assert "UserKnownHostsFile" not in stage
        assert (record / "staged").read_text().splitlines() == KNOWN_HOSTS_LINES
        outer, _, inner = call.partition(" ansible@jump.example ")
        assert "StrictHostKeyChecking=yes" in outer
        assert "UserKnownHostsFile" not in outer
        assert "-o StrictHostKeyChecking=yes -o UserKnownHostsFile=/tmp/staged-hk" in inner
        assert "GlobalKnownHostsFile=/dev/null" in inner
        assert "rm -f '/tmp/staged-hk'" in cleanup
        assert "ansible@jump.example" in cleanup
        assert result.returncode == 1

    def test_a_key_mismatch_stops_at_once_and_names_the_vm(
        self, script: Path, tmp_path: Path
    ) -> None:
        result, record = _run(script, tmp_path, _vm_script_env(script))

        assert result.returncode == 1
        assert "vm-01" in result.stderr
        assert "ssh_host_keys.vm-01" in result.stderr
        assert "--regenerate vm-01" in result.stderr
        assert len(_calls(record)) == 1

    @pytest.mark.parametrize(
        "value",
        ["", "vm-01,192.0.2.10 ssh-rsa AAAAB3Nza", "not a known hosts line", f"{KNOWN_HOSTS};"],
    )
    def test_empty_or_malformed_known_hosts_exits_before_any_ssh(
        self, script: Path, tmp_path: Path, value: str
    ) -> None:
        result, record = _run(script, tmp_path, _vm_script_env(script, ssh_known_hosts=value))

        assert result.returncode == 1
        assert "ssh_known_hosts" in result.stderr
        assert _calls(record) == []

    def test_the_staged_and_local_files_are_removed(self, script: Path, tmp_path: Path) -> None:
        _run(script, tmp_path, _vm_script_env(script, jumphost="ansible@jump.example"))

        assert list(tmp_path.glob("tmp.*")) == []


def test_console_connector_cert_fetch_goes_through_the_pinned_channel() -> None:
    """The agent certificate comes over ``remote_cmd``, so only over the verified channel."""
    text = CC_SCRIPT.read_text()
    assert 'remote_cmd "${ip_address}" "openssl s_client' in text
    assert (
        'VM_SSH_OPTS="-o StrictHostKeyChecking=yes -o UserKnownHostsFile=${VM_KNOWN_HOSTS}' in text
    )
    assert 'SSH="ssh ${VM_SSH_OPTS}' in text


def test_aiqum_variable_export_quotes_values_and_skips_non_scalars(tmp_path: Path) -> None:
    """The ``eval`` block shell-quotes scalars and ignores lists and bad names."""
    text = AIQUM_SCRIPT.read_text()
    match = re.search(r'^eval "\$\(python3 -c "\n(.*?)\n"\)"$', text, re.S | re.M)
    assert match
    snippet = match.group(0)
    variables = {
        "spaced": "a b; id $(false) 'q' \"d\"",
        "number": 5,
        "listed": ["x"],
        "bad-name": "x",
    }
    script = f'{snippet}\nprintf "%s|%s|%s" "$spaced" "$number" "${{listed:-unset}}"\n'
    result = subprocess.run(
        ["bash", "-c", script],
        env={
            "PATH": os.environ["PATH"],
            "INFRAFOUNDRY_PACKAGE_VARS": json.dumps(variables),
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "a b; id $(false) 'q' \"d\"|5|unset"


class TestK3sScripts:
    @staticmethod
    def _env(known_hosts: str, jumphost: str = "") -> dict[str, str]:
        return {
            "INFRAFOUNDRY_VAR_server_ip": "198.51.100.1",
            "INFRAFOUNDRY_VAR_server_name": "srv",
            "INFRAFOUNDRY_VAR_jumphost": jumphost,
            "INFRAFOUNDRY_VAR_k3s_server_args": "--disable traefik",
            "INFRAFOUNDRY_VAR_cluster_name": "c",
            "INFRAFOUNDRY_VAR_kubeconfig_dir": "~/.kube",
            "INFRAFOUNDRY_VAR_ssh_known_hosts": known_hosts,
            "INFRAFOUNDRY_PACKAGE_VARS": json.dumps({"agents": []}),
        }

    def test_a_key_mismatch_stops_at_once_and_names_the_node(self, tmp_path: Path) -> None:
        known = f"srv,198.51.100.1 {PUBLIC_A}"
        result, record = _run(K3S_SCRIPT, tmp_path, self._env(known))

        assert result.returncode == 1
        assert "srv" in result.stderr
        assert "ssh_host_keys.srv" in result.stderr
        (call,) = _calls(record)
        assert "StrictHostKeyChecking=yes" in call
        assert (record / "used_known_hosts.1").read_text().strip() == known

    def test_jumphost_stages_the_file_and_cleans_up(self, tmp_path: Path) -> None:
        known = f"srv,198.51.100.1 {PUBLIC_A}"
        result, record = _run(K3S_SCRIPT, tmp_path, self._env(known, "ansible@jump.example"))

        stage, call, cleanup = _calls(record)
        assert "StrictHostKeyChecking=yes" in stage
        assert (record / "staged").read_text().strip() == known
        assert "UserKnownHostsFile=/tmp/staged-hk" in call
        assert "rm -f '/tmp/staged-hk'" in cleanup
        assert result.returncode == 1

    @pytest.mark.parametrize("value", ["", "srv,198.51.100.1 ssh-rsa AAAA"])
    def test_missing_or_malformed_keys_exit_before_any_ssh(
        self, tmp_path: Path, value: str
    ) -> None:
        result, record = _run(K3S_SCRIPT, tmp_path, self._env(value))

        assert result.returncode == 1
        assert "foundry secrets host-keys" in result.stderr
        assert _calls(record) == []


_OCI_ANSIBLE = """#!/bin/sh
n=$(cat "$RECORD/ansible_count" 2>/dev/null || echo 0)
n=$((n + 1))
echo "$n" > "$RECORD/ansible_count"
echo "$ANSIBLE_HOST_KEY_CHECKING" > "$RECORD/hkc$n"
echo "$ANSIBLE_SSH_COMMON_ARGS" > "$RECORD/args$n"
"""
_OCI_KNOWN = f"ctl,ctl.example.net {PUBLIC_A};w1,w1.example.net {PUBLIC_B}"


def _run_oci(
    script: Path, tmp_path: Path, env_extra: dict[str, str], *, ssh_ok: bool = True
) -> tuple[subprocess.CompletedProcess[str], Path]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True)
    record = tmp_path / "record"
    record.mkdir(parents=True)
    for name, body in {
        "ssh": _SSH_STUB,
        "ssh-add": "#!/bin/sh\necho key\n",
        "sleep": "#!/bin/sh\nexit 0\n",
        "ansible-playbook": _OCI_ANSIBLE,
    }.items():
        stub = bin_dir / name
        stub.write_text(body)
        stub.chmod(0o755)
    env = {
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "HOME": str(tmp_path),
        "RECORD": str(record),
        "TMPDIR": str(tmp_path),
        "INFRAFOUNDRY_BLUEPRINT_DIR": str(BLUEPRINTS / "k3s-cluster"),
        "INFRAFOUNDRY_WARNINGS_FILE": str(tmp_path / "warnings.jsonl"),
        **({"FAKE_SSH_OK": "1"} if ssh_ok else {}),
        **env_extra,
    }
    result = subprocess.run(
        ["bash", str(script)], env=env, capture_output=True, text=True, check=False, timeout=60
    )
    return result, record


def _oci_post_env(known_hosts: str) -> dict[str, str]:
    return {
        "INFRAFOUNDRY_VAR_control_name": "ctl",
        "INFRAFOUNDRY_VAR_cluster_name": "c",
        "INFRAFOUNDRY_VAR_tailnet": "example.net",
        "INFRAFOUNDRY_VAR_ssh_public_key": "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAItest a@b.example",
        "INFRAFOUNDRY_VAR_kubeconfig_local_path": "/tmp/kube.yaml",
        "INFRAFOUNDRY_VAR_ssh_known_hosts": known_hosts,
        "INFRAFOUNDRY_PACKAGE_VARS": json.dumps({"workers": [{"name": "w1"}]}),
    }


_OCI_HANDLERS = [
    ("k3s-bootstrap.sh", {"K3S_SSH_PUBLIC_KEY": "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAItest a@b"}),
    ("k3s-kubeconfig-mode.sh", {}),
    ("k3s-dns.sh", {"K3S_DNS_NAMESERVERS": "192.0.2.53"}),
]


class TestOciK3sScripts:
    def test_post_terraform_is_strict_everywhere(self, tmp_path: Path) -> None:
        result, record = _run_oci(
            OCI_DIR / "k3s-post-terraform.sh", tmp_path, _oci_post_env(_OCI_KNOWN)
        )

        assert result.returncode == 0, result.stderr
        calls = _calls(record)
        assert calls
        for call in calls:
            assert "StrictHostKeyChecking=yes" in call
            assert "GlobalKnownHostsFile=/dev/null" in call
        used = {p.read_text().strip() for p in record.glob("used_known_hosts.*")}
        assert used == {"\n".join(_OCI_KNOWN.split(";"))}
        assert int((record / "ansible_count").read_text()) == 2
        for n in (1, 2):
            assert (record / f"hkc{n}").read_text().strip() == "True"
            args = (record / f"args{n}").read_text()
            assert "StrictHostKeyChecking=yes" in args
            assert "UserKnownHostsFile=" in args
            assert "/dev/null" not in args.replace("GlobalKnownHostsFile=/dev/null", "")

    def test_the_temporary_file_is_removed_on_exit(self, tmp_path: Path) -> None:
        _run_oci(OCI_DIR / "k3s-post-terraform.sh", tmp_path, _oci_post_env(_OCI_KNOWN))
        assert not [p for p in tmp_path.glob("tmp.*") if p.is_file()]

    @pytest.mark.parametrize("value", ["", "ctl,ctl.example.net ssh-rsa AAAA"])
    def test_missing_or_malformed_keys_exit_before_any_call(
        self, tmp_path: Path, value: str
    ) -> None:
        result, record = _run_oci(OCI_DIR / "k3s-post-terraform.sh", tmp_path, _oci_post_env(value))

        assert result.returncode == 1
        assert "foundry secrets host-keys" in result.stderr
        assert _calls(record) == []
        assert not (record / "ansible_count").exists()

    def test_a_key_mismatch_stops_at_once_and_names_the_node(self, tmp_path: Path) -> None:
        result, record = _run_oci(
            OCI_DIR / "k3s-post-terraform.sh",
            tmp_path,
            _oci_post_env(_OCI_KNOWN),
            ssh_ok=False,
        )

        assert result.returncode == 1
        assert "ssh_host_keys.ctl" in result.stderr
        assert "--regenerate ctl" in result.stderr
        assert len(_calls(record)) == 1

    @pytest.mark.parametrize(("name", "extra"), _OCI_HANDLERS, ids=lambda v: str(v)[:20])
    def test_handlers_refuse_without_keys_and_run_strict_with_them(
        self, tmp_path: Path, name: str, extra: dict[str, str]
    ) -> None:
        base = {
            "K3S_CONTROL_NAME": "ctl",
            "K3S_WORKER_NAMES": "w1",
            "K3S_TAILNET": "example.net",
            **extra,
        }
        denied, record = _run_oci(OCI_DIR / name, tmp_path / "a", base | {"K3S_KNOWN_HOSTS": ""})
        assert denied.returncode != 0
        assert not (record / "ansible_count").exists()
        warnings = (tmp_path / "a" / "warnings.jsonl").read_text()
        assert "foundry secrets host-keys" in warnings

        ok, record = _run_oci(
            OCI_DIR / name, tmp_path / "b", base | {"K3S_KNOWN_HOSTS": _OCI_KNOWN}
        )
        assert ok.returncode == 0, ok.stderr
        assert (record / "hkc1").read_text().strip() == "True"
        assert "StrictHostKeyChecking=yes" in (record / "args1").read_text()

    def test_verify_cluster_without_kubectl_or_keys_skips_with_a_warning(
        self, tmp_path: Path
    ) -> None:
        # Hide kubectl without hiding its neighbours: on CI it sits in /usr/bin beside bash,
        # so dropping that directory would drop bash too. Link everything else instead.
        shadow = tmp_path / "no-kubectl"
        shadow.mkdir()
        path_dirs: list[str] = []
        for entry in os.environ["PATH"].split(os.pathsep):
            directory = Path(entry)
            if not (directory / "kubectl").exists():
                path_dirs.append(entry)
                continue
            for tool in directory.iterdir():
                if tool.name != "kubectl" and not (shadow / tool.name).exists():
                    (shadow / tool.name).symlink_to(tool)
            if str(shadow) not in path_dirs:
                path_dirs.append(str(shadow))
        env = {
            "PATH": os.pathsep.join(path_dirs),
            "KUBECONFIG": str(tmp_path / "kube.yaml"),
            "K3S_CONTROL_NAME": "ctl",
            "K3S_TAILNET": "example.net",
            "K3S_KNOWN_HOSTS": "",
        }
        (tmp_path / "kube.yaml").write_text("x")
        result, record = _run_oci(OCI_DIR / "verify-cluster.sh", tmp_path / "w", env)
        assert result.returncode == 0, result.stderr
        assert _calls(record) == []
        assert "no pinned SSH host keys" in (tmp_path / "w" / "warnings.jsonl").read_text()
