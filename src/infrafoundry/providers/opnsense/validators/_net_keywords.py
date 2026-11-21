"""Accepted network keywords for OPNsense rule fields (#1598).

The firewall-rule and NAT-rule validators check ``source_net``,
``destination_net`` and ``target`` against one accepted set built here, so the
two validators no longer keep separate copies.

The set is the union of four sources:

1. ``STATIC_NET_KEYWORDS``, the fallback when nothing is known about the box.
   A read-only probe of an OPNsense 26.1 firewall offered no ``<id>_subnets``
   form, not even ``lan_subnets`` / ``wan_subnets``. Whether other versions
   accept them is unchecked, so the static set keeps both.
2. ``<id>`` and ``<id>ip`` for every managed ``interfaces.assignments`` name.
3. ``<id>`` and ``<id>ip`` for the ``identifier`` of every live interface row.
   Only the ``identifier`` field is read: the live map is also keyed by device
   name (``em1``), which is not a keyword.
4. The keys of the live rule editor's ``networks`` option group
   (``context.existing_net_keywords``), which also carries ``lo0`` and any form
   a later version adds.
"""

from __future__ import annotations

from collections.abc import Iterable

from infrafoundry.providers.opnsense.validators.context import OPNsenseValidationContext

#: Fallback keywords used when no interface or live option is known.
STATIC_NET_KEYWORDS: frozenset[str] = frozenset(
    {
        "any",
        "lan",
        "wan",
        "wanip",
        "lanip",
        "(self)",
        "lan_subnets",
        "wan_subnets",
    }
)


def interface_net_keywords(ids: Iterable[str]) -> set[str]:
    """Return the ``<id>`` and ``<id>ip`` keywords for each interface id.

    Args:
        ids: Interface identifiers such as ``opt1``. Empty ids are skipped.

    Returns:
        The network and address keyword of every non-empty id.
    """
    keywords: set[str] = set()
    for iface_id in ids:
        if not iface_id:
            continue
        keywords.add(iface_id)
        keywords.add(f"{iface_id}ip")
    return keywords


def accepted_net_keywords(context: OPNsenseValidationContext) -> frozenset[str]:
    """Build the network keywords a rule field may use.

    Args:
        context: Validation context carrying managed assignments, live
            interface rows and the live network options.

    Returns:
        The static keywords plus those derived from managed and live
        interfaces and the live option keys.
    """
    live_ids: list[str] = []
    for row in context.existing_interfaces.values():
        if not isinstance(row, dict):
            continue
        identifier = row.get("identifier")
        if isinstance(identifier, str) and identifier:
            live_ids.append(identifier)
    return frozenset(
        STATIC_NET_KEYWORDS
        | interface_net_keywords(context.interface_assignment_names)
        | interface_net_keywords(live_ids)
        | context.existing_net_keywords
    )
