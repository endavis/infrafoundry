"""Validation context for the OPNsense sub-validators.

One context carries every input the OPNsense validators take. Each validator
reads only the fields it needs, so the unused ones keep their empty defaults.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationContext
from infrafoundry.providers.opnsense.validators._xref import XRefIndex


@dataclass(frozen=True)
class HaPeerCheck:
    """Outcome of the ``core/hasync_status/version`` call to the HA peer (#1393).

    Attributes:
        ok: Whether the call returned without an error.
        message: The error message when ``ok`` is false, else an empty string.
        version: The peer's firmware version when the reply carries one.
        answered: Whether the peer returned a non-empty ``response``.
    """

    ok: bool
    message: str = ""
    version: str | None = None
    answered: bool = False


@dataclass(frozen=True, kw_only=True)
class OPNsenseValidationContext(ValidationContext):
    """Inputs for the OPNsense validators.

    ``resources`` is the list validators that take a plain resource list check.
    The typed lists below are for validators that check one resource type.

    Attributes:
        aliases: ``alias`` resources.
        firewall_rules: ``firewall_rule`` resources.
        vlans: ``vlan`` resources.
        assignments: ``interface_assignment`` resources.
        nat_rules: ``nat_rule`` resources.
        gateways: ``gateway`` resources.
        static_routes: ``static_route`` resources.
        virtual_ips: ``virtual_ip`` resources.
        overrides: ``unbound_host_override`` resources.
        host_aliases: ``unbound_host_alias`` resources.
        forwards: ``unbound_forward`` resources.
        dhcp4_reservations: Kea DHCPv4 reservation resources.
        dhcp6_reservations: Kea DHCPv6 reservation resources.
        alias_names: Alias names managed in the configuration.
        interface_assignment_names: Interface assignment names managed in the configuration.
        gateway_names: Gateway names managed in the configuration.
        vlan_names: VLAN names managed in the configuration.
        managed_host_override_names: Host override names managed in the configuration.
        dhcp4_subnet_names: Kea DHCPv4 subnet names managed in the configuration.
        dhcp6_subnet_names: Kea DHCPv6 subnet names managed in the configuration.
        existing_interfaces: Interfaces present on the live system.
        existing_aliases: Aliases present on the live system.
        existing_gateways: Gateway names present on the live system.
        existing_host_override_names: Host override names present on the live system.
        existing_hasync_interfaces: Interfaces the box offers for pfsync (live option keys).
        existing_hasync_sync_items: Sync items the box offers (live option keys).
        managed_gateways: ``gateway`` resources managed in the configuration.
        index: Dotted-type cross-reference index, or None when not built.
        live_carp_status: ``diagnostics/interface/getVipStatus`` reply, or None when unread.
        live_sync_target: The live ``synchronizetoip`` value, or an empty string.
        peer_check: Result of the HA peer version call, or None when no call was made.
        peer_carp_status: ``getVipStatus`` reply of the ``ha_backup`` firewall (#1450), or
            None when no pair is declared or the peer was unreadable.
        node_label: Firewall name of the node ``live_carp_status`` came from.
        peer_label: Firewall name of the ``ha_backup`` node.
    """

    aliases: list[ResourceConfig] = field(default_factory=list)
    firewall_rules: list[ResourceConfig] = field(default_factory=list)
    vlans: list[ResourceConfig] = field(default_factory=list)
    assignments: list[ResourceConfig] = field(default_factory=list)
    nat_rules: list[ResourceConfig] = field(default_factory=list)
    gateways: list[ResourceConfig] = field(default_factory=list)
    static_routes: list[ResourceConfig] = field(default_factory=list)
    virtual_ips: list[ResourceConfig] = field(default_factory=list)
    overrides: list[ResourceConfig] = field(default_factory=list)
    host_aliases: list[ResourceConfig] = field(default_factory=list)
    forwards: list[ResourceConfig] = field(default_factory=list)
    dhcp4_reservations: list[ResourceConfig] = field(default_factory=list)
    dhcp6_reservations: list[ResourceConfig] = field(default_factory=list)
    alias_names: set[str] = field(default_factory=set)
    interface_assignment_names: set[str] = field(default_factory=set)
    gateway_names: set[str] = field(default_factory=set)
    vlan_names: set[str] = field(default_factory=set)
    managed_host_override_names: set[str] = field(default_factory=set)
    dhcp4_subnet_names: set[str] = field(default_factory=set)
    dhcp6_subnet_names: set[str] = field(default_factory=set)
    existing_interfaces: dict[str, Any] = field(default_factory=dict)
    existing_aliases: dict[str, Any] = field(default_factory=dict)
    existing_gateways: set[str] = field(default_factory=set)
    existing_host_override_names: set[str] = field(default_factory=set)
    existing_hasync_interfaces: set[str] = field(default_factory=set)
    existing_hasync_sync_items: set[str] = field(default_factory=set)
    managed_gateways: list[ResourceConfig] | None = None
    index: XRefIndex | None = None
    live_carp_status: dict[str, Any] | None = None
    live_sync_target: str = ""
    peer_check: HaPeerCheck | None = None
    peer_carp_status: dict[str, Any] | None = None
    node_label: str = ""
    peer_label: str = ""
