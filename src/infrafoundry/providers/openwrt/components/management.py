"""Refuse changes that could cut the management connection.

A ``network.interface`` change is a management change when the settings address lies
in the interface's subnet before or after the change, or when the address cannot be
resolved or the change cannot be read. It is refused unless the resource sets
``confirm_management_change: true``. With the flag, and the settings address equal to
the interface's current address, the run reconnects to the new address before it
confirms; if that fails the device rolls back by itself.
"""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable
from typing import Any

from ..schema import Desired

Resolver = Callable[[str], str | None]


def resolve_ipv4(host: str) -> str | None:
    """Return the IPv4 address of ``host``, or ``None`` when it does not resolve."""
    try:
        ipaddress.IPv4Address(host)
    except ValueError:
        pass
    else:
        return host
    try:
        infos = socket.getaddrinfo(host, None, socket.AF_INET)
    except OSError:
        return None
    return str(infos[0][4][0]) if infos else None


def interfaces_of(values: Any) -> list[ipaddress.IPv4Interface] | None:
    """Read the addresses of a UCI interface section.

    Handles ``ipaddr`` with or without a separate ``netmask``, and a CIDR or list
    ``ipaddr`` as stored by some devices.

    Args:
        values: The section's options, as the module diff reports them.

    Returns:
        The addresses (empty for a missing section), or ``None`` when unreadable.
    """
    if not isinstance(values, dict):
        return None
    raw = values.get("ipaddr")
    if raw in (None, ""):
        return []
    entries = raw if isinstance(raw, list) else [raw]
    netmask = values.get("netmask")
    found: list[ipaddress.IPv4Interface] = []
    for entry in entries:
        text = str(entry)
        if "/" not in text and netmask and not isinstance(raw, list):
            text = f"{text}/{netmask}"
        try:
            found.append(ipaddress.IPv4Interface(text))
        except ValueError:
            return None
    return found


def management_refusals(
    address: str,
    changed: list[tuple[Desired, dict[str, Any] | None, dict[str, Any] | None]],
    *,
    resolve: Resolver = resolve_ipv4,
) -> tuple[list[str], str | None]:
    """Return the refusals for the changed interfaces and the host to reconnect to.

    Args:
        address: The settings address (an IP literal or a name).
        changed: ``(object, before, after)`` for each ``network.interface`` the run
            changes; ``before``/``after`` are the section values from the diff, or
            ``None`` when the diff had none.
        resolve: Resolves the settings address; replaced in tests.

    Returns:
        The refusal messages (empty when the run may go on) and the new address to
        reconnect to, if the management address itself changes.
    """
    refusals: list[str] = []
    reconnect: str | None = None
    management = resolve(address)
    target = ipaddress.IPv4Address(management) if management else None
    for item, before, after in changed:
        old = interfaces_of(before) if before is not None else None
        new = interfaces_of(after) if after is not None else None
        if target is None or old is None or new is None:
            affected = True
        else:
            affected = any(target in i.network for i in (*old, *new))
        if not affected:
            continue
        if not item.confirm:
            reason = (
                "the settings address cannot be resolved"
                if target is None
                else "the change cannot be read"
                if old is None or new is None
                else f"the settings address {management} is in its subnet"
            )
            refusals.append(
                f"network.interface '{item.name}' changes the management network ({reason}); "
                "set confirm_management_change: true to allow it"
            )
            continue
        if (
            target is not None
            and old
            and new
            and any(i.ip == target for i in old)
            and new[0].ip != target
        ):
            reconnect = str(new[0].ip)
    return refusals, reconnect
