"""Preflight checks for packages that run their scripts on a jumphost (#657).

A package that sets ``jumphost`` has its blueprint scripts rsynced to that
host and run there; the scripts then SSH to the package's VMs using the
jumphost's own ssh-agent. When the agent holds no key, or the wrong one, the
failure only shows minutes into an apply, as a wait-loop timeout after
terraform has already created the VMs. ``infra doctor`` runs these checks
first.

All checks for one jumphost run in a single SSH session, opened the way the
script handler opens it, so they see the same login environment (and
ssh-agent) the scripts will.
"""

from __future__ import annotations

import subprocess  # nosec B404 - runs ssh with list args and a fixed remote script
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from infrafoundry.core.provider import ResourceConfig

# Same host-key handling as the script handler's jumphost transport, plus
# BatchMode so a missing key fails instead of prompting.
_SSH_OPTS = [
    "-o",
    "BatchMode=yes",
    "-o",
    "ConnectTimeout=10",
    "-o",
    "StrictHostKeyChecking=no",
]
_TIMEOUT_SECONDS = 60

# The script handler rsyncs scripts into /tmp, runs them with bash and needs
# python3 to export package variables; scripts reach targets with ssh/scp and
# ``outputs:`` are copied back with scp.
REQUIRED_TOOLS = ("rsync", "bash", "python3", "ssh", "scp")

# Each line the remote script prints is "<tag> <value...>".
_REMOTE_SCRIPT = "; ".join(
    [
        "echo 'connect ok'",
        'ssh-add -l >/dev/null 2>&1; echo "agent $?"',
        "ssh-add -L 2>/dev/null | sed 's/^/key /'",
        *(
            f"command -v {tool} >/dev/null 2>&1 && echo 'tool {tool} ok' "
            f"|| echo 'tool {tool} missing'"
            for tool in REQUIRED_TOOLS
        ),
        "d=$(mktemp -d /tmp/infrafoundry-doctor-XXXXXX 2>/dev/null) "
        "&& rmdir \"$d\" && echo 'tmp ok' || echo 'tmp fail'",
        "true",
    ]
)


class Status(StrEnum):
    """Outcome of one preflight check."""

    OK = "OK"
    WARN = "WARN"
    FAIL = "FAIL"
    SKIP = "SKIP"


@dataclass(frozen=True)
class Check:
    """One line of the preflight report."""

    name: str
    status: Status
    detail: str = ""


@dataclass
class JumphostReport:
    """Every check run against one jumphost."""

    jumphost: str
    checks: list[Check] = field(default_factory=list)

    @property
    def failed(self) -> bool:
        """Whether any check failed."""
        return any(c.status is Status.FAIL for c in self.checks)


def _key_id(line: str) -> tuple[str, str] | None:
    """Return ``(type, base64)`` of an OpenSSH public key line, ignoring the comment."""
    parts = line.split()
    return (parts[0], parts[1]) if len(parts) >= 2 else None


def _declared_keys(resource: ResourceConfig) -> list[str]:
    """Public keys the package puts on its VMs, where it declares them."""
    keys: list[str] = []
    declared = (resource.package_variables or {}).get("ssh_public_key")
    if isinstance(declared, str) and declared.strip():
        keys.append(declared.strip())
    ssh_keys = resource.config.get("ssh_keys")
    if isinstance(ssh_keys, list):
        keys.extend(str(k).strip() for k in ssh_keys if str(k).strip())
    return keys


def jumphosts_to_check(resources: Iterable[ResourceConfig]) -> dict[str, list[str]]:
    """Group the resources' jumphosts with the public keys their VMs expect.

    Args:
        resources: The resources in scope for the doctor run.

    Returns:
        ``{jumphost: [public key, ...]}`` in first-seen order, keys
        de-duplicated. Resources whose package sets no jumphost are left out;
        a jumphost whose packages declare no key maps to an empty list.
    """
    result: dict[str, list[str]] = {}
    for resource in resources:
        jumphost = str((resource.package_variables or {}).get("jumphost", "")).strip()
        if not jumphost:
            continue
        keys = result.setdefault(jumphost, [])
        for key in _declared_keys(resource):
            if key not in keys:
                keys.append(key)
    return result


def _parse(output: str) -> dict[str, Any]:
    parsed: dict[str, Any] = {"connect": False, "agent": None, "keys": [], "tools": {}}
    for line in output.splitlines():
        tag, _, value = line.strip().partition(" ")
        if tag == "connect":
            parsed["connect"] = True
        elif tag == "agent" and value.strip().isdigit():
            parsed["agent"] = int(value)
        elif tag == "key":
            parsed["keys"].append(value)
        elif tag == "tool":
            name, _, state = value.partition(" ")
            parsed["tools"][name] = state == "ok"
        elif tag == "tmp":
            parsed["tmp"] = value == "ok"
    return parsed


def _agent_check(code: int | None, loaded: int) -> Check:
    if code == 0:
        return Check("ssh-agent", Status.OK, f"{loaded} key(s) loaded")
    if code == 1:
        return Check("ssh-agent", Status.FAIL, "agent is running but has no keys loaded")
    return Check("ssh-agent", Status.FAIL, "no ssh-agent reachable (SSH_AUTH_SOCK unset or stale)")


def _key_checks(expected: list[str], loaded: list[str]) -> list[Check]:
    if not expected:
        return [Check("key match", Status.SKIP, "package declares no public key to compare")]
    loaded_ids = {_key_id(k) for k in loaded}
    checks = []
    for key in expected:
        key_id = _key_id(key)
        label = " ".join(key.split()[2:]) or (key_id[0] if key_id else key[:20])
        if key_id in loaded_ids:
            checks.append(Check(f"key match: {label}", Status.OK))
        else:
            checks.append(
                Check(f"key match: {label}", Status.FAIL, "not loaded in the jumphost's agent")
            )
    return checks


def check_jumphost(
    jumphost: str,
    expected_keys: list[str],
    run: Callable[..., subprocess.CompletedProcess[Any]] = subprocess.run,
) -> JumphostReport:
    """Run the preflight checks against *jumphost* in one SSH session.

    Args:
        jumphost: SSH destination, as in the package's ``jumphost`` variable.
        expected_keys: Public keys the package's VMs accept; at least one must
            match each declared key in the jumphost's agent.
        run: ``subprocess.run`` or a stand-in for tests.

    Returns:
        The report. When the jumphost can't be reached, it holds that single
        failed check.
    """
    report = JumphostReport(jumphost)
    try:
        result = run(
            ["ssh", *_SSH_OPTS, jumphost, _REMOTE_SCRIPT],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        report.checks.append(
            Check("SSH to jumphost", Status.FAIL, f"timed out after {_TIMEOUT_SECONDS}s")
        )
        return report
    except OSError as e:
        report.checks.append(Check("SSH to jumphost", Status.FAIL, f"could not run ssh: {e}"))
        return report

    parsed = _parse(result.stdout or "")
    if result.returncode != 0 or not parsed["connect"]:
        detail = (result.stderr or "").strip().splitlines()
        report.checks.append(
            Check(
                "SSH to jumphost",
                Status.FAIL,
                f"ssh exited {result.returncode}" + (f": {detail[-1]}" if detail else ""),
            )
        )
        return report

    report.checks.append(Check("SSH to jumphost", Status.OK))
    report.checks.append(_agent_check(parsed["agent"], len(parsed["keys"])))
    if parsed["agent"] == 0:
        report.checks.extend(_key_checks(expected_keys, parsed["keys"]))
    missing = [t for t in REQUIRED_TOOLS if not parsed["tools"].get(t, False)]
    if missing:
        report.checks.append(Check("tools", Status.FAIL, "missing: " + ", ".join(missing)))
    else:
        report.checks.append(Check("tools", Status.OK, ", ".join(REQUIRED_TOOLS)))
    if parsed.get("tmp"):
        report.checks.append(Check("writable /tmp", Status.OK))
    else:
        report.checks.append(Check("writable /tmp", Status.FAIL, "cannot create a dir in /tmp"))
    return report
