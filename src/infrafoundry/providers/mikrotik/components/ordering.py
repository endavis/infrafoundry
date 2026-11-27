"""Pure ordering and lock-out checks for MikroTik plans.

A bridge with VLAN filtering on drops traffic it has no VLAN entry for, so the
order of changes decides whether the operator keeps the management connection.
The phases are:

* A: disable ``vlan-filtering`` on bridges going on to off
* B: creates in dependency order, certificate signing (a created or unsigned
  certificate is signed right after its create), bridge VLAN membership widened to old and new,
  port PVID updates on bridges whose filtering is off at that moment
* C: enable ``vlan-filtering`` on bridges going off to on
* D: narrowing: exact bridge VLAN membership, PVID updates on filtering bridges,
  other updates
* E: deletes in reverse dependency order
* F: ``ip.service`` updates

Changes that touch the live management path sort last inside D and E. Everything
here is a function of its arguments; no client is involved.
"""

from __future__ import annotations

import ipaddress
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from ..schema import (
    DEPENDENCY_ORDER,
    KIND_LIST,
    SPECS,
    ResourceSpec,
    key_of,
    normalize_value,
    parse_vlan_ids,
    to_rest_value,
)
from .diff import CREATE, DELETE, SIGN, UPDATE, Change, TypeDiff

PHASES = "ABCDEF"
PHASE_TITLES = {
    "A": "disable vlan-filtering",
    "B": "create and widen",
    "C": "enable vlan-filtering",
    "D": "narrow and update",
    "E": "delete",
    "F": "services",
}

_BRIDGE = "interface.bridge"
_PORT = "interface.bridge.port"
_BVLAN = "interface.bridge.vlan"
_VLAN = "interface.vlan"
_ADDR = "ip.address"
_SERVICE = "ip.service"
_CERTIFICATE = "certificate"
_MEMBER_FIELDS = ("tagged", "untagged")

LiveState = Mapping[str, list[dict[str, str]]]
IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address


@dataclass(frozen=True)
class Step:
    """One REST write the apply will perform."""

    phase: str
    kind: str
    type_name: str
    key: tuple[Any, ...]
    resource_name: str
    live_id: str | None
    body: dict[str, str]
    note: str = ""
    management: bool = False


@dataclass(frozen=True)
class ManagementPath:
    """The live objects the management connection runs over."""

    address: str | None = None
    interface: str | None = None
    vlan_id: int | None = None
    bridge: str | None = None


@dataclass
class PathCheck:
    """Reasons to refuse a plan, and warnings that do not block it."""

    refusals: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _bool(row: Mapping[str, str], name: str, default: bool = False) -> bool:
    value = row.get(name)
    return default if value is None else bool(normalize_value("bool", value, name))


def _set(row: Mapping[str, str], name: str) -> frozenset[str]:
    value = normalize_value(KIND_LIST, row.get(name, ""), name)
    return value if isinstance(value, frozenset) else frozenset()


def _vlans(row: Mapping[str, str]) -> frozenset[int]:
    try:
        return parse_vlan_ids(row.get("vlan-ids", ""))
    except ValueError:
        return frozenset()


def _pvid(row: Mapping[str, str]) -> int:
    try:
        return int(row.get("pvid", "1"))
    except ValueError:
        return 1


def _body(spec: ResourceSpec, fields: Mapping[str, Any], names: Any) -> dict[str, str]:
    return {n: to_rest_value(spec.fields[n], fields[n]) for n in names if n in fields}


def live_management_path(live: LiveState, mgmt_ip: IPAddress | None) -> ManagementPath:
    """Find the live address, interface and VLAN the management address sits on."""
    if mgmt_ip is None:
        return ManagementPath()
    for row in live.get(_ADDR, []):
        try:
            network = ipaddress.ip_interface(row.get("address", "")).network
        except ValueError:
            continue
        if mgmt_ip not in network:
            continue
        name = row.get("interface")
        vlan = next((r for r in live.get(_VLAN, []) if r.get("name") == name), None)
        if vlan is not None:
            try:
                vid = int(vlan.get("vlan-id", ""))
            except ValueError:
                vid = None
            return ManagementPath(row.get("address"), name, vid, vlan.get("interface"))
        bridge = name if any(b.get("name") == name for b in live.get(_BRIDGE, [])) else None
        return ManagementPath(row.get("address"), name, None, bridge)
    return ManagementPath()


def _touches(change: Change, path: ManagementPath, live: LiveState) -> bool:
    """True when a change affects the live management path."""
    if path.address is None:
        return False
    first = change.key[0]
    match change.type_name:
        case "ip.address":
            return bool(first == path.address)
        case "interface.vlan":
            return bool(first == path.interface)
        case "interface.bridge":
            return bool(first == path.bridge)
        case "interface.bridge.vlan":
            return first == path.bridge and path.vlan_id in change.key[1]
        case "interface.bridge.port":
            return _port_bridge(change, live) == path.bridge
    return False


def _port_bridge(change: Change, live: LiveState) -> str | None:
    bridge = change.after.get("bridge") or change.before.get("bridge")
    return str(bridge) if bridge else None


def order_changes(
    diffs: Mapping[str, TypeDiff],
    live: LiveState,
    path: ManagementPath | None = None,
) -> list[Step]:
    """Turn per-type diffs into the ordered list of writes.

    Args:
        diffs: Diff per type.
        live: Live rows per type (bridge filtering state, bridge VLAN members).
        path: The live management path; its changes sort last within D and E.

    Returns:
        Steps ordered by phase, then dependency order.
    """
    path = path or ManagementPath()
    bridges_live = {r.get("name", ""): _bool(r, "vlan-filtering") for r in live.get(_BRIDGE, [])}
    going_off = {
        c.key[0]
        for c in diffs.get(_BRIDGE, TypeDiff(_BRIDGE)).changes
        if c.kind == UPDATE
        and "vlan-filtering" in c.changed
        and not _bool(c.after, "vlan-filtering")
    }

    def filtering_in_b(bridge: str | None) -> bool:
        return bool(bridge) and bridges_live.get(str(bridge), False) and bridge not in going_off

    steps: list[Step] = []

    def add(
        phase: str, change: Change, body: dict[str, str], note: str = "", *, kind: str | None = None
    ) -> None:
        steps.append(
            Step(
                phase,
                kind or change.kind,
                change.type_name,
                change.key,
                change.resource_name,
                change.live_id,
                body,
                note,
                _touches(change, path, live),
            )
        )

    for type_name, diff in diffs.items():
        spec = SPECS[type_name]
        for change in diff.changes:
            fields = change.after
            if change.kind == DELETE:
                add("E", change, {})
            elif change.kind == SIGN:
                add("B", change, {}, "sign")
            elif type_name == _SERVICE:
                add("F", change, _body(spec, fields, change.changed))
            elif change.kind == CREATE:
                body = _body(spec, fields, fields)
                if type_name == _BRIDGE and _bool(fields, "vlan-filtering"):
                    body["vlan-filtering"] = "no"
                    add(
                        "C", change, {"vlan-filtering": "yes"}, "enable vlan-filtering", kind=UPDATE
                    )
                add("B", change, body)
                if type_name == _CERTIFICATE:
                    add("B", change, {}, "sign", kind=SIGN)
            elif type_name == _BRIDGE:
                rest = [n for n in change.changed if n != "vlan-filtering"]
                if "vlan-filtering" in change.changed:
                    on = _bool(fields, "vlan-filtering")
                    add("C" if on else "A", change, {"vlan-filtering": "yes" if on else "no"})
                if rest:
                    add("D", change, _body(spec, fields, rest))
            elif type_name == _BVLAN:
                _bridge_vlan_update(spec, change, add)
            elif type_name == _PORT:
                rest = [n for n in change.changed if n != "pvid"]
                if "pvid" in change.changed:
                    phase = "B" if not filtering_in_b(_port_bridge(change, live)) else "D"
                    add(phase, change, _body(spec, fields, ["pvid"]))
                if rest:
                    add("D", change, _body(spec, fields, rest))
            else:
                add("D", change, _body(spec, fields, change.changed))

    return sorted(steps, key=_sort_key)


def _bridge_vlan_update(spec: ResourceSpec, change: Change, add: Any) -> None:
    """Split a bridge VLAN update into a widening step (B) and an exact step (D)."""
    widen: dict[str, str] = {}
    exact: dict[str, str] = {}
    for name in change.changed:
        if name not in _MEMBER_FIELDS:
            exact[name] = to_rest_value(spec.fields[name], change.after[name])
            continue
        before = _set(change.before, name)
        after = normalize_value(KIND_LIST, change.after[name], name)
        union = before | after
        if union != before:
            widen[name] = ",".join(sorted(union))
        if union != after:
            exact[name] = ",".join(sorted(after))
    if widen:
        add("B", change, widen, "widen membership")
    if exact:
        add("D", change, exact, "exact membership" if widen else "")


def _sort_key(step: Step) -> tuple[int, int, int, int]:
    phase = PHASES.index(step.phase)
    order = DEPENDENCY_ORDER.index(step.type_name)
    if step.phase == "E":
        order = -order
    kind = 0 if step.kind == CREATE else 1
    late = int(step.management) if step.phase in ("D", "E") else 0
    return (phase, late, order, kind)


def end_state(diffs: Mapping[str, TypeDiff], live: LiveState) -> dict[str, list[dict[str, str]]]:
    """Lay the planned changes over the live rows; undeclared live rows stay.

    Args:
        diffs: Diff per type.
        live: Live rows per type.

    Returns:
        Rows per type as RouterOS strings.
    """
    result: dict[str, list[dict[str, str]]] = {}
    for type_name, spec in SPECS.items():
        changes = {c.key: c for c in diffs.get(type_name, TypeDiff(type_name)).changes}
        rows: list[dict[str, str]] = []
        for row in live.get(type_name, []):
            change = changes.pop(key_of(spec, row) or (), None)
            if change is not None and change.kind == DELETE:
                continue
            merged = dict(row)
            if change is not None:
                merged.update(_body(spec, change.after, change.after))
            rows.append(merged)
        for change in changes.values():
            if change.kind == CREATE:
                rows.append(_body(spec, change.after, change.after))
        result[type_name] = rows
    return result


def _path_problems(end: Mapping[str, list[dict[str, str]]], name: str) -> list[str]:
    """Check that traffic to an address on interface ``name`` can still arrive."""
    ports = [p for p in end.get(_PORT, []) if not _bool(p, "disabled")]
    if any(p.get("interface") == name for p in ports):
        return [
            f"management interface '{name}' is a bridge port; an address on a port is unreachable"
        ]
    bridges = {b.get("name"): b for b in end.get(_BRIDGE, [])}
    vlan = next((v for v in end.get(_VLAN, []) if v.get("name") == name), None)
    if vlan is not None:
        parent = vlan.get("interface")
        bridge = bridges.get(parent)
        if bridge is None or not _bool(bridge, "vlan-filtering"):
            return []
        try:
            vid = int(vlan.get("vlan-id", ""))
        except ValueError:
            return []
        entries = [
            e
            for e in end.get(_BVLAN, [])
            if e.get("bridge") == parent and vid in _vlans(e) and not _bool(e, "disabled")
        ]
        if not any(parent in _set(e, "tagged") for e in entries):
            return [
                f"management VLAN {vid} on bridge '{parent}' has no bridge VLAN entry with "
                f"the bridge tagged, so '{name}' would be cut off"
            ]
        members = {m for e in entries for m in _set(e, "tagged") | _set(e, "untagged")}
        if not any(
            p.get("bridge") == parent and (p.get("interface") in members or _pvid(p) == vid)
            for p in ports
        ):
            return [f"management VLAN {vid} on bridge '{parent}' has no member port"]
        return []
    bridge = bridges.get(name)
    if bridge is not None and _bool(bridge, "vlan-filtering"):
        bridge_pvid = _pvid(bridge)
        if not any(p.get("bridge") == name and _pvid(p) == bridge_pvid for p in ports):
            return [f"bridge '{name}' filters VLANs but no port carries its pvid {bridge_pvid}"]
    return []


def check_management_path(end: Mapping[str, list[dict[str, str]]], mgmt_ip: IPAddress) -> PathCheck:
    """Refuse an end state that would cut the management connection.

    Args:
        end: The end state from :func:`end_state`.
        mgmt_ip: The management address (the host of ``api_url``).

    Returns:
        Refusal reasons (empty when safe) and warnings.
    """
    check = PathCheck()
    static: list[str] = []
    leased: list[str] = []
    for row in end.get(_ADDR, []):
        if _bool(row, "disabled"):
            continue
        try:
            network = ipaddress.ip_interface(row.get("address", "")).network
        except ValueError:
            continue
        if mgmt_ip not in network:
            continue
        (leased if _bool(row, "dynamic") else static).append(row.get("interface", ""))
    if not static and not leased:
        check.refusals.append(
            f"after the plan no address on the device contains the management address {mgmt_ip}"
        )
        return check
    # A static address wins; a DHCP-held one needs its client kept and the same path rules.
    holders = static or leased
    problems: list[str] = []
    for name in holders:
        found = [] if static else _lease_problems(end, name)
        found += _path_problems(end, name)
        if not found:
            return check
        problems.extend(found)
    check.refusals.extend(problems)
    return check


def _lease_problems(end: Mapping[str, list[dict[str, str]]], name: str) -> list[str]:
    """Refuse when the DHCP client that holds the management lease is removed or disabled."""
    clients = [c for c in end.get("ip.dhcp-client", []) if c.get("interface") == name]
    if any(not _bool(c, "disabled") for c in clients):
        return []
    return [
        f"the ip.dhcp-client on '{name}' holds the management address and would be "
        "removed or disabled"
    ]


def check_service_changes(diff: TypeDiff | None, scheme: str, api_port: int) -> PathCheck:
    """Refuse changes that would cut the REST service the provider connects through.

    Args:
        diff: The ``ip.service`` diff, or ``None``.
        scheme: ``http`` or ``https`` from ``api_url``.
        api_port: The port of ``api_url``.
    """
    check = PathCheck()
    if diff is None:
        return check
    service = "www" if scheme == "http" else "www-ssl"
    for change in diff.changes:
        if change.key != (service,) or change.kind != UPDATE:
            continue
        if "disabled" in change.changed and _bool(change.after, "disabled"):
            check.refusals.append(
                f"ip.service '{service}' carries the api_url and cannot be disabled"
            )
        if "port" in change.changed and int(change.after["port"]) != api_port:
            check.refusals.append(
                f"ip.service '{service}' port would differ from the api_url port {api_port}"
            )
        if "address" in change.changed:
            check.warnings.append(
                f"ip.service '{service}' address list changes; make sure it still allows this host"
            )
    return check
