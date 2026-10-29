"""Tests for the console-connector blueprint (#1140).

Loads the real example-config package via PackageLoader and asserts the merged
configuration, then checks the shell scripts statically (syntax, portability,
and the install-script guarantees the blueprint README promises).

Depends only on files checked into this repository:
  - blueprints/console-connector/
  - example-config/envs/dev/proxmox/console-connector/
"""

import os
import subprocess
import textwrap
from pathlib import Path

import pytest

from infrafoundry.core.config.blueprint_resolver import BlueprintResolver
from infrafoundry.core.config.package_loader import PackageLoader
from infrafoundry.core.exceptions import InvalidConfigurationError

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_ENVS = REPO_ROOT / "example-config" / "envs"
PACKAGE_DIR = EXAMPLE_ENVS / "dev" / "proxmox" / "console-connector"
SCRIPTS_DIR = REPO_ROOT / "blueprints" / "console-connector" / "scripts"
POST_SCRIPT = SCRIPTS_DIR / "console-connector-post-terraform.sh"
REMOTE_SCRIPT = SCRIPTS_DIR / "console-connector-install-remote.sh"


@pytest.fixture
def loader() -> PackageLoader:
    """PackageLoader pointed at the real example-config envs/ directory."""
    return PackageLoader(EXAMPLE_ENVS, blueprint_resolver=BlueprintResolver(EXAMPLE_ENVS))


def test_example_package_variables(loader: PackageLoader) -> None:
    """Blueprint defaults and package overrides are merged."""
    _resources, _events, variables = loader.load_package(
        PACKAGE_DIR, provider="proxmox", env_name="dev"
    )
    assert variables["vm_name"] == "console-connector"
    assert variables["template_vmid"] == 900
    assert variables["cores"] == 8
    assert variables["memory"] == 32768
    assert variables["disk_size"] == 180
    assert variables["docker_version"] == "27.5.1"
    assert variables["console_agent_install_args"] == ""


def test_example_renders_vm_and_dhcp(loader: PackageLoader) -> None:
    """The package yields a proxmox VM and an opnsense reservation."""
    resources, _events, _variables = loader.load_package(
        PACKAGE_DIR, provider="proxmox", env_name="dev"
    )
    assert {(r.provider, r.type) for r in resources} == {
        ("proxmox", "vm"),
        ("opnsense", "kea.dhcp4.reservations"),
    }
    vm = next(r for r in resources if r.type == "vm")
    assert vm.config["clone"] == {"vm_id": 900, "node_name": "pve1"}
    assert vm.config["cores"] == 8
    assert vm.config["memory"] == 32768
    assert vm.config["disk"]["size"] == 180
    assert vm.config["tags"] == ["ontap", "console-connector"]
    assert vm.config["cloud_init_snippets"] == [
        "users/ansible",
        "network/dhcp",
        "packages/qemu-agent",
        "system/hostname",
    ]
    dhcp = next(r for r in resources if r.type == "kea.dhcp4.reservations")
    assert dhcp.config["ip_address"] == "192.168.1.51"
    assert dhcp.config["hostname"] == "console-connector"


def test_on_create_event_points_at_executable_script(loader: PackageLoader) -> None:
    """The on_create handler references the existing, executable post script."""
    _resources, events, _variables = loader.load_package(
        PACKAGE_DIR, provider="proxmox", env_name="dev"
    )
    handlers = events["on_create"]
    assert len(handlers) == 1
    handler = handlers[0]
    assert handler["type"] == "script"
    assert handler["timeout"] == 3600
    assert handler["requires"] == ["console-connector"]
    script = Path(handler["script"])
    assert script.name == "console-connector-post-terraform.sh"
    assert script.is_file()
    assert script.stat().st_mode & 0o111


def test_missing_required_input_fails(tmp_path: Path) -> None:
    """A package without the installer location fails to load."""
    envs = tmp_path / "envs"
    pkg = envs / "test" / "proxmox" / "cc"
    pkg.mkdir(parents=True)
    (pkg / "infrafoundry.yml").write_text(
        textwrap.dedent(
            """\
            name: cc
            blueprint: console-connector
            variables:
              vm_name: cc
              vmid: 230
              target_node: pve1
              disk_storage: local-lvm
              ip_address: "192.168.1.60"
              dhcp_subnet: s
            """
        )
    )
    loader = PackageLoader(envs, blueprint_resolver=BlueprintResolver(envs))
    with pytest.raises(InvalidConfigurationError, match="console_agent"):
        loader.load_package(pkg, provider="proxmox", env_name="test")


@pytest.mark.parametrize("script", [POST_SCRIPT, REMOTE_SCRIPT], ids=lambda p: p.name)
def test_scripts_are_valid_bash(script: Path) -> None:
    """Both scripts pass ``bash -n`` and are executable."""
    result = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert script.stat().st_mode & 0o111


def test_post_script_is_portable() -> None:
    """The local script reads the package vars and avoids jq/yq."""
    text = POST_SCRIPT.read_text()
    assert "INFRAFOUNDRY_PACKAGE_VARS" in text
    code = [ln for ln in text.splitlines() if not ln.lstrip().startswith("#")]
    for tool in ("jq", "yq"):
        assert not any(f"{tool} " in ln.split() or f"| {tool}" in ln for ln in code)
    assert "JUMPHOST" in text
    assert "console-connector-install-remote.sh" in text


def test_remote_script_guarantees() -> None:
    """Proxy vars are unset, Docker is pinned, and the guard precedes the download."""
    text = REMOTE_SCRIPT.read_text()
    assert "unset http_proxy https_proxy" in text
    assert "docker-ce=${docker_apt_version}" in text
    assert "DOCKER_VERSION" in text
    guard = text.index("if console_agent_installed; then")
    assert guard < text.index("curl -4 -fsSO")
    assert guard < text.index("apt-get install -y ca-certificates")
    assert text.count("console_agent_installed()") == 1


def test_remote_script_verifies_installer_before_running_it() -> None:
    """The download is checked against CONSOLE_AGENT_SHA256 before chmod and exec."""
    text = REMOTE_SCRIPT.read_text()
    assert ': "${CONSOLE_AGENT_SHA256:?required}"' in text
    check = text.index("sha256sum -c --status -")
    assert text.index("curl -4 -fsSO") < check
    assert check < text.index('chmod +x "${CONSOLE_AGENT_INSTALLER}"')
    assert check < text.index('"./${CONSOLE_AGENT_INSTALLER}"')


@pytest.mark.parametrize(
    ("sha", "ok"),
    [("a" * 64, True), ("A1" * 32, True), ("a" * 63, False), ("g" * 64, False), ("", False)],
)
def test_remote_script_rejects_malformed_sha256(sha: str, ok: bool) -> None:
    """Only a 64-character hex digest gets past the input check."""
    text = REMOTE_SCRIPT.read_text()
    start = text.index('if ! [[ "${CONSOLE_AGENT_SHA256}"')
    block = text[start : text.index("fi\n", start) + 3]
    result = subprocess.run(
        ["bash", "-c", block],
        env={**os.environ, "CONSOLE_AGENT_SHA256": sha},
        capture_output=True,
        text=True,
    )
    assert (result.returncode == 0) is ok


def test_sha256_is_a_required_input(tmp_path: Path) -> None:
    """A package with the installer location but no digest fails to load."""
    envs = tmp_path / "envs"
    pkg = envs / "test" / "proxmox" / "cc"
    pkg.mkdir(parents=True)
    (pkg / "infrafoundry.yml").write_text(
        textwrap.dedent(
            """\
            name: cc
            blueprint: console-connector
            variables:
              vm_name: cc
              vmid: 230
              target_node: pve1
              disk_storage: local-lvm
              ip_address: "192.168.1.60"
              dhcp_subnet: s
              console_agent_url_base: "https://web/cc"
              console_agent_installer: NetApp_Console_Agent_Cloud_v4.0.0
            """
        )
    )
    loader = PackageLoader(envs, blueprint_resolver=BlueprintResolver(envs))
    with pytest.raises(InvalidConfigurationError, match="console_agent_sha256"):
        loader.load_package(pkg, provider="proxmox", env_name="test")


def test_post_script_upload_and_jumphost_hardening() -> None:
    """No fixed /tmp staging path, and the jumphost hop keeps host-key checks."""
    text = POST_SCRIPT.read_text()
    assert "/tmp/_console_connector_upload" not in text
    assert "/tmp/console-connector-install-remote.sh" not in text
    assert "mktemp" in text
    assert 'JUMP_SSH="ssh -o ConnectTimeout=10"' in text
    jump_lines = [ln for ln in text.splitlines() if "${JUMP_SSH}" in ln]
    assert jump_lines
    assert all("StrictHostKeyChecking" not in ln.split("${JUMPHOST}")[0] for ln in jump_lines)
