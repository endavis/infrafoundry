"""Shared helpers for refusing a kea subnet delete that would orphan reservations (#1264).

OPNsense does not cascade a kea ``delSubnet`` to the subnet's reservations, and it
does not refuse the delete either, so the reservations are left pointing at a
subnet that no longer exists. The subnet managers therefore refuse to delete a
subnet while a reservation InfraFoundry will not delete still uses it (ADR-0018:
never delete what we do not manage). The refusal is a warning, not a failure, so
unrelated changes are not blocked by an object outside InfraFoundry's control.

Messages name the subnet CIDR and each reservation's MAC or DUID and IP, never a
config.
"""

from __future__ import annotations

from typing import Any

#: Cap on the reservations named in one warning.
_MAX_NAMED = 5


def live_reservations_by_subnet(
    live_reservations: list[dict[str, Any]],
    subnet_uuids: set[str],
    identity_field: str,
) -> dict[str, list[str]]:
    """Describe every live reservation that sits on one of ``subnet_uuids``.

    Args:
        live_reservations: Rows from ``search_dhcp{4,6}_reservations``.
        subnet_uuids: Subnet UUIDs to look for.
        identity_field: ``hw_address`` (DHCPv4) or ``duid`` (DHCPv6).

    Returns:
        Subnet UUID to ``"<identity> <ip_address>"`` descriptors, only for subnets
        that have at least one reservation.
    """
    found: dict[str, list[str]] = {}
    for row in live_reservations:
        subnet = str(row.get("subnet", ""))
        if subnet not in subnet_uuids:
            continue
        found.setdefault(subnet, []).append(describe_reservation(row, identity_field))
    return found


def describe_reservation(row: dict[str, Any], identity_field: str) -> str:
    """Return ``"<identity> <ip_address>"`` for a live reservation row."""
    identity = str(row.get(identity_field, "") or row.get("uuid", ""))
    return f"{identity} {row.get('ip_address', '')}".strip()


def blocked_warning(type_name: str, cidr: str, descriptors: list[str]) -> str:
    """Build the warning for a subnet delete that was refused.

    Args:
        type_name: Resource type, e.g. ``kea.dhcp4.subnets``.
        cidr: The subnet that was kept.
        descriptors: ``"<identity> <ip>"`` entries of the reservations that block it.

    Returns:
        The one-line warning.
    """
    named = ", ".join(descriptors[:_MAX_NAMED])
    if len(descriptors) > _MAX_NAMED:
        named += f", +{len(descriptors) - _MAX_NAMED} more"
    return (
        f"not deleting {type_name} {cidr}: {len(descriptors)} reservation(s) InfraFoundry "
        f"does not manage still use it ({named}); remove or move them on the box, "
        "then re-run apply"
    )


def split_blocked_deletes(
    deletes: list[tuple[str, str]],
    kept_by_uuid: dict[str, list[str]],
    type_name: str,
) -> tuple[list[tuple[str, str]], list[tuple[str, str, list[str]]], list[str]]:
    """Move the deletes whose subnet still has blocking reservations to ``blocked``.

    Args:
        deletes: ``(uuid, cidr)`` delete candidates.
        kept_by_uuid: Subnet UUID to the descriptors of reservations that block it.
        type_name: Resource type for the warning text.

    Returns:
        ``(deletes, blocked, warnings)`` with ``blocked`` as ``(uuid, cidr, descriptors)``.
    """
    remaining: list[tuple[str, str]] = []
    blocked: list[tuple[str, str, list[str]]] = []
    warnings: list[str] = []
    for uuid, cidr in deletes:
        descriptors = kept_by_uuid.get(uuid)
        if not descriptors:
            remaining.append((uuid, cidr))
            continue
        blocked.append((uuid, cidr, descriptors))
        warnings.append(blocked_warning(type_name, cidr, descriptors))
    return remaining, blocked, warnings
