"""Lock-out safeguards for QNAP writes (ADR-0039). Pure functions, no I/O.

The switch's API cannot say which port carries the operator's management traffic, so the
checks work from the management VLAN and an operator-declared list of protected ports. A
plan that could cut the connection is refused (fail closed). ``allow_lockout_risk`` turns
the refusals about the management VLAN and protected ports into warnings; deleting a LACP
group that a remaining VLAN still lists is never overridable.

Port settings are checked against the *watched* ports: ``protected_ports`` (a ``lagN``
expands to its members) or, without it, the members of the management VLAN. Shutting a
watched port down, or changing its speed, duplex or FEC, is refused; so is any MTU change,
because the MTU looks switch-wide. Alias, flow control and enabling a port are safe.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from ..schema import port_label
from ..settings import QnapSettings
from .diff import Change

MAX_MANAGEMENT_VLAN = 4094


@dataclass
class LockoutCheck:
    """What the lock-out rules found."""

    refusals: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def management_vlan(
    settings: QnapSettings, ip_interface_result: Any
) -> tuple[int | None, list[str]]:
    """Return the management VLAN and the warnings that come with it.

    ``provider_settings.qnap.management_vlan`` wins. Otherwise it is inferred from
    ``GET ip/ipv4/interface``, only when exactly one entry is enabled and its key is a
    VLAN id. That is an inference and is flagged as such.

    Args:
        settings: The connection settings.
        ip_interface_result: The ``result`` of ``GET ip/ipv4/interface``.

    Returns:
        ``(vlan or None, warnings)``.
    """
    if settings.management_vlan is not None:
        return settings.management_vlan, []
    enabled: list[Any] = []
    if isinstance(ip_interface_result, list):
        for item in ip_interface_result:
            val = item.get("val") if isinstance(item, dict) else None
            if isinstance(val, dict) and val.get("enableInterface") is True:
                enabled.append(item.get("key"))
    if len(enabled) == 1:
        key = str(enabled[0])
        if key.isdigit() and 1 <= int(key) <= MAX_MANAGEMENT_VLAN:
            return int(key), [
                f"management VLAN inferred as {key} from ip/ipv4/interface (unverified); "
                "set provider_settings.qnap.management_vlan to confirm"
            ]
    return None, []


def check_lockout(
    end_vlans: Mapping[int, Mapping[int, bool]],
    end_lags: Mapping[int, Collection[int]],
    live_vlans: Mapping[int, Mapping[int, bool]],
    live_lags: Mapping[int, Collection[int]],
    mgmt_vlan: int,
    protected: Collection[int],
    start_index: int,
    allow_risk: bool,
) -> LockoutCheck:
    """Check the end state against the management VLAN and the protected ports.

    Args:
        end_vlans: VLAN id to ``{port: tagged}`` after the plan.
        end_lags: LACP group to its member ports after the plan.
        live_vlans: The same as read.
        live_lags: The same as read.
        mgmt_vlan: The management VLAN id.
        protected: Interface numbers that carry management traffic (may be empty).
        start_index: ``lacp/info.StartIndex``.
        allow_risk: Downgrade the overridable refusals to warnings.

    Returns:
        The refusals and warnings.
    """
    result = LockoutCheck()
    risks: list[str] = []

    def name(port: int) -> str:
        return port_label(port, start_index)

    live_mgmt = live_vlans.get(mgmt_vlan)
    end_mgmt = end_vlans.get(mgmt_vlan)
    if live_mgmt is not None and end_mgmt is None:
        risks.append(f"the plan deletes the management VLAN {mgmt_vlan}")
    elif live_mgmt is not None and end_mgmt is not None:
        watched = (
            [p for p in sorted(protected) if p in live_mgmt] if protected else sorted(live_mgmt)
        )
        for port in watched:
            if port not in end_mgmt:
                risks.append(f"the plan removes {name(port)} from the management VLAN {mgmt_vlan}")
            elif end_mgmt[port] != live_mgmt[port]:
                risks.append(
                    f"the plan flips the Tagged flag of {name(port)} in the management VLAN "
                    f"{mgmt_vlan}"
                )
        for port in sorted(p for p in protected if p not in live_mgmt):
            result.warnings.append(
                f"protected port {name(port)} is not a member of the management VLAN {mgmt_vlan}"
            )

    for group, members in end_lags.items():
        before = set(live_lags.get(group, ()))
        for port in sorted(set(members) - before):
            if port in protected:
                risks.append(f"the plan puts protected port {port} into LACP group {group}")

    for group, before_members in live_lags.items():
        interface = start_index + group
        if interface not in protected:
            continue
        if group not in end_lags:
            risks.append(f"the plan deletes LACP group {group}, whose interface is protected")
        elif not set(before_members) <= set(end_lags[group]):
            risks.append(f"the plan removes members of LACP group {group}, which is protected")

    for group in sorted(set(live_lags) - set(end_lags)):
        interface = start_index + group
        users = sorted(v for v, members in end_vlans.items() if interface in members)
        if users:
            result.refusals.append(
                f"the plan deletes LACP group {group} while VLAN {users[0]} still lists lag{group}"
            )

    if allow_risk:
        result.warnings.extend(f"lock-out risk allowed: {r}" for r in risks)
    else:
        result.refusals = [*risks, *result.refusals]
    return result


def watched_ports(
    protected: Collection[int],
    mgmt_members: Collection[int],
    lags: Mapping[int, Collection[int]],
    start_index: int,
) -> frozenset[int]:
    """Return the physical ports whose settings could cut the management connection.

    Args:
        protected: Interface numbers from ``protected_ports`` (may be empty).
        mgmt_members: Interface numbers in the management VLAN (live and end state).
        lags: LACP group to its member ports (live and end state).
        start_index: ``lacp/info.StartIndex``.

    Returns:
        ``protected`` when given, else the management VLAN members; a LAG interface
        expands to its member ports.
    """
    chosen = protected if protected else mgmt_members
    watched: set[int] = set()
    for interface in chosen:
        if interface > start_index:
            watched.update(lags.get(interface - start_index, ()))
        else:
            watched.add(interface)
    return frozenset(watched)


def check_port_lockout(
    changes: Iterable[Change], watched: Collection[int], allow_risk: bool
) -> LockoutCheck:
    """Check planned port changes against the watched ports and the switch-wide MTU.

    Args:
        changes: The port changes (``Change.fields`` names the changed fields).
        watched: Physical ports from :func:`watched_ports`.
        allow_risk: Downgrade the refusals to warnings.
    """
    risks: list[str] = []
    for change in changes:
        port = change.key[0]
        if port in watched:
            if change.after.get("Shutdown") is True and "shutdown" in change.fields:
                risks.append(f"the plan shuts down port {port}, which may carry management traffic")
            for name in ("speed", "duplex", "fec"):
                if name in change.fields:
                    risks.append(
                        f"the plan changes the {name} of port {port}, which may carry "
                        "management traffic"
                    )
        if "mtu" in change.fields:
            risks.append(
                f"the plan changes the MTU on port {port}; the MTU looks switch-wide "
                "(unverified), so it may affect every port"
            )
    result = LockoutCheck()
    if allow_risk:
        result.warnings = [f"lock-out risk allowed: {r}" for r in risks]
    else:
        result.refusals = risks
    return result
