"""Pure diff of declared QNAP VLANs and LACP groups against the switch (ADR-0039).

Membership model: a ``vlan`` resource owns the member lists it declares. A declared
``tagged`` or ``untagged`` list is authoritative and replaces the live set; an omitted list
keeps the live set. A port that becomes untagged in one VLAN is stripped from every other
VLAN that holds it untagged (a port is untagged in at most one VLAN), unmanaged VLANs
included, and the plan says so. Every write is a full member list, so a change carries the
complete end-state membership.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass, field, replace
from typing import Any

from infrafoundry.core.exceptions import InfraFoundryError

from ..schema import (
    DEFAULT_VLAN_ID,
    LACP_TYPE,
    VLAN_TYPE,
    DesiredLag,
    DesiredVlan,
    LacpInfo,
    LiveLag,
    LiveVlan,
    Port,
    port_label,
    resolve_port,
)

CREATE = "create"
UPDATE = "update"
DELETE = "delete"


class QnapPlanError(InfraFoundryError):
    """The declared end state cannot exist on this switch."""


@dataclass(frozen=True)
class LagEnd:
    """The mode and members of a LACP group."""

    mode: Any
    members: frozenset[int]


@dataclass(frozen=True)
class Change:
    """One planned change to one object. ``after`` is the complete end state."""

    kind: str
    type_name: str
    key: tuple[Any, ...]
    resource_name: str
    before: Any = None
    after: Any = None
    notes: tuple[str, ...] = ()
    incidental: bool = False
    """True for a strip of an undeclared VLAN: written, but not a managed object."""


@dataclass
class TypeDiff:
    """The changes for one resource type, plus the live objects left alone."""

    type_name: str
    changes: list[Change] = field(default_factory=list)
    unmanaged: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        """True when there is nothing to change."""
        return not self.changes

    def count(self, kind: str) -> int:
        """Number of changes of a kind."""
        return sum(1 for c in self.changes if c.kind == kind)


def label(key: tuple[Any, ...]) -> str:
    """Return a key as text."""
    return "/".join(str(part) for part in key)


def _ports(tokens: Iterable[Port] | None, start_index: int) -> frozenset[int] | None:
    if tokens is None:
        return None
    return frozenset(resolve_port(t, start_index) for t in tokens)


def _end_members(
    obj: DesiredVlan, current: Mapping[int, bool] | None, start_index: int
) -> dict[int, bool]:
    live = current or {}
    live_tagged = {p for p, tagged in live.items() if tagged}
    live_untagged = {p for p, tagged in live.items() if not tagged}
    tagged = _ports(obj.tagged, start_index)
    untagged = _ports(obj.untagged, start_index)
    if tagged is not None and untagged is not None and tagged & untagged:
        raise QnapPlanError(
            f"vlan '{obj.resource_name}': the same port is both tagged and untagged"
        )
    new_untagged = untagged if untagged is not None else live_untagged - (tagged or set())
    new_tagged = tagged if tagged is not None else live_tagged - (untagged or set())
    return {**dict.fromkeys(new_tagged, True), **dict.fromkeys(new_untagged, False)}


def diff_vlans(
    desired: list[DesiredVlan],
    live: list[LiveVlan],
    start_index: int,
    *,
    add_only: bool,
    managed_keys: Collection[tuple[Any, ...]] | None,
) -> TypeDiff:
    """Diff the declared VLANs against the live ones.

    Args:
        desired: Declared VLANs.
        live: VLANs on the switch.
        start_index: ``lacp/info.StartIndex``, to resolve ``lagN`` ports.
        add_only: Suppress every delete.
        managed_keys: Keys InfraFoundry applied before (ADR-0018), or ``None``. Only these
            are deleted when undeclared.

    Returns:
        The changes (with strips of moved untagged ports), the kept VLANs and warnings.

    Raises:
        QnapPlanError: If two VLANs both claim a port untagged.
    """
    diff = TypeDiff(VLAN_TYPE)
    live_by = {v.id: v for v in live}
    end: dict[int, dict[int, bool]] = {v.id: dict(v.members) for v in live}
    changes: dict[int, Change] = {}
    deletes: list[Change] = []
    claimed: dict[int, int] = {}  # port -> vlan that newly holds it untagged
    declared: set[int] = set()

    for obj in desired:
        declared.add(obj.id)
        current = live_by.get(obj.id)
        if obj.absent:
            if current is None or obj.id == DEFAULT_VLAN_ID:
                continue
            if add_only:
                diff.unmanaged.append(f"{obj.id} (absent: true, skipped: add-only)")
                continue
            deletes.append(
                Change(DELETE, VLAN_TYPE, obj.key, obj.resource_name, before=dict(current.members))
            )
            end.pop(obj.id, None)
            continue
        members = _end_members(obj, current.members if current else None, start_index)
        end[obj.id] = members
        old = current.members if current else {}
        for port, tagged in members.items():
            newly_untagged = not tagged and old.get(port) is not False
            if newly_untagged and claimed.setdefault(port, obj.id) != obj.id:
                raise QnapPlanError(
                    f"port {port_label(port, start_index)} is declared untagged in "
                    f"vlan {claimed[port]} and vlan {obj.id}"
                )
        if current is None:
            changes[obj.id] = Change(
                CREATE, VLAN_TYPE, obj.key, obj.resource_name, after=dict(members)
            )
        elif dict(current.members) != members:
            changes[obj.id] = Change(
                UPDATE,
                VLAN_TYPE,
                obj.key,
                obj.resource_name,
                before=dict(current.members),
                after=dict(members),
            )

    for vlan in live:
        if vlan.id in declared or vlan.id == DEFAULT_VLAN_ID:
            continue
        key = (vlan.id,)
        if managed_keys is not None and not add_only and key in managed_keys:
            deletes.append(Change(DELETE, VLAN_TYPE, key, label(key), before=dict(vlan.members)))
            end.pop(vlan.id, None)
        else:
            diff.unmanaged.append(str(vlan.id))

    for port, owner in sorted(claimed.items()):
        for other, members in list(end.items()):
            if other == owner or members.get(port) is not False:
                continue
            note = f"untag port {port_label(port, start_index)} (moves to vlan {owner})"
            stripped = {p: t for p, t in members.items() if p != port}
            end[other] = stripped
            existing = changes.get(other)
            if existing is not None:
                changes[other] = replace(existing, after=stripped, notes=(*existing.notes, note))
            else:
                before = dict(live_by[other].members)
                changes[other] = Change(
                    UPDATE,
                    VLAN_TYPE,
                    (other,),
                    str(other),
                    before=before,
                    after=stripped,
                    notes=(note,),
                    incidental=other not in declared,
                )

    diff.changes = [*changes.values(), *deletes]
    return diff


def diff_lags(
    desired: list[DesiredLag],
    live: list[LiveLag],
    start_index: int,
    *,
    add_only: bool,
    managed_keys: Collection[tuple[Any, ...]] | None,
) -> TypeDiff:
    """Diff the declared LACP groups against the live ones.

    Args:
        desired: Declared groups.
        live: Groups on the switch.
        start_index: ``lacp/info.StartIndex``, to resolve ports.
        add_only: Suppress every delete.
        managed_keys: Keys InfraFoundry applied before (ADR-0018), or ``None``.

    Raises:
        QnapPlanError: If a new group lacks a mode or members, or lists a ``lagN`` member.
    """
    diff = TypeDiff(LACP_TYPE)
    live_by = {g.group: g for g in live}
    declared: set[int] = set()
    for obj in desired:
        declared.add(obj.group)
        current = live_by.get(obj.group)
        if obj.absent:
            if current is None:
                continue
            if add_only:
                diff.unmanaged.append(f"{obj.group} (absent: true, skipped: add-only)")
            else:
                diff.changes.append(
                    Change(
                        DELETE,
                        LACP_TYPE,
                        obj.key,
                        obj.resource_name,
                        before=LagEnd(current.mode, current.members),
                    )
                )
            continue
        members = _ports(obj.members, start_index)
        if members is not None and any(m > start_index for m in members):
            raise QnapPlanError(f"lacp.group '{obj.resource_name}': members must be physical ports")
        if current is None:
            if obj.mode is None or members is None:
                raise QnapPlanError(
                    f"lacp.group '{obj.resource_name}': a new group needs mode and members"
                )
            diff.changes.append(
                Change(
                    CREATE, LACP_TYPE, obj.key, obj.resource_name, after=LagEnd(obj.mode, members)
                )
            )
            continue
        mode = obj.mode if obj.mode is not None else current.mode
        end_members = members if members is not None else current.members
        if str(mode) != str(current.mode) or end_members != current.members:
            diff.changes.append(
                Change(
                    UPDATE,
                    LACP_TYPE,
                    obj.key,
                    obj.resource_name,
                    before=LagEnd(current.mode, current.members),
                    after=LagEnd(mode, end_members),
                )
            )
    for lag in live:
        if lag.group in declared:
            continue
        key = (lag.group,)
        if managed_keys is not None and not add_only and key in managed_keys:
            diff.changes.append(
                Change(
                    DELETE,
                    LACP_TYPE,
                    key,
                    label(key),
                    before=LagEnd(lag.mode, lag.members),
                )
            )
        else:
            diff.unmanaged.append(str(lag.group))
    return diff


def end_state(
    diffs: Mapping[str, TypeDiff],
    live_vlans: Mapping[int, Mapping[int, bool]],
    live_lags: Mapping[int, LagEnd],
) -> tuple[dict[int, dict[int, bool]], dict[int, LagEnd]]:
    """Apply the planned changes to the live state and return the end state.

    Args:
        diffs: The diffs by type.
        live_vlans: VLAN id to ``{port: tagged}``.
        live_lags: Group to its mode and members.
    """
    vlans = {i: dict(m) for i, m in live_vlans.items()}
    lags = dict(live_lags)
    vlan_diff = diffs.get(VLAN_TYPE)
    for change in vlan_diff.changes if vlan_diff else []:
        if change.kind == DELETE:
            vlans.pop(change.key[0], None)
        else:
            vlans[change.key[0]] = dict(change.after)
    lag_diff = diffs.get(LACP_TYPE)
    for change in lag_diff.changes if lag_diff else []:
        if change.kind == DELETE:
            lags.pop(change.key[0], None)
        else:
            lags[change.key[0]] = change.after
    return vlans, lags


def check_end_state(
    diffs: Mapping[str, TypeDiff],
    end_vlans: Mapping[int, Mapping[int, bool]],
    end_lags: Mapping[int, LagEnd],
    *,
    port_count: int,
    info: LacpInfo,
) -> None:
    """Check what the plan writes against what this switch has.

    Raises:
        QnapPlanError: On an unknown port, an unknown ``lagN``, a physical port that is in a
            LACP group and also listed in a VLAN, or more members than a group allows.
    """
    start = info.start_index
    in_lag = {m: g for g, lag in end_lags.items() for m in lag.members}
    lag_diff = diffs.get(LACP_TYPE)
    for change in lag_diff.changes if lag_diff else []:
        if change.kind == DELETE:
            continue
        group = change.key[0]
        if group > info.max_channels:
            raise QnapPlanError(f"lacp group {group} is above the switch's {info.max_channels}")
        if len(change.after.members) > info.max_ports:
            raise QnapPlanError(
                f"lacp group {group} has {len(change.after.members)} members; the switch "
                f"allows {info.max_ports}"
            )
        for port in sorted(change.after.members):
            if not 1 <= port <= port_count:
                raise QnapPlanError(f"lacp group {group}: port {port} does not exist")
    vlan_diff = diffs.get(VLAN_TYPE)
    for change in vlan_diff.changes if vlan_diff else []:
        if change.kind == DELETE or change.incidental:
            continue
        for port in sorted(change.after):
            name = port_label(port, start)
            if port > start:
                if (port - start) not in end_lags or port - start > info.max_channels:
                    raise QnapPlanError(f"vlan {change.key[0]}: {name} is not a LACP group")
            elif not 1 <= port <= port_count:
                raise QnapPlanError(f"vlan {change.key[0]}: port {port} does not exist")
            elif port in in_lag:
                raise QnapPlanError(
                    f"vlan {change.key[0]}: port {port} is a member of lag{in_lag[port]}; "
                    f"list lag{in_lag[port]} instead"
                )


def untag_warnings(
    end_vlans: Mapping[int, Mapping[int, bool]],
    live_vlans: Mapping[int, Mapping[int, bool]],
    start_index: int,
) -> list[str]:
    """Warn about each port that is untagged in a live VLAN and in none of the end state."""
    live_untagged = {p for m in live_vlans.values() for p, tagged in m.items() if not tagged}
    end_untagged = {p for m in end_vlans.values() for p, tagged in m.items() if not tagged}
    return [
        f"port {port_label(p, start_index)} will have no untagged VLAN"
        for p in sorted(live_untagged - end_untagged)
    ]
