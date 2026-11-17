"""Offline virtual IP topology validator for OPNsense (#1391).

Plan-time checks (offline: YAML only, ADR-0023) over ``interfaces.virtual_ips`` resources,
for CARP VIPs only:

* **VHID reuse** (WARNING): the same VHID on more than one interface. CARP advertisements
  for one VHID share a multicast group per broadcast domain, so a reused VHID on different
  interfaces is a likely copy-paste mistake. The same VHID on one interface (several
  addresses, IPv4 plus IPv6) is legitimate and not reported.
* **Subnet membership** (ERROR): the CARP address must lie inside the network of the
  interface's static address in config, or inside the network of an ``ipalias`` VIP on the
  same interface (CARP on an alias subnet is a known pattern).

ipalias and proxyarp are excluded on purpose: OPNsense accepts IP aliases outside the
interface subnet (hence the ipalias-only ``gateway`` field), and proxyarp is commonly used
for routed blocks that are not on the interface. An ERROR blocks plan, so it runs only in
this narrow case.

The interface address comes from the ``interfaces.assignments`` resource whose name equals
the VIP's ``interface``. The subnet check is skipped, with no check emitted, when the
address is unknown: no assignment in config, the address family is not ``static``, the
address is malformed, the VIP is IPv6 link-local, or no index was built.

VIPs whose fields are malformed are skipped silently; ``VirtualIPValidator`` reports those.
"""

from __future__ import annotations

import ipaddress
from typing import Any, override

from infrafoundry.core.protocols import SpecializedValidator
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.opnsense.validators._xref import XRefIndex, resolve_xref
from infrafoundry.providers.opnsense.validators.context import OPNsenseValidationContext

_ASSIGNMENT_TYPE = "interfaces.assignments"
_VIP_TYPE = "interfaces.virtual_ips"
_VHID_MIN = 1
_VHID_MAX = 255

_Network = ipaddress.IPv4Network | ipaddress.IPv6Network
_Address = ipaddress.IPv4Address | ipaddress.IPv6Address


class VirtualIPTopologyValidator(SpecializedValidator[OPNsenseValidationContext]):
    """Checks CARP VHID reuse and CARP address membership in the interface subnet."""

    def __init__(self, report: ValidationReport) -> None:
        """Initialize the validator.

        Args:
            report: ``ValidationReport`` to add results to.
        """
        self.report = report

    @override
    def validate(self, context: OPNsenseValidationContext) -> None:
        """Run both checks over the CARP VIPs in ``context.virtual_ips``.

        Args:
            context: Context whose ``virtual_ips`` hold the VIPs and whose ``index`` holds
                the environment's resources (for interface addresses).
        """
        carp = [
            vip
            for vip in context.virtual_ips
            if isinstance(vip.config, dict) and vip.config.get("mode") == "carp"
        ]
        if not carp:
            return
        self._check_vhid_reuse(carp, context.index)
        for vip in carp:
            self._check_subnet_membership(vip, context.index)

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_vhid(raw: Any) -> int | None:
        """Return the VHID as an int in range, or None when absent or malformed."""
        if raw is None or isinstance(raw, bool) or not isinstance(raw, (str, int)):
            return None
        try:
            value = int(str(raw))
        except ValueError:
            return None
        if value < _VHID_MIN or value > _VHID_MAX:
            return None
        return value

    @staticmethod
    def _resolve_interface(vip: ResourceConfig, index: XRefIndex | None) -> str | None:
        """Return the VIP's interface name, resolving a dotted ref when possible."""
        interface = vip.config.get("interface")
        if not isinstance(interface, str) or not interface:
            return None
        if "." not in interface:
            return interface
        if index is None:
            return interface
        current_plugin = vip.type.split(".", 1)[0] if "." in vip.type else None
        resolved = resolve_xref(
            interface,
            expected_type=_ASSIGNMENT_TYPE,
            index=index,
            current_plugin=current_plugin,
        )
        return resolved.name if resolved is not None else interface

    @staticmethod
    def _parse_address(raw: Any) -> _Address | None:
        """Parse a VIP address, or return None when malformed."""
        if not isinstance(raw, str):
            return None
        try:
            return ipaddress.ip_address(raw)
        except ValueError:
            return None

    @staticmethod
    def _interface_network(assignment: ResourceConfig, version: int) -> _Network | None:
        """Return the static network of the assignment for an IP version, or None."""
        config: Any = assignment.config  # YAML may hold a non-mapping; guard below
        if not isinstance(config, dict):
            return None
        block = config.get("ipv4" if version == 4 else "ipv6")
        if not isinstance(block, dict) or block.get("type") != "static":
            return None
        address = block.get("address")
        subnet = block.get("subnet")
        if not isinstance(address, str) or subnet is None or isinstance(subnet, bool):
            return None
        try:
            iface = ipaddress.ip_interface(f"{address}/{subnet}")
        except ValueError:
            return None
        if iface.version != version:
            return None
        return iface.network

    def _alias_networks(self, interface: str, version: int, index: XRefIndex) -> list[_Network]:
        """Return the networks of ipalias VIPs on ``interface`` for an IP version."""
        networks: list[_Network] = []
        for other in index.get(_VIP_TYPE, {}).values():
            if not isinstance(other.config, dict) or other.config.get("mode") != "ipalias":
                continue
            if self._resolve_interface(other, index) != interface:
                continue
            address = other.config.get("address")
            prefix = other.config.get("network")
            if not isinstance(address, str) or prefix is None or isinstance(prefix, bool):
                continue
            try:
                iface = ipaddress.ip_interface(f"{address}/{prefix}")
            except ValueError:
                continue
            if iface.version == version:
                networks.append(iface.network)
        return networks

    # ------------------------------------------------------------------
    # checks
    # ------------------------------------------------------------------

    def _check_vhid_reuse(self, carp: list[ResourceConfig], index: XRefIndex | None) -> None:
        """Warn once per VHID that is used on more than one interface."""
        groups: dict[int, list[tuple[str, str]]] = {}
        for vip in carp:
            vhid = self._parse_vhid(vip.config.get("vhid"))
            interface = self._resolve_interface(vip, index)
            if vhid is None or interface is None:
                continue
            groups.setdefault(vhid, []).append((vip.name, interface))
        for vhid, members in sorted(groups.items()):
            if len({interface for _, interface in members}) < 2:
                continue
            listing = ", ".join(f"'{name}' on '{interface}'" for name, interface in members)
            self.report.add_check(
                check_name=f"virtual_ip_vhid_{vhid}_reused",
                passed=False,
                level=ValidationLevel.WARNING,
                message=(
                    f"CARP vhid {vhid} is used on more than one interface: {listing}. "
                    "Use a distinct vhid per interface unless the reuse is intended."
                ),
            )

    def _check_subnet_membership(self, vip: ResourceConfig, index: XRefIndex | None) -> None:
        """Fail when a CARP address is outside its interface's static network."""
        if index is None:
            return
        address = self._parse_address(vip.config.get("address"))
        interface = self._resolve_interface(vip, index)
        if address is None or interface is None:
            return
        if address.version == 6 and address.is_link_local:
            return
        assignment = index.get(_ASSIGNMENT_TYPE, {}).get(interface)
        if assignment is None:
            return
        network = self._interface_network(assignment, address.version)
        if network is None:
            return
        if address in network or any(
            address in net for net in self._alias_networks(interface, address.version, index)
        ):
            self.report.add_check(
                check_name=f"virtual_ip_{vip.name}_subnet",
                passed=True,
                level=ValidationLevel.INFO,
                message=(
                    f"CARP virtual_ip '{vip.name}' address {address} is inside the "
                    f"network of interface '{interface}'"
                ),
            )
            return
        self.report.add_check(
            check_name=f"virtual_ip_{vip.name}_subnet",
            passed=False,
            level=ValidationLevel.ERROR,
            message=(
                f"CARP virtual_ip '{vip.name}' address {address} is outside the network "
                f"{network} of interface '{interface}' (and of every ipalias on it)"
            ),
        )
