"""Shell tests for the reverse-proxy scripts (#1689), with stubbed ssh and caddy tools."""

from __future__ import annotations

import base64
import os
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "blueprints" / "reverse-proxy" / "scripts"
CONFIG = SCRIPTS / "reverse-proxy-config.sh"
NODE = SCRIPTS / "reverse-proxy-node.sh"

KNOWN_HOSTS = "reverse-proxy,192.0.2.70 ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGJ1bmRsZWRrZXk"
ROUTES = '[{"name": "nas", "backend": "https://192.0.2.20", "insecure": true}]'

_SSH_STUB = """#!/bin/sh
printf '%s\\n' "$*" >> "$RECORD/ssh_calls"
case "$*" in
*mktemp*) cat > "$RECORD/staged"; echo /tmp/staged-hk; exit 0 ;;
*"bash -c"*) cat > "$RECORD/payload"; exit "${FAKE_NODE_RC:-0}" ;;
esac
exit 0
"""


def _stubs(directory: Path, tools: dict[str, str]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for name, body in tools.items():
        stub = directory / name
        stub.write_text(body)
        stub.chmod(0o755)


def _run_config(
    tmp_path: Path, env_extra: dict[str, str]
) -> tuple[subprocess.CompletedProcess[str], Path]:
    record = tmp_path / "record"
    record.mkdir()
    _stubs(tmp_path / "bin", {"ssh": _SSH_STUB, "sleep": "#!/bin/sh\nexit 0\n"})
    env = {
        "PATH": f"{tmp_path / 'bin'}:{os.environ['PATH']}",
        "HOME": str(tmp_path),
        "RECORD": str(record),
        "TMPDIR": str(tmp_path),
        "INFRAFOUNDRY_WARNINGS_FILE": str(tmp_path / "warnings"),
        "RP_VM_NAME": "reverse-proxy",
        "RP_IP": "192.0.2.70",
        "RP_JUMPHOST": "",
        "RP_SSH_USER": "ansible",
        "RP_KNOWN_HOSTS": KNOWN_HOSTS,
        "RP_DOMAIN": "example.com",
        "RP_CERT_DIR": "/etc/ssl/infrafoundry",
        "RP_ROUTES": ROUTES,
        "RP_ALLOWED": "[]",
        **env_extra,
    }
    result = subprocess.run(
        ["bash", str(CONFIG)], env=env, capture_output=True, text=True, check=False, timeout=60
    )
    return result, record


def _calls(record: Path) -> list[str]:
    path = record / "ssh_calls"
    return path.read_text().splitlines() if path.exists() else []


@pytest.mark.parametrize("script", sorted(SCRIPTS.glob("*.sh")), ids=lambda p: p.name)
def test_scripts_do_not_disable_host_key_checking(script: Path) -> None:
    text = script.read_text(encoding="utf-8")
    assert "StrictHostKeyChecking=no" not in text
    assert "accept-new" not in text
    assert "UserKnownHostsFile=/dev/null" not in text
    assert "ANSIBLE_HOST_KEY_CHECKING=False" not in text


def test_every_ssh_call_is_strict_and_pinned(tmp_path: Path) -> None:
    result, record = _run_config(tmp_path, {})

    assert result.returncode == 0, result.stderr
    calls = _calls(record)
    assert calls
    for call in calls:
        assert "StrictHostKeyChecking=yes" in call
    assert all("GlobalKnownHostsFile=/dev/null" in c for c in calls)


@pytest.mark.parametrize("known_hosts", ["", "not a known hosts line"])
def test_missing_or_malformed_known_hosts_exit_before_any_ssh(
    tmp_path: Path, known_hosts: str
) -> None:
    result, record = _run_config(tmp_path, {"RP_KNOWN_HOSTS": known_hosts})

    assert result.returncode != 0
    assert _calls(record) == []


@pytest.mark.parametrize(
    "override",
    [
        {"RP_IP": "1.2.3.4;id"},
        {"RP_JUMPHOST": "ansible@jump.example.com;id"},
        {"RP_SSH_USER": "a b"},
        {"RP_CERT_DIR": "/etc/ssl/x;id"},
    ],
)
def test_injected_values_are_rejected_before_any_ssh(
    tmp_path: Path, override: dict[str, str]
) -> None:
    result, record = _run_config(tmp_path, override)

    assert result.returncode != 0
    assert _calls(record) == []
    assert "invalid" in result.stderr


def test_jumphost_stages_the_known_hosts_and_cleans_up(tmp_path: Path) -> None:
    result, record = _run_config(tmp_path, {"RP_JUMPHOST": "ansible@jump.example.com"})

    assert result.returncode == 0, result.stderr
    assert (record / "staged").read_text().strip() == KNOWN_HOSTS
    calls = _calls(record)
    assert any("rm -f '/tmp/staged-hk'" in c for c in calls)
    assert all("ansible@jump.example.com" in c for c in calls)


def test_payload_holds_the_caddyfile_and_the_node_script(tmp_path: Path) -> None:
    result, record = _run_config(tmp_path, {})

    assert result.returncode == 0, result.stderr
    payload = (record / "payload").read_text()
    match = re.search(r"^RP_CADDYFILE_B64=(\S+)$", payload, re.MULTILINE)
    assert match is not None
    assert "https://nas.example.com {" in base64.b64decode(match.group(1)).decode()
    assert "RP_CERT_DIR=/etc/ssl/infrafoundry" in payload
    assert NODE.read_text() in payload


def test_no_routes_send_an_empty_caddyfile(tmp_path: Path) -> None:
    result, record = _run_config(tmp_path, {"RP_ROUTES": "[]"})

    assert result.returncode == 0, result.stderr
    assert "RP_CADDYFILE_B64=\n" in (record / "payload").read_text()


def test_invalid_routes_warn_and_fail_before_ssh(tmp_path: Path) -> None:
    result, record = _run_config(tmp_path, {"RP_ROUTES": '[{"name": "a", "backend": "ftp://x"}]'})

    assert result.returncode == 1
    assert _calls(record) == []
    assert (tmp_path / "warnings").exists()


def test_node_exit_three_warns_about_certs_issue(tmp_path: Path) -> None:
    result, _record = _run_config(tmp_path, {"FAKE_NODE_RC": "3"})

    assert result.returncode == 3
    assert "foundry certs issue" in (tmp_path / "warnings").read_text()


def test_other_node_failure_warns_and_propagates(tmp_path: Path) -> None:
    result, _record = _run_config(tmp_path, {"FAKE_NODE_RC": "7"})

    assert result.returncode == 7
    assert "exit 7" in (tmp_path / "warnings").read_text()


@pytest.mark.parametrize("script", [CONFIG, NODE])
def test_scripts_are_executable_in_the_tree(script: Path) -> None:
    out = subprocess.run(
        ["git", "ls-files", "-s", str(script)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert out.startswith("100755"), out


# --- node script, run locally against stub tools -------------------------------------


_CADDY = """#!/bin/sh
echo "caddy $*" >> "$RECORD/node_calls"
if [ -n "$FAKE_VALIDATE_FAIL" ]; then exit 1; fi
"""
_SYSTEMCTL = """#!/bin/sh
echo "systemctl $*" >> "$RECORD/node_calls"
case "$1" in is-active) exit "${FAKE_INACTIVE:-0}" ;; esac
"""
_INSTALL = """#!/bin/sh
# install [-d] [-o u] [-g g] [-m m] SRC DEST | -d DIR : copy, ignoring ownership.
dir=""
while [ "${1#-}" != "$1" ]; do
    case "$1" in
    -d) dir=1; shift ;;
    -o|-g|-m) shift 2 ;;
    *) shift ;;
    esac
done
if [ -n "$dir" ]; then mkdir -p "$1"; echo "install -d $1" >> "$RECORD/node_calls"; exit 0; fi
cp "$1" "$2"
echo "install $2" >> "$RECORD/node_calls"
"""


def _run_node(
    tmp_path: Path, caddyfile: str, live: str | None, certs: bool = True, **extra: str
) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
    record = tmp_path / "record"
    record.mkdir()
    _stubs(
        tmp_path / "bin",
        {"caddy": _CADDY, "systemctl": _SYSTEMCTL, "install": _INSTALL},
    )
    cert_dir = tmp_path / "certs"
    cert_dir.mkdir()
    if certs:
        (cert_dir / "proxy.fullchain.pem").write_text("cert")
        (cert_dir / "proxy.key").write_text("key")
    live_path = tmp_path / "Caddyfile"
    if live is not None:
        live_path.write_text(live)
    env = {
        "PATH": f"{tmp_path / 'bin'}:{os.environ['PATH']}",
        "TMPDIR": str(tmp_path),
        "RECORD": str(record),
        "RP_CADDYFILE_B64": base64.b64encode(caddyfile.encode()).decode(),
        "RP_CERT_DIR": str(cert_dir),
        "RP_CADDYFILE_PATH": str(live_path),
        **extra,
    }
    result = subprocess.run(
        ["bash", str(NODE)], env=env, capture_output=True, text=True, check=False, timeout=60
    )
    return result, record, live_path


def _node_calls(record: Path) -> list[str]:
    path = record / "node_calls"
    return path.read_text().splitlines() if path.exists() else []


def test_node_unchanged_caddyfile_does_not_reload(tmp_path: Path) -> None:
    result, record, _live = _run_node(tmp_path, "site\n", live="site\n")

    assert result.returncode == 0, result.stderr
    assert "unchanged" in result.stdout
    assert not any(c.startswith("systemctl reload") for c in _node_calls(record))


def test_node_changed_caddyfile_validates_installs_then_reloads(tmp_path: Path) -> None:
    result, record, live = _run_node(tmp_path, "new\n", live="old\n")

    assert result.returncode == 0, result.stderr
    assert live.read_text() == "new\n"
    calls = _node_calls(record)
    validate = next(i for i, c in enumerate(calls) if c.startswith("caddy validate"))
    installed = next(i for i, c in enumerate(calls) if c.startswith("install ") and "new" in c)
    reload = next(i for i, c in enumerate(calls) if c == "systemctl reload caddy")
    assert validate < installed < reload


def test_node_failed_validate_leaves_the_live_file_alone(tmp_path: Path) -> None:
    result, record, live = _run_node(tmp_path, "bad\n", live="old\n", FAKE_VALIDATE_FAIL="1")

    assert result.returncode != 0
    assert live.read_text() == "old\n"
    assert not any("reload" in c or "restart" in c for c in _node_calls(record))


def test_node_missing_certificate_files_exit_three(tmp_path: Path) -> None:
    result, _record, live = _run_node(tmp_path, "new\n", live="old\n", certs=False)

    assert result.returncode == 3
    assert "foundry certs issue" in result.stderr
    assert live.read_text() == "old\n"


def test_node_inactive_caddy_is_restarted(tmp_path: Path) -> None:
    _result, record, _live = _run_node(tmp_path, "new\n", live=None, FAKE_INACTIVE="1")

    assert "systemctl restart caddy" in _node_calls(record)


def test_node_rejects_a_malformed_payload(tmp_path: Path) -> None:
    result, _record, _live = _run_node(tmp_path, "x\n", live=None, RP_CADDYFILE_B64="a;b")

    assert result.returncode == 1
    assert "malformed" in result.stderr
