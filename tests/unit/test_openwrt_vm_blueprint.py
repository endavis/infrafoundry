"""The openwrt-vm blueprint (#1493).

Loads the example consumer through PackageLoader and renders the bootstrap
expect template offline. No Proxmox host, no OpenWrt box.

Depends only on files in this repository:
  - blueprints/openwrt-vm/                         (the blueprint)
  - example-config/envs/dev/proxmox/openwrt-test/  (the example consumer)
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
BLUEPRINT_DIR = REPO_ROOT / "blueprints" / "openwrt-vm"
ROLE_DIR = BLUEPRINT_DIR / "roles" / "openwrt-bootstrap"
EXAMPLE_ENVS = REPO_ROOT / "example-config" / "envs"
PACKAGE_DIR = EXAMPLE_ENVS / "dev" / "proxmox" / "openwrt-test"
KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIExampleKeyNotARealKeyDoNotUse0000000"


def _load(package: Path) -> tuple[list[Any], dict[str, Any], dict[str, Any]]:
    loader = PackageLoader(EXAMPLE_ENVS, blueprint_resolver=BlueprintResolver(EXAMPLE_ENVS))
    return loader.load_package(package, provider="proxmox", env_name="dev")


@pytest.fixture
def loaded() -> tuple[list[Any], dict[str, Any], dict[str, Any]]:
    """The example package, loaded through the blueprint resolver."""
    return _load(PACKAGE_DIR)


def _package_with(tmp_path: Path, extra: str) -> list[Any]:
    package = tmp_path / "dev" / "proxmox" / "openwrt-test"
    package.mkdir(parents=True)
    source = (PACKAGE_DIR / "infrafoundry.yml").read_text()
    (package / "infrafoundry.yml").write_text(source.rstrip("\n") + "\n" + extra)
    resources, _events, _variables = _load(package)
    return resources


def test_example_package_merges_blueprint_defaults(loaded: Any) -> None:
    _resources, _events, variables = loaded

    assert variables["vm_name"] == "openwrt-test"
    assert variables["vmid"] == 952
    assert variables["image_source"].endswith(".img.gz")
    assert re.fullmatch(r"[0-9a-f]{64}|", variables["image_sha256"])
    assert variables["mgmt_bridge"] == "vmbr0"
    assert variables["wan_bridge"] == "vmbr1"
    assert variables["lan_dhcp"] is False


def test_vm_imports_the_gz_with_a_lan_and_a_wan_nic(loaded: Any) -> None:
    resources, _events, _variables = loaded

    [vm] = resources
    assert (vm.provider, vm.type, vm.name) == ("proxmox", "vm", "openwrt-test")
    config = vm.config
    assert config["disk_image_source"].startswith("https://downloads.openwrt.org/")
    assert config["disk_image_source"].endswith(".img.gz")
    assert config["disk_bus"] == "ide"
    assert config["serial"] is True
    assert config["onboot"] is False
    assert config["tags"] == ["openwrt", "openwrt-test"]
    assert config["network"] == [
        {"bridge": "vmbr0", "model": "virtio"},
        {"bridge": "vmbr1", "model": "virtio"},
    ]


def test_empty_wan_bridge_gives_a_single_nic(tmp_path: Path) -> None:
    [vm] = _package_with(tmp_path, '  wan_bridge: ""\n')

    assert vm.config["network"] == [{"bridge": "vmbr0", "model": "virtio"}]


def test_mgmt_vlan_tags_only_the_lan_nic(tmp_path: Path) -> None:
    [vm] = _package_with(tmp_path, "  mgmt_vlan: 20\n")

    network = vm.config["network"]
    assert network[0]["tag"] == 20
    assert all("tag" not in nic for nic in network[1:])


def test_bootstrap_runs_on_create_after_the_vm(loaded: Any) -> None:
    _resources, events, _variables = loaded

    [handler] = events["on_create"]
    assert handler["type"] == "script"
    assert handler["script"].endswith("scripts/openwrt-post-terraform.sh")
    assert handler["requires"] == ["openwrt-test"]
    assert handler["continue_on_error"] is False


def _expect_script(**overrides: Any) -> str:
    defaults = yaml.safe_load((ROLE_DIR / "defaults" / "main.yml").read_text())
    values = {
        "openwrt_vmid": 952,
        "openwrt_hostname": "openwrt-test",
        "openwrt_ssh_key": KEY,
        "openwrt_mgmt_ip": "192.0.2.242",
        **defaults,
        **overrides,
    }
    env = Environment(loader=FileSystemLoader(ROLE_DIR / "templates"), undefined=StrictUndefined)
    return env.get_template("bootstrap.exp.j2").render(**values)


def test_expect_script_spawns_on_the_serial_socket_with_console_output_off() -> None:
    script = _expect_script()

    assert "spawn socat STDIO,rawer UNIX-CONNECT:/var/run/qemu-server/952.serial0" in script
    assert script.index("log_user 0") < script.index("spawn ")
    assert "log_user 1" not in script


def test_expect_script_turns_password_login_off_and_reloads_the_network_last() -> None:
    script = _expect_script()

    assert "PasswordAuth=off" in script
    assert "RootPasswordAuth=off" in script
    assert "uci set network.lan.ipaddr='192.0.2.242'" in script
    assert "uci set network.lan.netmask='255.255.255.0'" in script
    assert script.index('run "uci commit"') < script.index("/etc/init.d/network reload")
    assert script.rindex("run ") == script.index('run "/etc/init.d/network reload"')


def test_expect_script_turns_lan_services_off_by_default() -> None:
    script = _expect_script()

    for line in (
        "uci set dhcp.lan.ignore=1",
        "uci set dhcp.lan.ra=disabled",
        "uci set dhcp.lan.dhcpv6=disabled",
        "uci set dhcp.lan.ndp=disabled",
        "/etc/init.d/odhcpd restart",
    ):
        assert line in script
    assert script.index("dhcp.lan.ndp=disabled") < script.index('run "uci commit"')


def test_expect_script_keeps_lan_services_with_lan_dhcp() -> None:
    script = _expect_script(openwrt_lan_dhcp=True)

    assert "dhcp.lan.ignore" not in script
    assert "dhcp.lan.ra=" not in script
    assert "dhcp.lan.dhcpv6=" not in script
    assert "dhcp.lan.ndp=" not in script


def test_expect_script_sets_gateway_and_dns_only_when_given() -> None:
    plain = _expect_script()
    full = _expect_script(openwrt_mgmt_gateway="192.0.2.1", openwrt_mgmt_dns="192.0.2.53")

    assert "network.lan.gateway" not in plain
    assert "network.lan.dns" not in plain
    assert "uci set network.lan.gateway='192.0.2.1'" in full
    assert "uci set network.lan.dns='192.0.2.53'" in full


def test_success_marker_is_split_in_the_sent_command() -> None:
    script = _expect_script()

    [sent] = [line for line in script.splitlines() if line.startswith('send "echo')]
    assert "BOOTSTRAP OK" not in sent
    assert 'expect {\n  "BOOTSTRAP OK"' in script


def test_key_comment_is_dropped_before_the_template() -> None:
    tasks = yaml.safe_load((ROLE_DIR / "tasks" / "main.yml").read_text())

    [step] = [t for t in tasks if "set_fact" in str(t) or "ansible.builtin.set_fact" in t]
    assert step["ansible.builtin.set_fact"]["openwrt_ssh_key"] == (
        "{{ openwrt_ssh_public_key.split()[:2] | join(' ') }}"
    )
    key = yaml.safe_load(
        (PACKAGE_DIR / "infrafoundry.yml").read_text(),
    )["variables"]["ssh_public_key"]
    assert " ".join(key.split()[:2]) == KEY
    assert "example-key" not in _expect_script()


# A fake OpenWrt serial console, run in place of socat. It draws the "press
# Enter" line twice before reading, answers every command with an exit-code
# marker and prints an unsolicited kernel-style line between commands.
FAKE_CONSOLE = r"""
import sys, termios
fd = sys.stdin.fileno()
attrs = termios.tcgetattr(fd)
attrs[3] &= ~termios.ECHO
termios.tcsetattr(fd, termios.TCSANOW, attrs)
closed_once = sys.argv[3] if len(sys.argv) > 3 else ""
drop_once = sys.argv[4] if len(sys.argv) > 4 else ""
import os
if closed_once:
    if not os.path.exists(closed_once):
        open(closed_once, "w").close()
        sys.exit(0)
inputs = open(sys.argv[1], "w")
fail_on = sys.argv[2]
PROMPT = "root@OpenWrt:~# "
def out(text):
    sys.stdout.write(text)
    sys.stdout.flush()
def read():
    line = sys.stdin.readline().rstrip("\r\n")
    inputs.write(line + "\n")
    inputs.flush()
    return line
out("[    1.000000] boot\r\nPlease press Enter to activate this console.\r\n")
out("Please press Enter to activate this console.\r\n")
read()
out("\r\n" + PROMPT)
while True:
    line = read()
    if line == "" and drop_once and not os.path.exists(drop_once):
        open(drop_once, "w").close()
        continue
    out(line + "\r\n")
    if line.startswith("echo \"BOOTSTRAP"):
        out("BOOTSTRAP OK\r\n" + PROMPT)
        continue
    code = 1 if fail_on and fail_on in line else 0
    out("[   12.345678] kernel: noise\r\n@@RC=%d@@\r\n" % code + PROMPT)
"""


CHUNK = re.compile(r"^printf '%s' '([^']*)' >> /etc/dropbear/authorized_keys\.new")


def _key_from_chunks(lines: list[str]) -> str:
    return "".join(m.group(1) for line in lines if (m := CHUNK.match(line)))


def _run_bootstrap(
    tmp_path: Path, fail_on: str, *, close_first: bool = False, drop_first_enter: bool = False
) -> tuple[subprocess.CompletedProcess[str], Path]:
    console = tmp_path / "console.py"
    console.write_text(FAKE_CONSOLE)
    inputs = tmp_path / "inputs.txt"
    log = tmp_path / "bootstrap.log"
    script = _expect_script(openwrt_boot_timeout=20)
    spawn = "spawn socat STDIO,rawer UNIX-CONNECT:/var/run/qemu-server/952.serial0"
    assert spawn in script
    closed_once = tmp_path / "closed-once" if close_first else "{}"
    dropped_once = tmp_path / "dropped-once" if drop_first_enter else ""
    script = script.replace(
        spawn,
        f"spawn {sys.executable} -I {console} {inputs} {{{fail_on}}} {closed_once} {dropped_once}",
    )
    script = re.sub(r"(?m)^set logpath .*$", f"set logpath {log}", script)
    exp = tmp_path / "bootstrap.exp"
    exp.write_text(script)
    result = subprocess.run(
        ["expect", "-f", str(exp)], capture_output=True, text=True, timeout=60, check=False
    )
    return result, inputs


@pytest.mark.skipif(not shutil.which("expect"), reason="expect is not installed")
def test_bootstrap_waits_for_boot_and_runs_every_command(tmp_path: Path) -> None:
    result, inputs = _run_bootstrap(tmp_path, "")

    assert result.returncode == 0, result.stdout + result.stderr
    sent = inputs.read_text().splitlines()
    # One Enter activates the console; one more draws a fresh prompt once boot
    # output has gone quiet. Redraws of the activation message send nothing.
    assert sent[:2] == ["", ""]
    assert sent.count("") == 2
    # Nothing is changed before procd reports that init is complete.
    assert "init complete" in sent[2]
    assert sent[3].startswith("mkdir -p /etc/dropbear")
    assert _key_from_chunks(sent) == KEY
    assert any(line.startswith("mv /etc/dropbear/authorized_keys.new ") for line in sent)
    assert any("RootPasswordAuth=off" in line for line in sent)
    assert any(line.startswith("uci commit") for line in sent)
    assert "Bootstrap applied" in result.stdout
    assert "kernel: noise" not in result.stdout


@pytest.mark.skipif(not shutil.which("expect"), reason="expect is not installed")
def test_bootstrap_fails_when_a_command_returns_non_zero(tmp_path: Path) -> None:
    result, _inputs = _run_bootstrap(tmp_path, "uci commit")

    assert result.returncode != 0
    assert "ERROR: command failed" in result.stdout
    assert "Bootstrap applied" not in result.stdout


def test_post_terraform_script_refuses_to_run_without_the_key(tmp_path: Path) -> None:
    env = {
        "PATH": os.environ["PATH"],
        "INFRAFOUNDRY_PACKAGE_DIR": str(tmp_path),
        "INFRAFOUNDRY_BLUEPRINT_DIR": str(BLUEPRINT_DIR),
        "INFRAFOUNDRY_VAR_vmid": "952",
        "INFRAFOUNDRY_VAR_vm_name": "openwrt-test",
        "INFRAFOUNDRY_VAR_target_node": "pve-node1",
        "INFRAFOUNDRY_VAR_pve_host": "192.0.2.13",
        "INFRAFOUNDRY_VAR_mgmt_ip": "192.0.2.242",
    }

    result = subprocess.run(
        ["bash", str(BLUEPRINT_DIR / "scripts" / "openwrt-post-terraform.sh")],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "INFRAFOUNDRY_VAR_ssh_public_key is not set" in result.stderr
    assert not (tmp_path / ".generated-inventory.json").exists()


def test_readiness_probe_reads_only_the_ssh_banner() -> None:
    script = (BLUEPRINT_DIR / "scripts" / "openwrt-post-terraform.sh").read_text()
    probe = script[script.index("# The probe") :]

    assert "ssh -i" not in probe
    assert " -i " not in probe
    assert "private" not in probe.lower()
    assert '"SSH-"' in probe


@pytest.mark.parametrize(
    "path",
    [
        BLUEPRINT_DIR / "openwrt-bootstrap.yml",
        *sorted((BLUEPRINT_DIR / "roles").rglob("*.yml")),
    ],
    ids=lambda p: str(p.relative_to(BLUEPRINT_DIR)),
)
def test_ansible_yaml_parses(path: Path) -> None:
    assert yaml.safe_load(path.read_text(encoding="utf-8")) is not None


@pytest.mark.skipif(not shutil.which("expect"), reason="expect is not installed")
def test_bootstrap_reconnects_when_the_console_closes_at_once(tmp_path: Path) -> None:
    # The serial socket can exist before QEMU accepts on it; socat then hits EOF.
    result, inputs = _run_bootstrap(tmp_path, "", close_first=True)

    assert (tmp_path / "closed-once").exists()
    assert result.returncode == 0, result.stdout + result.stderr
    sent = inputs.read_text().splitlines()
    assert sent.count("") == 2
    assert any(line.startswith("uci commit") for line in sent)
    assert "Bootstrap applied" in result.stdout


def test_bootstrap_fails_clearly_when_the_console_closes_mid_command() -> None:
    script = _expect_script()
    assert 'eof { fail "Serial console closed while running: $cmd" }' in script
    assert 'eof { fail "Serial console closed before the bootstrap marker" }' in script


def test_a_long_key_is_sent_in_short_chunks_and_length_checked() -> None:
    # The serial console drops characters from a 700+ character line (measured
    # with a 4096-bit RSA key), so no console line may carry the whole key.
    long_key = "ssh-rsa " + "A" * 700
    script = _expect_script(openwrt_ssh_key=long_key)
    sent = re.findall(r'(?m)^\s*run "(.*)"$', script)
    assert sent, "no run lines rendered"
    assert max(len(line) for line in sent) < 200
    chunks = [line.replace("\\[", "[").replace("\\]", "]") for line in sent]
    assert _key_from_chunks(chunks) == long_key
    assert any(f"-eq {len(long_key) + 1}" in line for line in sent)


@pytest.mark.skipif(not shutil.which("expect"), reason="expect is not installed")
def test_bootstrap_presses_enter_again_when_the_first_one_is_dropped(tmp_path: Path) -> None:
    # An Enter sent while procd still sets up the console can vanish (measured).
    result, inputs = _run_bootstrap(tmp_path, "", drop_first_enter=True)

    assert (tmp_path / "dropped-once").exists()
    assert result.returncode == 0, result.stdout + result.stderr
    sent = inputs.read_text().splitlines()
    assert sent[:3] == ["", "", ""]
    assert "init complete" in sent[3]
    assert "Bootstrap applied" in result.stdout
