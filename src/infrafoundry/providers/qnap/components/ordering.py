"""Orders QNAP writes into phases (ADR-0039).

Every VLAN write carries the complete member list, so the order only has to keep three
things true on the switch at every step:

* a port is untagged in at most one VLAN: phase B writes the VLANs that give an untagged
  port away *before* the VLAN that takes it, which also lets two VLANs swap ports;
* a LAG interface exists before a VLAN lists it (phase A) and is deleted only after the
  VLANs stop listing it (phases F, G);
* the management VLAN is written last among the updates.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ..schema import (
    LACP_TYPE,
    VLAN_TYPE,
    lag_body,
    lag_delete_body,
    vlan_body,
    vlan_delete_body,
)
from .diff import CREATE, DELETE, UPDATE, Change, TypeDiff

PHASE_TITLES = {
    "A": "create LACP groups",
    "B": "free untagged ports that move",
    "C": "create VLANs",
    "D": "update VLANs",
    "E": "update LACP groups",
    "F": "delete VLANs",
    "G": "delete LACP groups",
}

_VLAN_PATH = "vlan"
_LAG_PATH = "lacp/group"


@dataclass(frozen=True)
class Step:
    """One write to the switch."""

    phase: str
    kind: str
    type_name: str
    key: tuple[Any, ...]
    resource_name: str
    method: str
    path: str
    body: dict[str, Any]
    incidental: bool = False


def _vlan_step(phase: str, change: Change, method: str, body: dict[str, Any], kind: str) -> Step:
    return Step(
        phase,
        kind,
        VLAN_TYPE,
        change.key,
        change.resource_name,
        method,
        _VLAN_PATH,
        body,
        change.incidental,
    )


def _lag_step(phase: str, change: Change, method: str, body: dict[str, Any]) -> Step:
    return Step(
        phase, change.kind, LACP_TYPE, change.key, change.resource_name, method, _LAG_PATH, body
    )


def _lag_write(change: Change, member_as_str: bool) -> dict[str, Any]:
    return lag_body(change.key[0], change.after.mode, change.after.members, member_as_str)


def _freed_ports(
    vlan_id: int, live: Mapping[int, bool], end_vlans: Mapping[int, Mapping[int, bool]]
) -> set[int]:
    """Untagged ports of a live VLAN that end untagged in a different VLAN."""
    own = end_vlans.get(vlan_id, {})
    return {
        port
        for port, tagged in live.items()
        if not tagged
        and own.get(port) is not False
        and any(m.get(port) is False for other, m in end_vlans.items() if other != vlan_id)
    }


def order_changes(
    vlan_diff: TypeDiff | None,
    lag_diff: TypeDiff | None,
    live_vlans: Mapping[int, Mapping[int, bool]],
    end_vlans: Mapping[int, Mapping[int, bool]],
    mgmt_vlan: int | None,
    *,
    member_as_str: bool = True,
) -> list[Step]:
    """Turn the diffs into steps in phase order.

    Args:
        vlan_diff: The VLAN diff, if any.
        lag_diff: The LACP group diff, if any.
        live_vlans: VLAN id to ``{port: tagged}`` as read.
        end_vlans: The same after every change.
        mgmt_vlan: The management VLAN; its update is written last in phase D.
        member_as_str: Whether ``PortMembers`` holds strings.
    """
    vlans = vlan_diff.changes if vlan_diff else []
    lags = lag_diff.changes if lag_diff else []
    steps: list[Step] = []
    already_final: set[int] = set()
    steps += [
        _lag_step("A", c, "POST", _lag_write(c, member_as_str)) for c in lags if c.kind == CREATE
    ]
    for change in vlans:
        if change.kind == CREATE:
            continue
        vlan_id = change.key[0]
        freed = _freed_ports(vlan_id, live_vlans[vlan_id], end_vlans)
        if freed:
            kept = {p: t for p, t in live_vlans[vlan_id].items() if p not in freed}
            steps.append(_vlan_step("B", change, "PUT", vlan_body(vlan_id, kept), UPDATE))
            if change.kind == UPDATE and kept == change.after and vlan_id != mgmt_vlan:
                already_final.add(vlan_id)  # the phase B write is already the end state
    steps += [
        _vlan_step("C", c, "POST", vlan_body(c.key[0], c.after), CREATE)
        for c in vlans
        if c.kind == CREATE
    ]
    updates = [c for c in vlans if c.kind == UPDATE and c.key[0] not in already_final]
    updates.sort(key=lambda c: c.key[0] == mgmt_vlan)
    steps += [_vlan_step("D", c, "PUT", vlan_body(c.key[0], c.after), UPDATE) for c in updates]
    steps += [
        _lag_step("E", c, "PUT", _lag_write(c, member_as_str)) for c in lags if c.kind == UPDATE
    ]
    steps += [
        _vlan_step("F", c, "DELETE", vlan_delete_body(c.key[0]), DELETE)
        for c in vlans
        if c.kind == DELETE
    ]
    steps += [
        _lag_step("G", c, "DELETE", lag_delete_body(c.key[0])) for c in lags if c.kind == DELETE
    ]
    return steps
