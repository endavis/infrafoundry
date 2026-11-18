"""The routeros-chr blueprint (#1485).

Loads the example consumer through PackageLoader and renders the bootstrap
expect template offline. No Proxmox host, no RouterOS box.

Depends only on files in this repository:
  - blueprints/routeros-chr/                         (the blueprint)
  - example-config/envs/dev/proxmox/chr-test/        (the example consumer)
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from infrafoundry.core.config.blueprint_resolver import BlueprintResolver
from infrafoundry.core.config.package_loader import PackageLoader

REPO_ROOT = Path(__file__).resolve().parents[2]
BLUEPRINT_DIR = REPO_ROOT / "blueprints" / "routeros-chr"
ROLE_DIR = BLUEPRINT_DIR / "roles" / "routeros-bootstrap"
EXAMPLE_ENVS = REPO_ROOT / "example-config" / "envs"
PACKAGE_DIR = EXAMPLE_ENVS / "dev" / "proxmox" / "chr-test"


def _load(package: Path) -> tuple[list[Any], dict[str, Any], dict[str, Any]]:
    loader = PackageLoader(EXAMPLE_ENVS, blueprint_resolver=BlueprintResolver(EXAMPLE_ENVS))
    return loader.load_package(package, provider="proxmox", env_name="dev")


@pytest.fixture
def loaded() -> tuple[list[Any], dict[str, Any], dict[str, Any]]:
    """The example package, loaded through the blueprint resolver."""
    return _load(PACKAGE_DIR)


def _package_with(tmp_path: Path, extra: str) -> list[Any]:
    package = tmp_path / "dev" / "proxmox" / "chr-test"
    package.mkdir(parents=True)
    source = (PACKAGE_DIR / "infrafoundry.yml").read_text()
    (package / "infrafoundry.yml").write_text(source.rstrip("\n") + "\n" + extra)
    resources, _events, _variables = _load(package)
    return resources


def test_example_package_merges_blueprint_defaults(loaded: Any) -> None:
    _resources, _events, variables = loaded

    assert variables["vm_name"] == "chr-test"
    assert variables["vmid"] == 951
    assert variables["image_source"].endswith(".img.zip")
    assert len(variables["image_sha256"]) == 64
    assert variables["mgmt_bridge"] == "vmbr0"
    assert variables["trunk_bridge"] == "vmbr1"


def test_vm_imports_the_zip_with_a_management_and_two_trunk_nics(loaded: Any) -> None:
    resources, _events, _variables = loaded

    [vm] = resources
    assert (vm.provider, vm.type, vm.name) == ("proxmox", "vm", "chr-test")
    config = vm.config
    assert config["disk_image_source"].startswith("https://download.mikrotik.com/")
    assert config["disk_image_source"].endswith(".img.zip")
    assert config["disk_bus"] == "ide"
    assert config["serial"] is True
    assert config["onboot"] is False
    assert config["tags"] == ["routeros", "chr-test"]
    assert config["network"] == [
        {"bridge": "vmbr0", "model": "virtio"},
        {"bridge": "vmbr1", "model": "virtio"},
        {"bridge": "vmbr1", "model": "virtio"},
    ]


def test_trunk_nics_input_sets_the_nic_count(tmp_path: Path) -> None:
    [vm] = _package_with(tmp_path, "  trunk_nics: 3\n")

    assert len(vm.config["network"]) == 4


def test_mgmt_vlan_tags_only_the_first_nic(tmp_path: Path) -> None:
    [vm] = _package_with(tmp_path, "  mgmt_vlan: 20\n")

    network = vm.config["network"]
    assert network[0]["tag"] == 20
    assert all("tag" not in nic for nic in network[1:])


def test_bootstrap_runs_on_create_after_the_vm(loaded: Any) -> None:
    _resources, events, _variables = loaded

    [handler] = events["on_create"]
    assert handler["type"] == "script"
    assert handler["script"].endswith("scripts/routeros-post-terraform.sh")
    assert handler["requires"] == ["chr-test"]
    assert handler["continue_on_error"] is False


def _expect_script(**overrides: Any) -> str:
    defaults = yaml.safe_load((ROLE_DIR / "defaults" / "main.yml").read_text()) | overrides
    env = Environment(loader=FileSystemLoader(ROLE_DIR / "templates"), undefined=StrictUndefined)
    return env.get_template("bootstrap.exp.j2").render(
        routeros_vmid=951, routeros_hostname="chr-test", **defaults
    )


def test_expect_script_logs_in_as_admin_on_the_serial_socket() -> None:
    script = _expect_script()

    assert "spawn socat STDIO,rawer UNIX-CONNECT:/var/run/qemu-server/951.serial0" in script
    assert 'send "admin+ct\\r"' in script
    assert '/system identity set name=\\"chr-test\\"' in script


def test_expect_script_takes_the_password_only_from_the_environment() -> None:
    script = _expect_script()

    assert "$env(ROUTEROS_ADMIN_PASSWORD)" in script
    sends = [script[i : i + 60] for i in range(len(script)) if script.startswith("send -- ", i)]
    assert len(sends) == 2
    assert all("$env(ROUTEROS_ADMIN_PASSWORD)" in s for s in sends)
    # Console output never reaches stdout, so it never reaches Ansible's output.
    assert script.index("log_user 0") < script.index("spawn ")
    assert "log_user 1" not in script


# A fake CHR serial console, run in place of socat. It reproduces what a live
# RouterOS 7.25.1 CHR printed (#1485): the "new password>" line is drawn twice
# before input is read, and a password typed at the shell prompt is echoed back.
FAKE_CONSOLE = r"""
import sys, termios
fd = sys.stdin.fileno()
attrs = termios.tcgetattr(fd)
attrs[3] &= ~termios.ECHO
termios.tcsetattr(fd, termios.TCSANOW, attrs)
inputs = open(sys.argv[1], "w")
def out(text):
    sys.stdout.write(text)
    sys.stdout.flush()
def read():
    line = sys.stdin.readline().rstrip("\r\n")
    inputs.write(line + "\n")
    inputs.flush()
    return line
out("MikroTik 7.25.1\r\nCHR Login: ")
read()
out("\r\nPassword: ")
read()
out("\r\nDo you want to see the software license? [Y/n]: ")
read()
out("\r\nChange your password (Ctrl-C to skip)\r\n\x1b[9999Bnew password> \rnew password> ")
read()
out("*" * 24 + "\r\n\x1b[9999Brepeat new password> ")
read()
out("*" * 24 + "\r\nPassword changed\r\n\x1b[9999B > ")
while True:
    line = read()
    out(line + "\r\n")
    if line == "/quit":
        break
    if line.startswith(":put"):
        out("BOOTSTRAP OK\r\n")
    elif not line.startswith("/"):
        out("expected command name (line 1 column 1)\r\n")
    out("\x1b[9999B > ")
"""


@pytest.mark.skipif(not shutil.which("expect"), reason="expect is not installed")
def test_bootstrap_answers_each_password_prompt_once_and_never_leaks_it(tmp_path: Path) -> None:
    password = "Zq7testSecretValue42xy"  # test fixture, not a real secret
    console = tmp_path / "console.py"
    console.write_text(FAKE_CONSOLE)
    inputs = tmp_path / "inputs.txt"
    log = tmp_path / "bootstrap.log"
    script = _expect_script(routeros_boot_timeout=20)
    spawn = "spawn socat STDIO,rawer UNIX-CONNECT:/var/run/qemu-server/951.serial0"
    assert spawn in script
    script = script.replace(spawn, f"spawn {sys.executable} -I {console} {inputs}")
    script = re.sub(r"(?m)^set logpath .*$", f"set logpath {log}", script)
    script = script.replace("set timeout 60", "set timeout 20")
    exp = tmp_path / "bootstrap.exp"
    exp.write_text(script)

    result = subprocess.run(
        ["expect", "-f", str(exp)],
        env={**os.environ, "ROUTEROS_ADMIN_PASSWORD": password},
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    sent = inputs.read_text().splitlines()
    assert sent.count(password) == 2
    assert sent[3:5] == [password, password]
    assert password not in result.stdout + result.stderr
    assert password not in log.read_text()
    assert "Bootstrap applied" in result.stdout


def test_expect_script_has_no_static_address_by_default() -> None:
    script = _expect_script()

    assert "dhcp-client remove" not in script
    assert "ip address add" not in script
    assert "ip route add" not in script
    assert "/ip service set www disabled=no" in script


def test_expect_script_sets_a_static_address_before_enabling_www() -> None:
    script = _expect_script(routeros_mgmt_ip="192.0.2.241", routeros_mgmt_prefix=24)

    removed = script.index("/ip dhcp-client remove")
    added = script.index("/ip address add address=192.0.2.241/24 interface=ether1")
    assert removed < added < script.index("/ip service set www disabled=no")
    assert "ip route add" not in script


def test_expect_script_adds_the_default_route_with_a_gateway() -> None:
    script = _expect_script(routeros_mgmt_ip="192.0.2.241", routeros_mgmt_gateway="192.0.2.1")

    assert "/ip route add dst-address=0.0.0.0/0 gateway=192.0.2.1" in script


def test_success_marker_is_split_in_the_sent_command() -> None:
    script = _expect_script()

    [sent] = [line for line in script.splitlines() if line.startswith('send ":put')]
    assert "BOOTSTRAP OK" not in sent
    assert 'expect {\n  "BOOTSTRAP OK"' in script


def test_post_terraform_script_refuses_to_run_without_the_password(tmp_path: Path) -> None:
    env = {
        "PATH": os.environ["PATH"],
        "INFRAFOUNDRY_PACKAGE_DIR": str(tmp_path),
        "INFRAFOUNDRY_BLUEPRINT_DIR": str(BLUEPRINT_DIR),
        "INFRAFOUNDRY_VAR_vmid": "951",
        "INFRAFOUNDRY_VAR_vm_name": "chr-test",
        "INFRAFOUNDRY_VAR_target_node": "pve-node1",
        "INFRAFOUNDRY_VAR_pve_host": "192.0.2.13",
    }

    result = subprocess.run(
        ["bash", str(BLUEPRINT_DIR / "scripts" / "routeros-post-terraform.sh")],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "INFRAFOUNDRY_VAR_routeros_admin_password is not set" in result.stderr
    assert not (tmp_path / ".generated-inventory.json").exists()


def test_readiness_probe_sends_no_credentials_and_accepts_only_401() -> None:
    script = (BLUEPRINT_DIR / "scripts" / "routeros-post-terraform.sh").read_text()
    probe = script[script.index('URL="http://') :]

    assert "routeros_admin_password" not in probe
    assert " -u " not in probe
    assert "--user" not in probe
    assert '[ "$code" = "401" ]' in probe


@pytest.mark.parametrize(
    "path",
    [
        BLUEPRINT_DIR / "routeros-bootstrap.yml",
        *sorted((BLUEPRINT_DIR / "roles").rglob("*.yml")),
    ],
    ids=lambda p: str(p.relative_to(BLUEPRINT_DIR)),
)
def test_ansible_yaml_parses(path: Path) -> None:
    assert yaml.safe_load(path.read_text(encoding="utf-8")) is not None


def test_launch_task_hides_the_password_and_passes_it_by_environment() -> None:
    tasks = yaml.safe_load((ROLE_DIR / "tasks" / "main.yml").read_text())

    [launch] = [t for t in tasks if t["name"].startswith("Launch wrapper")]
    assert launch["no_log"] is True
    assert "routeros_admin_password" in launch["environment"]["ROUTEROS_ADMIN_PASSWORD"]
