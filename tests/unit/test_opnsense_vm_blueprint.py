"""The opnsense-vm blueprint (#1094).

Loads the example consumer through PackageLoader and renders the bootstrap
templates offline. No Proxmox host, no OPNsense box.

Depends only on files in this repository:
  - blueprints/opnsense-vm/                          (the blueprint)
  - example-config/envs/dev/proxmox/fw-test/   (the example consumer)
"""

from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from infrafoundry.core.config.blueprint_resolver import BlueprintResolver
from infrafoundry.core.config.package_loader import PackageLoader

REPO_ROOT = Path(__file__).resolve().parents[2]
BLUEPRINT_DIR = REPO_ROOT / "blueprints" / "opnsense-vm"
TEMPLATES = BLUEPRINT_DIR / "roles" / "opnsense-bootstrap" / "templates"
EXAMPLE_ENVS = REPO_ROOT / "example-config" / "envs"
PACKAGE_DIR = EXAMPLE_ENVS / "dev" / "proxmox" / "fw-test"

VALUES = {
    "hostname": "fw-test",
    "domain": "lab.local",
    "root_password": "pw-'quoted\"",
    "api_key": "key123",
    "api_secret": "secret-456",
    "wan_ip": "172.20.10.250",
    "wan_prefix": "24",
    "lan_ip": "172.20.99.1",
    "lan_prefix": "24",
    "api_allow_cidr": "172.20.10.0/24",
}


@pytest.fixture
def loaded() -> tuple[list[Any], dict[str, Any], dict[str, Any]]:
    """The example package, loaded through the blueprint resolver."""
    resolver = BlueprintResolver(EXAMPLE_ENVS)
    loader = PackageLoader(EXAMPLE_ENVS, blueprint_resolver=resolver)
    resources, events, variables = loader.load_package(
        PACKAGE_DIR, provider="proxmox", env_name="dev"
    )
    return resources, events, variables


def test_example_package_merges_blueprint_defaults(loaded: Any) -> None:
    _resources, _events, variables = loaded

    assert variables["vm_name"] == "fw-test"
    assert variables["vmid"] == 950
    assert variables["target_node"] == "node3"
    assert variables["wan_bridge"] == "vmbr0"
    assert variables["wan_vlan"] == 10
    assert variables["lan_bridge"] == "vmbr1"
    assert variables["image_source"].endswith("-nano-amd64.img.bz2")


def test_vm_imports_the_nano_image_with_lan_then_wan_nics(loaded: Any) -> None:
    resources, _events, _variables = loaded

    [vm] = resources
    assert (vm.provider, vm.type, vm.name) == ("proxmox", "vm", "fw-test")
    config = vm.config
    assert config["disk_image_source"].startswith("https://pkg.opnsense.org/releases/")
    assert "disk_image_sha256" not in config  # empty image_sha256 skips the check
    assert config["serial"] is True
    assert config["onboot"] is False
    assert config["vmid"] == 950
    assert config["tags"] == ["opnsense", "fw-test"]
    assert config["network"] == [
        {"bridge": "vmbr1", "model": "e1000"},
        {"bridge": "vmbr0", "model": "e1000", "tag": 10},
    ]


def test_bootstrap_runs_on_create_after_the_vm(loaded: Any) -> None:
    _resources, events, _variables = loaded

    [handler] = events["on_create"]
    assert handler["type"] == "script"
    assert handler["script"].endswith("scripts/opnsense-post-terraform.sh")
    assert handler["requires"] == ["fw-test"]
    assert handler["continue_on_error"] is False


def _ansible_like_env() -> Environment:
    env = Environment(loader=FileSystemLoader(TEMPLATES), undefined=StrictUndefined)
    env.filters["to_json"] = json.dumps
    env.filters["b64encode"] = lambda s: base64.b64encode(s.encode()).decode()
    return env


def test_bootstrap_php_carries_the_values_as_base64_json() -> None:
    php = (
        _ansible_like_env()
        .get_template("bootstrap.php.j2")
        .render(opnsense_bootstrap_values=VALUES)
    )

    [encoded] = re.findall(r"base64_decode\('([A-Za-z0-9+/=]+)'\)", php)
    assert json.loads(base64.b64decode(encoded)) == VALUES
    # Secrets appear only inside the base64 blob.
    assert "secret-456" not in php
    assert "pw-" not in php


@pytest.mark.parametrize(
    "line",
    [
        "require_once('script/load_phalcon.php');",
        "$root->password = password_hash($v['root_password'], PASSWORD_BCRYPT, ['cost' => 11]);",
        "$root->apikeys = $v['api_key'] . '|' . crypt($v['api_secret'], '$6$$');",
        "unset($wan->blockpriv);",
        "unset($wan->blockbogons);",
        "$destination->addChild('network', 'wanip');",
        "$destination->addChild('port', '443');",
        "$cfg->dnsmasq->enable = '0';",
        "unset($cfg->dnsmasq->dhcp_ranges[0]);",
        "Config::getInstance()->save();",
        'echo "BOOTSTRAP OK\\n";',
    ],
)
def test_bootstrap_php_makes_the_expected_edits(line: str) -> None:
    php = (
        _ansible_like_env()
        .get_template("bootstrap.php.j2")
        .render(opnsense_bootstrap_values=VALUES)
    )

    assert line in php


def test_bootstrap_php_removes_every_dhcp_range_before_saving() -> None:
    php = (
        _ansible_like_env()
        .get_template("bootstrap.php.j2")
        .render(opnsense_bootstrap_values=VALUES)
    )

    # A single unset would leave all but the first range; the loop runs until none remain.
    assert "while (isset($cfg->dnsmasq->dhcp_ranges[0])) {" in php
    assert php.index("dhcp_ranges") < php.index("Config::getInstance()->save();")


@pytest.mark.skipif(shutil.which("php") is None, reason="php is not installed")
def test_bootstrap_php_is_valid_php(tmp_path: Path) -> None:
    script = tmp_path / "bootstrap.php"
    script.write_text(
        _ansible_like_env()
        .get_template("bootstrap.php.j2")
        .render(opnsense_bootstrap_values=VALUES)
    )

    subprocess.run(["php", "-l", str(script)], check=True, capture_output=True)


def _expect_script(**overrides: Any) -> str:
    defaults_file = BLUEPRINT_DIR / "roles" / "opnsense-bootstrap" / "defaults" / "main.yml"
    import yaml

    defaults = yaml.safe_load(defaults_file.read_text()) | overrides
    return (
        _ansible_like_env().get_template("bootstrap.exp.j2").render(opnsense_vmid=950, **defaults)
    )


def test_expect_script_answers_the_interface_assignment_with_em_names() -> None:
    script = _expect_script()

    assert '"Enter the WAN interface name" { send "em1\\r"; exp_continue }' in script
    assert '"Enter the LAN interface name" { send "em0\\r"; exp_continue }' in script
    assert "spawn socat STDIO,rawer UNIX-CONNECT:/var/run/qemu-server/950.serial0" in script


def test_expect_script_stops_logging_before_sending_the_payload() -> None:
    script = _expect_script()

    payload_sent = script.index("printf '%s' '$chunk' >> /tmp/ifb.b64")
    logging_off = script.index("log_user 0\nlog_file\n")
    logging_back = script.index("log_user 1")
    assert logging_off < payload_sent < logging_back
    assert script.index('"BOOTSTRAP OK"') < logging_back
    assert "$env(OPNSENSE_BOOTSTRAP_B64)" in script


def test_post_terraform_script_refuses_to_run_without_the_secrets(tmp_path: Path) -> None:
    env = {
        "PATH": os.environ["PATH"],
        "INFRAFOUNDRY_PACKAGE_DIR": str(tmp_path),
        "INFRAFOUNDRY_BLUEPRINT_DIR": str(BLUEPRINT_DIR),
        "INFRAFOUNDRY_VAR_vmid": "950",
        "INFRAFOUNDRY_VAR_vm_name": "fw-test",
        "INFRAFOUNDRY_VAR_target_node": "node3",
        "INFRAFOUNDRY_VAR_pve_host": "192.0.2.3",
        "INFRAFOUNDRY_VAR_wan_ip": "192.0.2.250",
    }

    result = subprocess.run(
        ["bash", str(BLUEPRINT_DIR / "scripts" / "opnsense-post-terraform.sh")],
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "INFRAFOUNDRY_VAR_opnsense_root_password is not set" in result.stderr
    assert not (tmp_path / ".generated-inventory.json").exists()


@pytest.mark.parametrize(
    "path",
    [
        BLUEPRINT_DIR / "opnsense-bootstrap.yml",
        *sorted((BLUEPRINT_DIR / "roles").rglob("*.yml")),
    ],
    ids=lambda p: str(p.relative_to(BLUEPRINT_DIR)),
)
def test_ansible_yaml_parses(path: Path) -> None:
    import yaml

    assert yaml.safe_load(path.read_text()) is not None


def test_readiness_probe_sends_no_credentials() -> None:
    # The box's certificate is self-signed and not verified, so the probe must
    # not hand the API key to whatever answers on the WAN address.
    script = (BLUEPRINT_DIR / "scripts" / "opnsense-post-terraform.sh").read_text()
    probe = script[script.index('URL="https://') :]

    assert "opnsense_api_key" not in probe
    assert "opnsense_api_secret" not in probe
    assert '[ "$code" = "302" ] || [ "$code" = "401" ]' in probe


def test_default_package_keeps_the_image_disk_size(loaded: Any) -> None:
    resources, _events, variables = loaded

    assert variables["disk_size"] == 0
    assert "disk_size" not in resources[0].config


def test_disk_size_input_reaches_the_vm(tmp_path: Path) -> None:
    package = tmp_path / "dev" / "proxmox" / "fw-test"
    package.mkdir(parents=True)
    source = (PACKAGE_DIR / "infrafoundry.yml").read_text()
    (package / "infrafoundry.yml").write_text(source.rstrip("\n") + "\n  disk_size: 16\n")
    resolver = BlueprintResolver(EXAMPLE_ENVS)
    loader = PackageLoader(EXAMPLE_ENVS, blueprint_resolver=resolver)

    resources, _events, variables = loader.load_package(package, provider="proxmox", env_name="dev")

    assert variables["disk_size"] == 16
    assert resources[0].config["disk_size"] == 16


def test_expect_script_has_no_grow_step_by_default() -> None:
    script = _expect_script()

    for text in ("gpart", "growfs", "ifb-grow"):
        assert text not in script


def test_expect_script_grows_the_filesystem_when_disk_size_is_set() -> None:
    script = _expect_script(opnsense_disk_size=16)

    first_shell = script.index("Timed out waiting for the shell")
    grow = script.index("gpart recover")
    assert first_shell < grow < script.index("log_user 0")
    assert "gpart resize -i" in script
    assert "growfs -y /" in script
    assert "/tmp/ifb-grow.log" in script
    block = script[script.index("set grow {") : script.index("log_user 0")]
    assert "ERROR:" not in block
    assert 'puts "WARNING: Growing the root filesystem timed out; continuing"' in block


def test_grow_step_is_valid_sh() -> None:
    script = _expect_script(opnsense_disk_size=16)
    body = re.search(r"set grow \{sh -c '(.*)'\}\n", script)
    assert body is not None

    subprocess.run(["sh", "-n", "-c", body.group(1)], check=True, capture_output=True)
