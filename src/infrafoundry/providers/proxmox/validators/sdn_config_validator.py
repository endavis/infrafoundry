"""SDN zone and vnet configuration field-level validation for Proxmox (#1137)."""

from __future__ import annotations

import ipaddress
import re
from typing import Any

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport

# Zone kinds the provider can render
VALID_ZONE_KINDS = frozenset({"vxlan"})

# Proxmox SDN zone and vnet IDs: lowercase letter, then up to 7 letters or digits
SDN_ID_PATTERN = re.compile(r"^[a-z][a-z0-9]{0,7}$")

# VXLAN network identifiers are 24 bits; 0 is reserved
MAX_VNI = 16_777_215


def sdn_id(resource: ResourceConfig) -> str:
    """Return the Proxmox ID of an SDN zone or vnet: ``config.id``, else its name."""
    return str((resource.config or {}).get("id") or resource.name)


class SDNConfigValidator:
    """Validates SDN zone and vnet configuration before Terraform generation.

    Errors are reported for values Proxmox or terraform would reject: malformed
    IDs, VXLAN zones without peers, vnets in an undeclared zone, and missing or
    duplicate VXLAN tags.
    """

    def __init__(self, report: ValidationReport) -> None:
        """Initialize SDN config validator.

        Args:
            report: ValidationReport to add results to.
        """
        self.report = report

    def validate(self, zones: list[ResourceConfig], vnets: list[ResourceConfig]) -> None:
        """Validate SDN zones and the vnets that use them.

        Args:
            zones: ``sdn_zone`` resources.
            vnets: ``sdn_vnet`` resources.
        """
        zone_kinds: dict[str, str] = {}
        for zone in zones:
            config = zone.config or {}
            self._validate_id("zone", zone)
            kind = config.get("kind", "vxlan")
            if kind not in VALID_ZONE_KINDS:
                self._error(
                    f"proxmox_sdn_zone_{zone.name}_kind",
                    f"SDN zone '{zone.name}': kind '{kind}' is not supported. "
                    f"Must be one of: {sorted(VALID_ZONE_KINDS)}",
                )
                continue
            zone_kinds[zone.name] = kind
            zone_kinds[sdn_id(zone)] = kind
            self._validate_vxlan_zone(zone.name, config)

        tags: dict[int, str] = {}
        for vnet in vnets:
            config = vnet.config or {}
            self._validate_id("vnet", vnet)
            zone_ref = config.get("zone")
            if zone_ref not in zone_kinds:
                self._error(
                    f"proxmox_sdn_vnet_{vnet.name}_zone",
                    f"SDN vnet '{vnet.name}': zone '{zone_ref}' is not a declared sdn_zone.",
                )
                continue
            if zone_kinds[zone_ref] == "vxlan":
                self._validate_vxlan_tag(vnet.name, config.get("tag"), tags)

    def _validate_id(self, kind: str, resource: ResourceConfig) -> None:
        value = sdn_id(resource)
        if not SDN_ID_PATTERN.match(value):
            self._error(
                f"proxmox_sdn_{kind}_{resource.name}_id",
                f"SDN {kind} '{resource.name}': id '{value}' must be 1-8 lowercase letters "
                "or digits, starting with a letter (set config.id to override the name).",
            )

    def _validate_vxlan_zone(self, name: str, config: dict[str, Any]) -> None:
        peers = config.get("peers")
        if not isinstance(peers, list) or not peers:
            self._error(
                f"proxmox_sdn_zone_{name}_peers",
                f"SDN zone '{name}': a VXLAN zone needs 'peers', a list of node IP addresses.",
            )
        else:
            for peer in peers:
                try:
                    ipaddress.ip_address(str(peer))
                except ValueError:
                    self._error(
                        f"proxmox_sdn_zone_{name}_peer_{peer}",
                        f"SDN zone '{name}': peer '{peer}' is not an IP address.",
                    )

        mtu = config.get("mtu")
        if mtu is not None and (not isinstance(mtu, int) or isinstance(mtu, bool) or mtu <= 0):
            self._error(
                f"proxmox_sdn_zone_{name}_mtu",
                f"SDN zone '{name}': mtu must be a positive integer (got {mtu!r}).",
            )

    def _validate_vxlan_tag(self, name: str, tag: Any, seen: dict[int, str]) -> None:
        if not isinstance(tag, int) or isinstance(tag, bool) or not 1 <= tag <= MAX_VNI:
            self._error(
                f"proxmox_sdn_vnet_{name}_tag",
                f"SDN vnet '{name}': a vnet in a VXLAN zone needs 'tag', "
                f"its VNI, from 1 to {MAX_VNI} (got {tag!r}).",
            )
            return
        if tag in seen:
            self._error(
                f"proxmox_sdn_vnet_{name}_tag_duplicate",
                f"SDN vnet '{name}': tag {tag} is already used by vnet '{seen[tag]}'.",
            )
            return
        seen[tag] = name

    def _error(self, check_name: str, message: str) -> None:
        self.report.add_check(
            check_name=check_name, passed=False, message=message, level=ValidationLevel.ERROR
        )
