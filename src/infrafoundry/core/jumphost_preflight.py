"""Preflight checks for packages that run their scripts on a jumphost (#657).

A package that sets ``jumphost`` has its blueprint scripts rsynced to that
host and run there; the scripts then SSH to the package's VMs using the
jumphost's own ssh-agent. When the agent holds no key, or the wrong one, the
failure only shows minutes into an apply, as a wait-loop timeout after
terraform has already created the VMs. ``infra doctor`` runs these checks
first.

Targets are the package's VMs that have a DHCP reservation (the same lookup
``known_hosts`` uses). A deployed target must accept SSH from the jumphost; a
target that is not deployed yet must have a route from the jumphost and an
address nothing answers on. ``outputs:`` destinations are checked on the
workstation, where the script handler copies them.

All checks for one jumphost run in a single SSH session, opened the way the
script handler opens it, so they see the same login environment (and
ssh-agent) the scripts will.
"""

from __future__ import annotations

import os
import shlex
import subprocess  # nosec B404 - runs ssh with list args; remote values are shlex-quoted
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

import jinja2

from infrafoundry.core.config.filters import create_jinja2_env
from infrafoundry.core.known_hosts import RESERVATION_TYPE, reservation_ips
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.state.models import ResourceState

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

# Target SSH uses the blueprint scripts' options: host keys are not checked
# and not recorded, so a reused IP can't block them.
_TARGET_SSH = (
    "ssh -o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=no "
    "-o UserKnownHostsFile=/dev/null"
)

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


@dataclass(frozen=True)
class Target:
    """A package VM the jumphost's scripts will SSH to."""

    name: str
    ip: str
    user: str | None
    deployed: bool | None
    """``True`` if deployed, ``False`` if not yet, ``None`` if the state is in between."""


class _StateLookup(Protocol):
    def get_resources(self, environment: str | None = None) -> list[Any]: ...


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


def deployment_state(state: _StateLookup, env: str) -> Callable[[ResourceConfig], bool | None]:
    """Return a lookup telling whether a resource is deployed, from the state DB.

    The DB keeps a row per deployment, and every ``infra plan`` adds a
    ``planned`` row, so the newest row is not the deployment state. The
    lookup uses each resource's newest row that is not ``planned``.

    Args:
        state: The state manager.
        env: Environment name.

    Returns:
        A function giving ``True`` for active or updating resources, ``False``
        for untracked or deleted ones, and ``None`` otherwise (creating,
        deleting or in error).
    """
    latest: dict[tuple[str, str], Any] = {}
    for record in state.get_resources(environment=env):
        if record.state == ResourceState.PLANNED:
            continue
        key = (record.provider, record.name)
        if key not in latest or record.created_at > latest[key].created_at:
            latest[key] = record

    def lookup(resource: ResourceConfig) -> bool | None:
        record = latest.get((resource.provider, resource.name))
        if record is None or record.state == ResourceState.DELETED:
            return False
        if record.state in (ResourceState.ACTIVE, ResourceState.UPDATING):
            return True
        return None

    return lookup


def targets_by_jumphost(
    resources: Iterable[ResourceConfig],
    all_resources: Iterable[ResourceConfig],
    deployed: Callable[[ResourceConfig], bool | None],
) -> dict[str, list[Target]]:
    """Find the VMs each jumphost's scripts will reach.

    Args:
        resources: The resources in scope for the doctor run.
        all_resources: Every resource in the environment, used to find the
            DHCP reservation that gives a VM its IP.
        deployed: Deployment-state lookup, see :func:`deployment_state`.

    Returns:
        ``{jumphost: [Target, ...]}``. A resource is a target when its
        package sets ``jumphost`` and a reservation's ``hostname`` equals its
        name. The SSH user is the package's ``ssh_user``, else the user part
        of ``jumphost``.
    """
    ips = reservation_ips(all_resources)
    result: dict[str, list[Target]] = {}
    for resource in resources:
        pkg_vars = resource.package_variables or {}
        jumphost = str(pkg_vars.get("jumphost", "")).strip()
        if not jumphost or resource.type == RESERVATION_TYPE:
            continue
        user = str(pkg_vars.get("ssh_user", "")).strip() or (
            jumphost.split("@", 1)[0] if "@" in jumphost else None
        )
        state = deployed(resource)
        for ip in ips.get(resource.name, []):
            result.setdefault(jumphost, []).append(Target(resource.name, ip, user, state))
    return result


def _target_lines(targets: Sequence[Target]) -> list[str]:
    lines: list[str] = []
    for i, target in enumerate(targets):
        if target.deployed and target.user:
            dest = shlex.quote(f"{target.user}@{target.ip}")
            # Keep ssh's last error line: it says why ("Permission denied", ...).
            lines.append(
                f"o=$({_TARGET_SSH} {dest} true 2>&1 </dev/null); c=$?; "
                f'echo "target {i} ssh $c"; '
                f"[ \"$c\" -eq 0 ] || printf 'target-error {i} %s\\n' "
                f'"$(printf \'%s\' "$o" | tail -n 1)"'
            )
        elif target.deployed is False:
            ip = shlex.quote(target.ip)
            lines.append(f'ip route get {ip} >/dev/null 2>&1; echo "target {i} route $?"')
            lines.append(f'ping -c 1 -W 1 {ip} >/dev/null 2>&1; echo "target {i} ping $?"')
    return lines


def _target_check(target: Target, codes: dict[str, int], error: str = "") -> Check:
    name = f"target {target.name} ({target.ip})"
    if target.deployed is None:
        return Check(name, Status.SKIP, "deployment in progress or failed; not checked")
    if target.deployed:
        if not target.user:
            return Check(name, Status.SKIP, "no ssh_user, and jumphost has no user@ part")
        code = codes.get("ssh")
        if code == 0:
            return Check(name, Status.OK, f"ssh as {target.user}")
        reason = f": {error}" if error else ""
        return Check(name, Status.FAIL, f"ssh as {target.user} failed (exit {code}){reason}")
    if codes.get("route") == 127:
        return Check(name, Status.WARN, "not deployed; 'ip' missing on the jumphost")
    if codes.get("route") != 0:
        return Check(name, Status.FAIL, "not deployed; no route from the jumphost")
    if codes.get("ping") == 0:
        return Check(name, Status.FAIL, "not deployed, but something answers at this IP")
    return Check(name, Status.OK, "not deployed; routable and unused")


def output_checks(
    handlers: Iterable[dict[str, Any]],
    resources: Iterable[ResourceConfig],
) -> dict[str, list[Check]]:
    """Check that each in-scope ``outputs:`` destination can be written.

    A destination that can't be written only warns during an apply, as
    the script handler does, so these checks WARN rather than FAIL.

    Args:
        handlers: Package event handler configs (``get_package_events``).
        resources: The resources in scope; a handler is in scope when one of
            its ``requires`` is, and that resource's package variables render
            the destination.

    Returns:
        ``{jumphost: [Check, ...]}`` for handlers whose package sets a jumphost.
    """
    by_name = {r.name: r for r in resources}
    template_env = create_jinja2_env(undefined=jinja2.StrictUndefined)
    result: dict[str, list[Check]] = {}
    seen: set[tuple[str, str]] = set()
    for handler in handlers:
        outputs = handler.get("outputs") or []
        owner = next((by_name[n] for n in handler.get("requires") or [] if n in by_name), None)
        if not outputs or owner is None:
            continue
        pkg_vars = owner.package_variables or {}
        jumphost = str(pkg_vars.get("jumphost", "")).strip()
        if not jumphost:
            continue
        for entry in outputs:
            raw = str(entry.get("dest", ""))
            if (jumphost, raw) in seen:
                continue
            seen.add((jumphost, raw))
            result.setdefault(jumphost, []).append(_output_check(template_env, raw, pkg_vars))
    return result


def _output_check(template_env: jinja2.Environment, raw: str, pkg_vars: dict[str, Any]) -> Check:
    try:
        rendered = template_env.from_string(raw).render(**pkg_vars)
    except jinja2.TemplateError as e:
        return Check(f"output {raw}", Status.WARN, f"does not render: {e}")
    name = f"output {rendered}"
    dest = Path(rendered).expanduser()
    if not dest.is_absolute():
        return Check(name, Status.WARN, "not an absolute path")
    if dest.exists():
        if os.access(dest, os.W_OK):
            return Check(name, Status.OK, "exists, writable")
        return Check(name, Status.WARN, "exists but is not writable")
    ancestor = dest.parent
    while not ancestor.exists():
        ancestor = ancestor.parent
    if ancestor.is_dir() and os.access(ancestor, os.W_OK | os.X_OK):
        return Check(name, Status.OK)
    return Check(name, Status.WARN, f"{ancestor} is not a writable directory")


def _parse(output: str) -> dict[str, Any]:
    parsed: dict[str, Any] = {
        "connect": False,
        "agent": None,
        "keys": [],
        "tools": {},
        "targets": {},
        "target_errors": {},
    }
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
        elif tag == "target-error":
            index, _, message = value.partition(" ")
            if index.isdigit():
                parsed["target_errors"][int(index)] = message.strip()
        elif tag == "target":
            index, kind, code = [*value.split(), "", "", ""][:3]
            if index.isdigit() and code.isdigit():
                parsed["targets"].setdefault(int(index), {})[kind] = int(code)
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
    targets: Sequence[Target] = (),
    run: Callable[..., subprocess.CompletedProcess[Any]] = subprocess.run,
) -> JumphostReport:
    """Run the preflight checks against *jumphost* in one SSH session.

    Args:
        jumphost: SSH destination, as in the package's ``jumphost`` variable.
        expected_keys: Public keys the package's VMs accept; at least one must
            match each declared key in the jumphost's agent.
        targets: VMs the scripts will reach, see :func:`targets_by_jumphost`.
        run: ``subprocess.run`` or a stand-in for tests.

    Returns:
        The report. When the jumphost can't be reached, it holds that single
        failed check.
    """
    report = JumphostReport(jumphost)
    try:
        result = run(
            ["ssh", *_SSH_OPTS, jumphost, "; ".join([_REMOTE_SCRIPT, *_target_lines(targets)])],
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
    for i, target in enumerate(targets):
        report.checks.append(
            _target_check(target, parsed["targets"].get(i, {}), parsed["target_errors"].get(i, ""))
        )
    return report
