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
    "wan_ip": "192.0.2.250",
    "wan_prefix": "24",
    "lan_ip": "203.0.113.1",
    "lan_prefix": "24",
    "api_allow_cidr": "192.0.2.0/24",
    "api_allow_lan": "0",
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


def _bootstrap_php(**overrides: str) -> str:
    return (
        _ansible_like_env()
        .get_template("bootstrap.php.j2")
        .render(opnsense_bootstrap_values=VALUES | overrides)
    )


def test_bootstrap_php_allows_only_the_wan_address_by_default() -> None:
    php = _bootstrap_php()

    assert "lanip" not in php
    assert php.count("addChild('rule')") == 1


def test_bootstrap_php_adds_a_lan_address_rule_when_asked() -> None:
    php = _bootstrap_php(api_allow_lan="1")

    assert php.count("addChild('rule')") == 2
    for line in [
        "$lan_rule->addChild('interface', 'wan');",
        "$lan_destination->addChild('network', 'lanip');",
        "$lan_destination->addChild('port', '443');",
        "$lan_rule->addChild('source')->addChild('address', $v['api_allow_cidr']);",
        "$destination->addChild('network', 'wanip');",
    ]:
        assert line in php
    assert php.index("$lan_rule") < php.index("Config::getInstance()->save();")


@pytest.mark.skipif(shutil.which("php") is None, reason="php is not installed")
@pytest.mark.parametrize("api_allow_lan", ["0", "1"])
def test_bootstrap_php_is_valid_php(tmp_path: Path, api_allow_lan: str) -> None:
    script = tmp_path / "bootstrap.php"
    script.write_text(_bootstrap_php(api_allow_lan=api_allow_lan))

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

    assert yaml.safe_load(path.read_text(encoding="utf-8")) is not None


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


def test_default_package_does_not_open_the_lan_address(loaded: Any) -> None:
    _resources, _events, variables = loaded

    assert variables["api_allow_lan"] is False


def test_api_allow_lan_input_reaches_the_package(tmp_path: Path) -> None:
    package = tmp_path / "dev" / "proxmox" / "fw-test"
    package.mkdir(parents=True)
    source = (PACKAGE_DIR / "infrafoundry.yml").read_text()
    (package / "infrafoundry.yml").write_text(source.rstrip("\n") + "\n  api_allow_lan: true\n")
    resolver = BlueprintResolver(EXAMPLE_ENVS)
    loader = PackageLoader(EXAMPLE_ENVS, blueprint_resolver=resolver)

    _resources, _events, variables = loader.load_package(
        package, provider="proxmox", env_name="dev"
    )

    assert variables["api_allow_lan"] is True


def test_playbook_and_role_pass_api_allow_lan_to_the_php() -> None:
    import yaml

    role = BLUEPRINT_DIR / "roles" / "opnsense-bootstrap"
    playbook = yaml.safe_load((BLUEPRINT_DIR / "opnsense-bootstrap.yml").read_text())
    tasks = yaml.safe_load((role / "tasks" / "main.yml").read_text())
    defaults = yaml.safe_load((role / "defaults" / "main.yml").read_text())

    role_vars = playbook[0]["roles"][0]["vars"]
    assert "INFRAFOUNDRY_VAR_api_allow_lan" in role_vars["opnsense_api_allow_lan"]
    assert "default('false', true)" in role_vars["opnsense_api_allow_lan"]
    [launch] = [t for t in tasks if "opnsense_bootstrap_values" in t.get("vars", {})]
    assert "ternary('1', '0')" in launch["vars"]["opnsense_bootstrap_values"]["api_allow_lan"]
    assert defaults["opnsense_api_allow_lan"] is False


SYNC = {"interface": "em2", "descr": "SYNC", "ip": "192.0.2.10", "prefix": "29"}


def _sync_package(tmp_path: Path, extra: str) -> list[Any]:
    package = tmp_path / "dev" / "proxmox" / "fw-test"
    package.mkdir(parents=True)
    source = (PACKAGE_DIR / "infrafoundry.yml").read_text()
    (package / "infrafoundry.yml").write_text(source.rstrip("\n") + "\n" + extra)
    loader = PackageLoader(EXAMPLE_ENVS, blueprint_resolver=BlueprintResolver(EXAMPLE_ENVS))
    resources, _events, _variables = loader.load_package(
        package, provider="proxmox", env_name="dev"
    )
    return resources


def _sync_php(**overrides: str) -> str:
    return (
        _ansible_like_env()
        .get_template("bootstrap.php.j2")
        .render(opnsense_bootstrap_values=VALUES, opnsense_bootstrap_sync=SYNC | overrides)
    )


def test_default_package_has_no_sync_nic(loaded: Any) -> None:
    resources, _events, variables = loaded

    assert variables["sync_bridge"] == ""
    assert len(resources[0].config["network"]) == 2


def test_sync_bridge_adds_a_third_untagged_nic(tmp_path: Path) -> None:
    [vm] = _sync_package(tmp_path, '  sync_bridge: vmbr2\n  sync_ip: "192.0.2.10"\n')

    assert vm.config["network"][2:] == [{"bridge": "vmbr2", "model": "e1000"}]
    assert len(vm.config["network"]) == 3


def test_sync_vlan_tags_the_third_nic(tmp_path: Path) -> None:
    [vm] = _sync_package(
        tmp_path, '  sync_bridge: vmbr2\n  sync_vlan: 30\n  sync_ip: "192.0.2.10"\n'
    )

    assert vm.config["network"][2] == {"bridge": "vmbr2", "model": "e1000", "tag": 30}


def test_bootstrap_php_without_sync_does_not_touch_opt1() -> None:
    php = _bootstrap_php()

    assert "opt1" not in php
    assert php.count("base64_decode(") == 1


def test_bootstrap_php_with_sync_assigns_opt1_and_adds_rules_before_save() -> None:
    php = _sync_php()

    assert "$cfg->interfaces->addChild('opt1');" in php
    assert "$sync->addChild('if', $s['interface']);" in php
    assert "$sync->addChild('ipaddr', $s['ip']);" in php
    assert "$pfsync_rule->addChild('protocol', 'pfsync');" in php
    assert "$xmlrpc_destination->addChild('network', 'opt1ip');" in php
    assert "$xmlrpc_destination->addChild('address'" not in php
    assert "$xmlrpc_destination->addChild('port', '443');" in php
    assert php.count("addChild('rule')") == 3
    [_, encoded] = re.findall(r"base64_decode\('([A-Za-z0-9+/=]+)'\)", php)
    assert json.loads(base64.b64decode(encoded)) == SYNC
    assert php.index("$xmlrpc_rule") < php.index("Config::getInstance()->save();")


def test_sync_rule_destination_is_the_same_for_any_sync_address() -> None:
    def destination_lines(php: str) -> list[str]:
        return [line for line in php.splitlines() if "$xmlrpc_destination" in line]

    first = destination_lines(_sync_php(ip="192.0.2.10"))
    second = destination_lines(_sync_php(ip="192.0.2.11"))

    assert first == second
    assert "192.0.2" not in "".join(first)


def test_bootstrap_php_with_sync_and_api_allow_lan_has_four_rules() -> None:
    php = (
        _ansible_like_env()
        .get_template("bootstrap.php.j2")
        .render(
            opnsense_bootstrap_values=VALUES | {"api_allow_lan": "1"},
            opnsense_bootstrap_sync=SYNC,
        )
    )

    assert php.count("addChild('rule')") == 4


def test_bootstrap_php_with_an_empty_sync_ip_skips_the_sync_block() -> None:
    assert "opt1" not in _sync_php(ip="")


@pytest.mark.skipif(shutil.which("php") is None, reason="php is not installed")
def test_bootstrap_php_with_sync_is_valid_php(tmp_path: Path) -> None:
    script = tmp_path / "bootstrap.php"
    script.write_text(_sync_php())

    subprocess.run(["php", "-l", str(script)], check=True, capture_output=True)


def test_playbook_and_role_pass_the_sync_inputs_to_the_php() -> None:
    import yaml

    role = BLUEPRINT_DIR / "roles" / "opnsense-bootstrap"
    playbook = yaml.safe_load((BLUEPRINT_DIR / "opnsense-bootstrap.yml").read_text())
    tasks = yaml.safe_load((role / "tasks" / "main.yml").read_text())
    defaults = yaml.safe_load((role / "defaults" / "main.yml").read_text())

    role_vars = playbook[0]["roles"][0]["vars"]
    for name in ("sync_bridge", "sync_ip", "sync_prefix"):
        assert f"INFRAFOUNDRY_VAR_{name}" in role_vars[f"opnsense_{name}"]
    [launch] = [t for t in tasks if "opnsense_bootstrap_sync" in t.get("vars", {})]
    assert launch["vars"]["opnsense_bootstrap_sync"]["interface"] == "{{ opnsense_sync_if }}"
    assert defaults["opnsense_sync_if"] == "em2"
    assert defaults["opnsense_sync_descr"] == "SYNC"
    assert defaults["opnsense_sync_bridge"] == ""


SSH_KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIExample admin@example.com"
SSH: dict[str, Any] = {
    "enabled": "1",
    "root_login": "0",
    "password_auth": "0",
    "authorized_keys": [SSH_KEY],
}


def _ssh_php(**overrides: Any) -> str:
    return (
        _ansible_like_env()
        .get_template("bootstrap.php.j2")
        .render(opnsense_bootstrap_values=VALUES, opnsense_bootstrap_ssh=SSH | overrides)
    )


def _blobs(php: str) -> list[Any]:
    return [
        json.loads(base64.b64decode(e))
        for e in re.findall(r"base64_decode\('([A-Za-z0-9+/=]+)'\)", php)
    ]


def _ssh_package(tmp_path: Path, extra: str) -> dict[str, Any]:
    package = tmp_path / "dev" / "proxmox" / "fw-test"
    package.mkdir(parents=True)
    source = (PACKAGE_DIR / "infrafoundry.yml").read_text()
    (package / "infrafoundry.yml").write_text(source.rstrip("\n") + "\n" + extra)
    loader = PackageLoader(EXAMPLE_ENVS, blueprint_resolver=BlueprintResolver(EXAMPLE_ENVS))
    _resources, _events, variables = loader.load_package(
        package, provider="proxmox", env_name="dev"
    )
    return variables


def test_default_package_has_ssh_off(loaded: Any) -> None:
    _resources, _events, variables = loaded

    assert variables["ssh_enabled"] is False
    assert variables["ssh_root_login"] is False
    assert variables["ssh_password_auth"] is False
    assert variables["ssh_authorized_keys"] == []


def test_ssh_inputs_reach_the_package(tmp_path: Path) -> None:
    variables = _ssh_package(
        tmp_path, f'  ssh_enabled: true\n  ssh_authorized_keys:\n    - "{SSH_KEY}"\n'
    )

    assert variables["ssh_enabled"] is True
    assert variables["ssh_authorized_keys"] == [SSH_KEY]


def test_bootstrap_php_without_ssh_is_unchanged() -> None:
    php = _bootstrap_php()

    assert "ssh" not in php
    assert "authorizedkeys" not in php
    assert php.count("base64_decode(") == 1
    disabled = (
        _ansible_like_env()
        .get_template("bootstrap.php.j2")
        .render(opnsense_bootstrap_values=VALUES, opnsense_bootstrap_ssh=SSH | {"enabled": "0"})
    )
    assert disabled == php


def test_bootstrap_php_key_only_ssh() -> None:
    php = _ssh_php()

    assert "$ssh->enabled = 'enabled';" in php
    assert "$root->authorizedkeys = base64_encode(implode(\"\\n\", $h['authorized_keys']));" in php
    assert "if ($h['root_login'] === '1')" in php
    assert "if ($h['password_auth'] === '1')" in php
    assert _blobs(php)[1] == SSH
    assert "AAAAC3NzaC1lZDI1NTE5" not in php
    assert php.index("$ssh->enabled") < php.index("Config::getInstance()->save();")


def test_bootstrap_php_password_ssh() -> None:
    php = _ssh_php(password_auth="1", root_login="1", authorized_keys=[])

    blob = _blobs(php)[1]
    assert (blob["password_auth"], blob["root_login"], blob["authorized_keys"]) == ("1", "1", [])
    assert "$ssh->enabled = 'enabled';" in php


def test_bootstrap_php_with_sync_and_ssh_has_three_blobs() -> None:
    php = (
        _ansible_like_env()
        .get_template("bootstrap.php.j2")
        .render(
            opnsense_bootstrap_values=VALUES,
            opnsense_bootstrap_sync=SYNC,
            opnsense_bootstrap_ssh=SSH,
        )
    )

    assert php.count("base64_decode(") == 3
    assert php.count("addChild('rule')") == 3


@pytest.mark.skipif(shutil.which("php") is None, reason="php is not installed")
@pytest.mark.parametrize("overrides", [{}, {"password_auth": "1", "authorized_keys": []}])
def test_bootstrap_php_with_ssh_is_valid_php(tmp_path: Path, overrides: dict[str, Any]) -> None:
    script = tmp_path / "bootstrap.php"
    script.write_text(_ssh_php(**overrides))

    subprocess.run(["php", "-l", str(script)], check=True, capture_output=True)


def test_playbook_and_role_pass_the_ssh_inputs_to_the_php() -> None:
    import yaml

    role = BLUEPRINT_DIR / "roles" / "opnsense-bootstrap"
    playbook = yaml.safe_load((BLUEPRINT_DIR / "opnsense-bootstrap.yml").read_text())
    tasks = yaml.safe_load((role / "tasks" / "main.yml").read_text())
    defaults = yaml.safe_load((role / "defaults" / "main.yml").read_text())

    role_vars = playbook[0]["roles"][0]["vars"]
    for name in ("ssh_enabled", "ssh_root_login", "ssh_password_auth"):
        assert f"INFRAFOUNDRY_VAR_{name}" in role_vars[f"opnsense_{name}"]
        assert "default('false', true)" in role_vars[f"opnsense_{name}"]
    assert "INFRAFOUNDRY_PACKAGE_VARS" in role_vars["opnsense_ssh_authorized_keys"]
    assert "from_json" in role_vars["opnsense_ssh_authorized_keys"]
    [launch] = [t for t in tasks if "opnsense_bootstrap_ssh" in t.get("vars", {})]
    ssh = launch["vars"]["opnsense_bootstrap_ssh"]
    for field in ("enabled", "root_login", "password_auth"):
        assert "ternary('1', '0')" in ssh[field]
    assert defaults["opnsense_ssh_enabled"] is False
    assert defaults["opnsense_ssh_root_login"] is False
    assert defaults["opnsense_ssh_password_auth"] is False
    assert defaults["opnsense_ssh_authorized_keys"] == []


def _truthy(value: Any) -> bool:
    return value is True or str(value).lower() in ("true", "1", "yes")


def _ssh_check_passes(**role_vars: Any) -> bool | None:
    """Evaluate the role's SSH assert; None when its `when` skips the task."""
    import yaml

    tasks = yaml.safe_load(
        (BLUEPRINT_DIR / "roles" / "opnsense-bootstrap" / "tasks" / "main.yml").read_text()
    )
    [task] = [t for t in tasks if t["name"] == "Check the SSH inputs"]
    env = Environment(undefined=StrictUndefined)
    env.filters["bool"] = _truthy

    def evaluate(expr: str) -> bool:
        return env.from_string("{{ " + expr + " }}").render(**role_vars) == "True"

    if not evaluate(task["when"]):
        return None
    return all(evaluate(expr) for expr in task["ansible.builtin.assert"]["that"])


@pytest.mark.parametrize(
    ("role_vars", "expected"),
    [
        ({"enabled": "true", "password": "false", "keys": []}, False),
        ({"enabled": "true", "password": "true", "keys": []}, True),
        ({"enabled": "true", "password": "false", "keys": [SSH_KEY]}, True),
        ({"enabled": "false", "password": "false", "keys": []}, None),
        ({"enabled": "true", "password": "false", "keys": SSH_KEY}, False),
    ],
)
def test_role_refuses_ssh_with_no_way_to_log_in(
    role_vars: dict[str, Any], expected: bool | None
) -> None:
    result = _ssh_check_passes(
        opnsense_ssh_enabled=role_vars["enabled"],
        opnsense_ssh_password_auth=role_vars["password"],
        opnsense_ssh_authorized_keys=role_vars["keys"],
    )

    assert result is expected
