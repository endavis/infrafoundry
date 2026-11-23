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
    assert vm.config["clone"] == {"vm_id": 900, "node_name": "node1"}
    assert vm.config["cores"] == 8
    assert vm.config["memory"] == 32768
    assert "balloon" not in vm.config
    assert vm.config["disk"]["size"] == 180
    assert vm.config["tags"] == ["ontap", "console-connector"]
    assert vm.config["cloud_init_snippets"] == [
        "users/ansible",
        "network/dhcp",
        "packages/qemu-agent",
        "system/hostname",
    ]
    dhcp = next(r for r in resources if r.type == "kea.dhcp4.reservations")
    assert dhcp.config["ip_address"] == "192.0.2.51"
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


def test_balloon_is_rendered_when_set(tmp_path: Path) -> None:
    """A non-zero balloon input becomes the VM's balloon minimum (#1183)."""
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
              target_node: node1
              disk_storage: local-lvm
              ip_address: "192.0.2.60"
              dhcp_subnet: s
              memory: 14336
              balloon: 8192
              console_agent_url_base: "http://example.invalid/connector"
              console_agent_installer: netapp-console-agent-4.12.0
              console_agent_sha256: "%s"
            """
            % ("a" * 64)
        )
    )
    loader = PackageLoader(envs, blueprint_resolver=BlueprintResolver(envs))
    resources, _events, _variables = loader.load_package(pkg, provider="proxmox", env_name="test")
    vm = next(r for r in resources if r.type == "vm")
    assert vm.config["memory"] == 14336
    assert vm.config["balloon"] == 8192


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
              target_node: node1
              disk_storage: local-lvm
              ip_address: "192.0.2.60"
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


def test_docker_version_lookup_survives_pipefail(tmp_path: Path) -> None:
    """Resolving the docker-ce version does not die of SIGPIPE under ``pipefail`` (#1180)."""
    rows = "".join(
        f" docker-ce | 5:27.{i}.1-1~ubuntu.24.04~noble | https://download.docker.com noble/stable\n"
        for i in range(5, 0, -1)
    )
    stub = tmp_path / "apt-cache"
    # Enough output to overflow the pipe buffer after awk has matched.
    stub.write_text(f"#!/bin/bash\nfor _ in $(seq 2000); do printf '%s' '{rows}'; done\n")
    stub.chmod(0o755)
    line = next(
        ln for ln in REMOTE_SCRIPT.read_text().splitlines() if ln.startswith("docker_apt_version=")
    )
    result = subprocess.run(
        ["bash", "-c", f'set -euo pipefail\n{line}\necho "$docker_apt_version"'],
        env={
            **os.environ,
            "PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}",
            "DOCKER_VERSION": "27.5.1",
        },
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "5:27.5.1-1~ubuntu.24.04~noble"


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
              target_node: node1
              disk_storage: local-lvm
              ip_address: "192.0.2.60"
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
    assert 'JUMP_SSH="ssh -o StrictHostKeyChecking=yes -o ConnectTimeout=10"' in text
    jump_lines = [ln for ln in text.splitlines() if "${JUMP_SSH}" in ln]
    assert jump_lines
    assert all("StrictHostKeyChecking" not in ln.split("${JUMPHOST}")[0] for ln in jump_lines)


REGISTER_SCRIPT = SCRIPTS_DIR / "console-connector-register.py"
BLUEPRINT_README = REPO_ROOT / "blueprints" / "console-connector" / "README.md"


def test_register_helper_compiles_and_is_executable() -> None:
    """The registration helper is valid Python and has the exec bit."""
    compile(REGISTER_SCRIPT.read_text(), str(REGISTER_SCRIPT), "exec")
    assert os.access(REGISTER_SCRIPT, os.X_OK)


def test_post_script_calls_helper_without_secret_argv() -> None:
    """Phase 5 calls the helper and never puts a secret on a command line."""
    text = POST_SCRIPT.read_text()
    assert "console-connector-register.py" in text
    code = [ln for ln in text.splitlines() if not ln.lstrip().startswith("#")]
    assert not any("console_client_secret" in ln and "register" in ln for ln in code)


def test_registration_inputs_are_optional(loader: PackageLoader) -> None:
    """The example package loads without the registration inputs."""
    _r, _e, variables = loader.load_package(PACKAGE_DIR, provider="proxmox", env_name="dev")
    assert variables["console_client_secret"] == ""
    assert variables["console_site"] == "default"


def test_readme_uses_real_installer_name() -> None:
    """The README names the installer netapp-console-agent-<version>."""
    text = BLUEPRINT_README.read_text()
    assert "netapp-console-agent-<version>" in text
    assert "NetApp_Console_Agent_Cloud" not in text


# --- Balloon handling during the agent install (#1632) ---

_BALLOON_BEGIN = "# --- balloon helpers: begin ---"
_BALLOON_END = "# --- balloon helpers: end ---"


def _balloon_helpers() -> str:
    """The balloon helper block of the post-Terraform script."""
    text = POST_SCRIPT.read_text()
    start = text.index(_BALLOON_BEGIN)
    return text[start : text.index(_BALLOON_END) + len(_BALLOON_END)]


def _cleanup_function() -> str:
    """The script's real ``cleanup`` function with the balloon restore, nothing else."""
    text = POST_SCRIPT.read_text()
    start = text.index("cleanup() {")
    block = text[start : text.index("\n}\n", start) + 3]
    # Keep only the balloon part; the rest needs the jumphost state.
    return block.split("    rm -f")[0] + "}\n"


def _run_balloon(
    tmp_path: Path,
    body: str,
    *,
    variables: dict[str, str] | None = None,
    memtotals: list[str] | None = None,
    extra: str = "",
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    """Run ``body`` after the helper block, with stub ssh/sleep; return result and ssh log."""
    log = tmp_path / "ssh.log"
    log.write_text("")
    for name in ("ssh", "sleep"):
        stub = tmp_path / name
        if name == "ssh":
            stub.write_text(f'#!/bin/bash\necho "$*" >> {log}\n')
        else:
            stub.write_text("#!/bin/bash\nexit 0\n")
        stub.chmod(0o755)
    counter = tmp_path / "counter"
    counter.write_text("0")
    values = tmp_path / "memtotals"
    values.write_text("\n".join(memtotals or ["MemTotal: 14000000 kB"]) + "\n")
    env_vars = {
        "vmid": "230",
        "target_node": "node1",
        "ip_address": "192.0.2.60",
        "memory": "14336",
        "balloon": "8192",
    }
    env_vars.update(variables or {})
    assigns = "".join(f"{k}='{v}'\n" for k, v in env_vars.items())
    script = (
        "set -euo pipefail\n"
        f"{assigns}"
        "MAX_WAIT=10\n"
        f"{_balloon_helpers()}\n"
        f"{_cleanup_function()}"
        "trap cleanup EXIT\n"
        "remote_cmd() {\n"
        f"  local n; n=$(cat {counter}); echo $((n + 1)) > {counter}\n"
        f"  local total; total=$(wc -l < {values})\n"
        "  [ $((n + 1)) -gt $total ] && n=$((total - 1))\n"
        f'  sed -n "$((n + 1))p" {values}\n'
        "}\n"
        f"{extra}\n"
        f"{body}\n"
    )
    result = subprocess.run(
        ["bash", "-c", script],
        env={**os.environ, "PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}"},
        capture_output=True,
        text=True,
    )
    return result, [ln for ln in log.read_text().splitlines() if ln]


@pytest.mark.parametrize("balloon", ["0", ""])
def test_balloon_disabled_makes_no_ssh_call(tmp_path: Path, balloon: str) -> None:
    """With balloon 0 or empty the guarded Phase 3a block never touches the node."""
    result, calls = _run_balloon(
        tmp_path,
        "if balloon_enabled; then raise_balloon; wait_for_memtotal; fi",
        variables={"balloon": balloon},
    )
    assert result.returncode == 0, result.stderr
    assert calls == []


def test_balloon_unset_makes_no_ssh_call(tmp_path: Path) -> None:
    """A package that never sets balloon skips the raise."""
    script = f"set -euo pipefail\n{_balloon_helpers()}\nballoon_enabled && echo on || echo off\n"
    result = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
    assert result.stdout.strip() == "off"


@pytest.mark.parametrize(
    ("pve_host", "target"),
    [("", "root@node1"), ("pve1.example.com", "root@pve1.example.com")],
)
def test_raise_balloon_targets_the_node(tmp_path: Path, pve_host: str, target: str) -> None:
    """The raise sets balloon to memory on pve_host, falling back to target_node."""
    result, calls = _run_balloon(
        tmp_path, "raise_balloon", variables={"pve_host": pve_host} if pve_host else None
    )
    assert result.returncode == 0, result.stderr
    # The raise is the qm set plus the monitor call; the EXIT trap adds the restore.
    assert len(calls) == 3
    assert target in calls[0]
    assert calls[0].endswith("qm set 230 --balloon 14336")
    assert "StrictHostKeyChecking=yes" in calls[0]


def test_balloon_restored_when_install_fails(tmp_path: Path) -> None:
    """A failure after the raise still restores the configured balloon on exit."""
    result, calls = _run_balloon(tmp_path, "raise_balloon\nfalse")
    assert result.returncode != 0
    assert len(calls) == 3
    assert calls[0].endswith("--balloon 14336")
    assert calls[2].endswith("qm set 230 --balloon 8192")


def test_balloon_not_restored_twice(tmp_path: Path) -> None:
    """After an explicit restore, the EXIT trap makes no second call."""
    result, calls = _run_balloon(
        tmp_path, 'raise_balloon\nrestore_balloon\n[ "${BALLOON_RAISED}" -eq 0 ]'
    )
    assert result.returncode == 0, result.stderr
    assert [c.rsplit(" ", 1)[1] for c in calls] == ["14336", "230", "8192"]


def test_raise_balloon_sets_minimum_then_live_target(tmp_path: Path) -> None:
    """The raise sends qm set, then the monitor balloon command, in that order (#1634)."""
    result, calls = _run_balloon(tmp_path, "raise_balloon")
    assert result.returncode == 0, result.stderr
    assert calls[0].endswith("qm set 230 --balloon 14336")
    assert calls[1].endswith('echo "balloon 14336" | qm monitor 230')
    assert "root@node1" in calls[1]


def test_raise_balloon_warns_and_continues_when_monitor_fails(tmp_path: Path) -> None:
    """A failing monitor call warns; the raise still succeeds and the restore runs."""
    log = tmp_path / "ssh.log"
    extra = f'ssh() {{\n  echo "$*" >> {log}\n  case "$*" in *"qm monitor"*) return 1;; esac\n}}\n'
    result, calls = _run_balloon(tmp_path, "raise_balloon\necho after-raise", extra=extra)
    assert result.returncode == 0, result.stderr
    assert "after-raise" in result.stdout
    assert "WARNING" in result.stderr
    assert "qm monitor" in calls[1]
    assert calls[2].endswith("qm set 230 --balloon 8192")


def test_phase_3a_wait_limit_is_600() -> None:
    """The memory wait after the raise allows 600 seconds."""
    text = POST_SCRIPT.read_text()
    phase = text[text.index("    raise_balloon\n") :]
    assert phase.startswith("    raise_balloon\n    MAX_WAIT=600\n")


def test_wait_for_memtotal_succeeds_once_memory_arrives(tmp_path: Path) -> None:
    """The wait polls until MemTotal reaches the installer minimum."""
    result, _ = _run_balloon(
        tmp_path,
        "wait_for_memtotal",
        memtotals=["MemTotal:        9000000 kB", "MemTotal:       14000000 kB"],
    )
    assert result.returncode == 0, result.stderr
    assert "13671 MiB" in result.stdout


def test_wait_for_memtotal_times_out(tmp_path: Path) -> None:
    """A guest that never gets the memory fails with the target in the message."""
    result, _ = _run_balloon(
        tmp_path, "wait_for_memtotal", memtotals=["MemTotal:        9000000 kB"]
    )
    assert result.returncode != 0
    assert "13312" in result.stderr
    assert "MemTotal" in result.stderr


@pytest.mark.parametrize("bad", [{"memory": "14336; id"}, {"vmid": "abc"}, {"balloon": "8x"}])
def test_balloon_inputs_validated_before_ssh(tmp_path: Path, bad: dict[str, str]) -> None:
    """A non-numeric value is rejected before anything reaches the node."""
    result, calls = _run_balloon(tmp_path, "raise_balloon", variables=bad)
    assert result.returncode != 0
    assert calls == []


def test_balloon_phase_ordering() -> None:
    """Raise and wait come before the installer; the explicit restore comes after it."""
    text = POST_SCRIPT.read_text()
    installer = text.index("bash ~/console-connector-install-remote.sh")
    assert text.index("    raise_balloon\n") < installer
    assert text.index("    wait_for_memtotal\n") < installer
    restore = text.index("restore_balloon || exit 1")
    assert installer < restore < text.index("--- Phase 4")


def test_pve_host_is_optional(loader: PackageLoader) -> None:
    """The example package, which sets no pve_host, still loads."""
    _resources, _events, variables = loader.load_package(
        PACKAGE_DIR, provider="proxmox", env_name="dev"
    )
    assert variables.get("pve_host", "") == ""


def test_readme_describes_the_balloon_raise() -> None:
    """The README no longer claims the installer is unaffected, and names pve_host."""
    text = BLUEPRINT_README.read_text()
    assert "installer's check is\n  unaffected" not in text
    assert "unaffected" not in text
    assert "pve_host" in text
