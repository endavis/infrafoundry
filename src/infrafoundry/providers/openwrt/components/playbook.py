"""Builders for the generated ``openwrt.yml`` playbook.

The playbook is built as Python dicts and dumped with ``yaml.safe_dump``, never from a
text template, so a user value cannot break the YAML or inject a task.

Shape of a run (one play against the inventory's single device):

1. Preflight: fail when UCI changes are already pending, so a run never commits
   someone else's staged edits.
2. A block of staging tasks (``community.openwrt.uci``, ``replace: false``), one per
   resource, named ``infrafoundry|<type>|<name>`` and tagged with the resource name.
3. In the same block, outside check mode and only when something was staged, the
   commit tail: hand the staged changes to an rpcd session, ``ubus call uci apply``
   with rollback, reconnect, then ``ubus call uci confirm``. A device that cannot be
   reached afterwards reverts by itself after the timeout.
4. A rescue that reverts the staging when the apply was not reached and otherwise
   reports ``INFRAFOUNDRY_ROLLBACK_PENDING``.

The ubus sequence was measured on a device running OpenWrt 23.05: a CLI call has no
session, so the tail creates one, grants it the uci scope, copies the staged config
files into its save dir, reverts the CLI staging, and applies in that session.
"""

from __future__ import annotations

from typing import Any

import yaml

from ..schema import SPECS, Desired, mac_variants
from ..settings import OpenWrtSettings

TASK_PREFIX = "infrafoundry"
ROLLBACK_MARKER = "INFRAFOUNDRY_ROLLBACK_PENDING"
PLAYBOOK_NAME = "openwrt.yml"
CONFIGS = ("network", "dhcp", "firewall")
SESSION_GRACE = 300
"""Seconds the rpcd session outlives the rollback timeout."""

UCI = "community.openwrt.uci"
RAW = "ansible.builtin.raw"
_ALWAYS = ["always"]
_NOT_CHECK = "not ansible_check_mode"
_APPLIED = "(infrafoundry_applied | default(false) | bool)"
_SESSION_RE = "^[0-9a-f]{32}$"


def task_name(item: Desired) -> str:
    """Return the task name that identifies a resource in the run's JSON output."""
    if item.absent:
        return f"{TASK_PREFIX}|absent|{item.type_name}|{item.name}"
    return f"{TASK_PREFIX}|{item.type_name}|{item.name}"


def staging_task(item: Desired) -> dict[str, Any]:
    """Return the task that sets one resource's options without replacing the section."""
    spec = item.spec
    args: dict[str, Any] = {
        "command": "section",
        "config": spec.config,
        "type": spec.section_type,
        "value": dict(item.values),
        "replace": False,
    }
    if spec.named:
        args["name"] = item.key
    else:
        args["find"] = {spec.find_option: item.key}
    return {"name": task_name(item), UCI: args, "tags": [item.name]}


def absent_task(item: Desired) -> dict[str, Any]:
    """Return the task that deletes one resource's section when it exists."""
    spec = item.spec
    args: dict[str, Any] = {"command": "absent", "config": spec.config, "type": spec.section_type}
    if spec.named:
        args["section"] = item.key
    else:
        args["find"] = {spec.find_option: item.key}
    return {"name": task_name(item), UCI: args, "tags": [item.name]}


def lease_guard_tasks(item: Desired, index: int) -> list[dict[str, Any]]:
    """Return the guards that fail the run when a lease cannot be matched safely.

    A ``find`` by MAC adopts a lease made in the vendor UI. It fails when more than one
    ``host`` section carries the MAC, or when one carries the other-case form of it
    (``uci`` compares strings exactly, so it would create a second lease).
    """
    mac = item.key
    guards: list[dict[str, Any]] = []
    checks: list[tuple[str, str, str]] = [("duplicate", mac, "> 1")]
    for position, variant in enumerate(v for v in mac_variants(mac) if v != mac):
        checks.append((f"case-{position}", variant, "> 0"))
    for label, value, condition in checks:
        register = f"infrafoundry_guard_{index}_{label.replace('-', '_')}"
        guards.append(
            {
                "name": f"{TASK_PREFIX}|guard|{item.name}|{label}",
                UCI: {
                    "command": "find_all",
                    "config": "dhcp",
                    "type": "host",
                    "find": {"mac": value},
                },
                "register": register,
                "changed_when": False,
                "tags": [item.name],
            }
        )
        message = (
            f"more than one dhcp host section has MAC {mac}; remove the duplicates first"
            if label == "duplicate"
            else f"a dhcp host section already has MAC {value}, the other-case form of {mac}; "
            "use one spelling"
        )
        guards.append(
            {
                "name": f"{TASK_PREFIX}|guard|{item.name}|{label}-fail",
                "ansible.builtin.fail": {"msg": message},
                "when": f"({register}.result_list | default([])) | length {condition}",
                "tags": [item.name],
            }
        )
    return guards


def preflight_tasks() -> list[dict[str, Any]]:
    """Return the tasks that refuse to run when UCI changes are already pending."""
    tasks: list[dict[str, Any]] = [
        {
            "name": f"{TASK_PREFIX}|preflight|{config}",
            UCI: {"command": "changes", "config": config},
            "register": f"infrafoundry_pending_{config}",
            "changed_when": False,
            "tags": list(_ALWAYS),
        }
        for config in CONFIGS
    ]
    pending = " or ".join(
        f"((infrafoundry_pending_{config}.changes | default({{}})) | length > 0)"
        for config in CONFIGS
    )
    tasks.append(
        {
            "name": f"{TASK_PREFIX}|preflight|fail",
            "ansible.builtin.fail": {
                "msg": "UCI changes are already pending on the device "
                f"({', '.join(CONFIGS)}); commit or revert them before this run"
            },
            "when": pending,
            "tags": list(_ALWAYS),
        }
    )
    return tasks


def _ubus(method: str, payload: str) -> str:
    return f"ubus call {method} '{payload}'"


def _session_payload(extra: str = "") -> str:
    return '{"ubus_rpc_session":"{{ infrafoundry_session }}"' + extra + "}"


def _raw(name: str, command: str, **extra: Any) -> dict[str, Any]:
    task: dict[str, Any] = {"name": f"{TASK_PREFIX}|commit|{name}", RAW: command}
    task.update(extra)
    return task


def commit_tail(settings: OpenWrtSettings) -> list[dict[str, Any]]:
    """Return the tasks that commit the staged changes with rollback and confirm them.

    Args:
        settings: Supplies the rollback timeout and the reconnect timeout.
    """
    timeout = settings.rollback_timeout
    handoff = (
        "set -e\n"
        "S={{ infrafoundry_session }}\n"
        "mkdir -p /var/run/rpcd/uci-$S\n"
        f"for c in {' '.join(CONFIGS)}; do\n"
        '  if [ -f /tmp/.uci/$c ]; then cp /tmp/.uci/$c "/var/run/rpcd/uci-$S/$c" '
        "&& uci revert $c; fi\n"
        "done\n"
    )
    grant = (
        '{"ubus_rpc_session":"{{ infrafoundry_session }}","scope":"uci",'
        '"objects":[["*","read"],["*","write"]]}'
    )
    apply_payload = _session_payload(f',"rollback":true,"timeout":{timeout}')
    inner: list[dict[str, Any]] = [
        _raw(
            "create-session",
            "ubus call session create "
            f"'{{\"timeout\":{timeout + SESSION_GRACE}}}' | jsonfilter -e @.ubus_rpc_session",
            register="infrafoundry_session_raw",
            changed_when=False,
            failed_when=(
                "(infrafoundry_session_raw.stdout | default('') | trim) "
                f"is not match('{_SESSION_RE}')"
            ),
        ),
        {
            "name": f"{TASK_PREFIX}|commit|remember-session",
            "ansible.builtin.set_fact": {
                "infrafoundry_session": "{{ infrafoundry_session_raw.stdout | trim }}"
            },
        },
        _raw("grant-session", _ubus("session grant", grant), changed_when=False),
        _raw("hand-over-staged", handoff),
        _raw(
            "apply-with-rollback",
            _ubus("uci apply", apply_payload),
            register="infrafoundry_apply",
            ignore_unreachable=True,
            failed_when=False,
        ),
        {
            "name": f"{TASK_PREFIX}|commit|record-apply",
            "ansible.builtin.set_fact": {
                "infrafoundry_applied": "{{ (infrafoundry_apply.unreachable | default(false)) "
                "or ((infrafoundry_apply.rc | default(1)) == 0) }}"
            },
        },
        {
            "name": f"{TASK_PREFIX}|commit|apply-failed",
            "ansible.builtin.fail": {
                "msg": "ubus uci apply did not run; nothing was committed: "
                "{{ infrafoundry_apply.stderr | default('') | trim }}"
            },
            "when": "not (infrafoundry_applied | bool)",
        },
        {
            "name": f"{TASK_PREFIX}|commit|use-new-address",
            "ansible.builtin.set_fact": {"ansible_host": "{{ infrafoundry_reconnect_host }}"},
            "when": "infrafoundry_reconnect_host is defined",
        },
        {
            "name": f"{TASK_PREFIX}|commit|reset-connection",
            "ansible.builtin.meta": "reset_connection",
        },
        {
            "name": f"{TASK_PREFIX}|commit|wait-for-device",
            "community.openwrt.wait_for_connection": {
                "timeout": settings.reconnect_timeout,
                "connect_timeout": settings.connect_timeout,
            },
        },
        _raw("confirm", _ubus("uci confirm", _session_payload())),
        _raw(
            "destroy-session",
            _ubus("session destroy", _session_payload()),
            changed_when=False,
            failed_when=False,
        ),
    ]
    return [
        {
            "name": f"{TASK_PREFIX}|commit|detect-staged",
            RAW: "for c in " + " ".join(CONFIGS) + "; do if [ -s /tmp/.uci/$c ]; then echo $c; fi; "
            "done; true",
            "register": "infrafoundry_staged_raw",
            "changed_when": False,
            "when": _NOT_CHECK,
            "tags": list(_ALWAYS),
        },
        {
            "name": f"{TASK_PREFIX}|commit|staged",
            "ansible.builtin.set_fact": {
                "infrafoundry_staged": "{{ infrafoundry_staged_raw.stdout_lines | default([]) }}"
            },
            "when": _NOT_CHECK,
            "tags": list(_ALWAYS),
        },
        {
            "name": f"{TASK_PREFIX}|commit|tail",
            "block": inner,
            "when": f"{_NOT_CHECK} and ((infrafoundry_staged | default([])) | length > 0)",
            "tags": list(_ALWAYS),
        },
    ]


def rescue_tasks(settings: OpenWrtSettings) -> list[dict[str, Any]]:
    """Return the rescue: revert unapplied staging, or report a pending rollback."""
    guard = f"{_NOT_CHECK} and not {_APPLIED}"
    return [
        {
            "name": f"{TASK_PREFIX}|rescue|revert-staged",
            UCI: {"command": "revert", "config": "{{ item }}"},
            "loop": list(CONFIGS),
            "when": guard,
            "ignore_errors": True,
            "ignore_unreachable": True,
            "tags": list(_ALWAYS),
        },
        {
            "name": f"{TASK_PREFIX}|rescue|destroy-session",
            RAW: _ubus("session destroy", _session_payload()),
            "when": f"{guard} and infrafoundry_session is defined",
            "ignore_errors": True,
            "ignore_unreachable": True,
            "tags": list(_ALWAYS),
        },
        {
            "name": f"{TASK_PREFIX}|rescue|rollback-pending",
            "ansible.builtin.fail": {
                "msg": f"{ROLLBACK_MARKER}: the device did not confirm within "
                f"{settings.rollback_timeout} s and reverts the change by itself"
            },
            "when": _APPLIED,
            "tags": list(_ALWAYS),
        },
        {
            "name": f"{TASK_PREFIX}|rescue|failed-before-apply",
            "ansible.builtin.fail": {
                "msg": "the run failed before the change was applied; staged changes were "
                "reverted: {{ ansible_failed_result.msg | default('') }}"
            },
            "when": f"not {_APPLIED}",
            "tags": list(_ALWAYS),
        },
    ]


def build_playbook(settings: OpenWrtSettings, items: list[Desired]) -> list[dict[str, Any]]:
    """Return the play for one run.

    Args:
        settings: Device settings (rollback timeout).
        items: Objects to stage or delete, in run order.
    """
    order = {name: index for index, name in enumerate(SPECS)}
    ordered = sorted(items, key=lambda i: (i.absent, order[i.type_name]))
    staging: list[dict[str, Any]] = []
    for index, item in enumerate(ordered):
        if item.absent:
            staging.append(absent_task(item))
            continue
        if item.type_name == "dhcp.host":
            staging.extend(lease_guard_tasks(item, index))
        staging.append(staging_task(item))
    block: dict[str, Any] = {
        "name": f"{TASK_PREFIX}|run",
        "block": [*staging, *commit_tail(settings)],
        "rescue": rescue_tasks(settings),
    }
    return [
        {
            "name": "infrafoundry openwrt",
            "hosts": "all",
            "gather_facts": False,
            "tasks": [*preflight_tasks(), block],
        }
    ]


def dump_playbook(play: list[dict[str, Any]]) -> str:
    """Render the play as YAML text."""
    return yaml.safe_dump(play, sort_keys=False, width=100)
