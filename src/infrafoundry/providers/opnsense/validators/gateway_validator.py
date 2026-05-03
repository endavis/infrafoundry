"""Gateway validation for OPNsense (ADR-0014, #721).

Plan-time validation for the ``gateways`` resource type. The validator is
deliberately split from the service-side ``gateway_configs_from_resources``
parser: the parser raises on hard schema violations (wrong protocol, missing
required fields), while the validator surfaces softer cross-resource
reference issues (unknown interface) and field-shape problems
(out-of-range priority/weight, IP-vs-protocol mismatch) as
``ValidationReport`` entries.

Cross-reference targets:

- ``interface``: managed ``interface_assignments`` names plus live
  ``interfacesInfo`` keys.
- ``ipaddr`` and ``gateway``: literal IP matching ``protocol``, or the
  literal ``"dynamic"`` for ``ipaddr``.
- ``monitor`` (optional): IP literal or hostname.
- ``priority``: integer in 1-255.
- ``weight``: integer ≥ 1.
"""

from __future__ import annotations

import ipaddress
import re
from typing import Any

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport

# RFC 1123 hostname check — letters, digits, hyphens; labels separated by dots.
# Used as a fallback for ``monitor`` after the IP-literal check fails.
_HOSTNAME_RE = re.compile(
    r"^(?=.{1,253}$)(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.(?!-)[A-Za-z0-9-]{1,63}(?<!-))*$"
)


class GatewayValidator:
    """Validates OPNsense gateway resources against managed + live state."""

    def __init__(self, report: ValidationReport) -> None:
        """Initialize validator.

        Args:
            report: ValidationReport to add results to.
        """
        self.report = report

    def validate(
        self,
        gateways: list[ResourceConfig],
        interface_assignment_names: set[str],
        existing_interfaces: dict[str, Any],
    ) -> None:
        """Validate gateway resources.

        Args:
            gateways: ``gateways`` ``ResourceConfig`` entries.
            interface_assignment_names: Set of managed interface-assignment
                names declared in YAML.
            existing_interfaces: Live interface map from
                ``OPNsenseValidator._get_existing_interfaces``.
        """
        for gateway in gateways:
            self._validate_one(
                gateway,
                interface_assignment_names=interface_assignment_names,
                existing_interfaces=existing_interfaces,
            )

    def _validate_one(
        self,
        gateway: ResourceConfig,
        *,
        interface_assignment_names: set[str],
        existing_interfaces: dict[str, Any],
    ) -> None:
        """Run all checks for a single gateway entry."""
        protocol = self._validate_protocol(gateway)
        self._validate_interface(
            gateway,
            interface_assignment_names=interface_assignment_names,
            existing_interfaces=existing_interfaces,
        )
        self._validate_ipaddr(gateway, protocol)
        self._validate_gateway_field(gateway, protocol)
        self._validate_monitor(gateway, protocol)
        self._validate_priority(gateway)
        self._validate_weight(gateway)
        self._validate_bool(gateway, "defaultgw")
        self._validate_bool(gateway, "enabled")
        self._validate_bool(gateway, "lock")
        self._validate_bool(gateway, "monitor_disable")
        self._validate_bool(gateway, "monitor_noroute")
        self._validate_bool(gateway, "force_down")
        self._validate_bool(gateway, "fargw")
        self._validate_description(gateway)

    # ------------------------------------------------------------------
    # protocol
    # ------------------------------------------------------------------

    def _validate_protocol(self, gateway: ResourceConfig) -> str | None:
        """Validate the ``protocol`` discriminator. Returns the value or None."""
        protocol = gateway.config.get("protocol")
        if protocol not in ("inet", "inet6"):
            self.report.add_check(
                check_name=f"gateway_{gateway.name}_protocol",
                passed=False,
                message=(
                    f"gateway '{gateway.name}' protocol must be 'inet' or 'inet6', got {protocol!r}"
                ),
                level=ValidationLevel.ERROR,
            )
            return None
        return str(protocol)

    # ------------------------------------------------------------------
    # interface
    # ------------------------------------------------------------------

    def _validate_interface(
        self,
        gateway: ResourceConfig,
        *,
        interface_assignment_names: set[str],
        existing_interfaces: dict[str, Any],
    ) -> None:
        interface = gateway.config.get("interface")
        if interface is None:
            self.report.add_check(
                check_name=f"gateway_{gateway.name}_interface",
                passed=False,
                message=f"gateway '{gateway.name}' missing required field 'interface'",
                level=ValidationLevel.ERROR,
            )
            return
        if not isinstance(interface, str) or not interface:
            self.report.add_check(
                check_name=f"gateway_{gateway.name}_interface",
                passed=False,
                message=f"gateway '{gateway.name}' interface must be a non-empty string",
                level=ValidationLevel.ERROR,
            )
            return
        if interface in interface_assignment_names or interface in existing_interfaces:
            self.report.add_check(
                check_name=f"gateway_{gateway.name}_interface",
                passed=True,
                message=f"Interface '{interface}' resolved for gateway '{gateway.name}'",
                level=ValidationLevel.INFO,
            )
            return
        self.report.add_check(
            check_name=f"gateway_{gateway.name}_interface",
            passed=False,
            message=(
                f"gateway '{gateway.name}' references unknown interface '{interface}'; "
                f"expected a managed interface_assignment name or a live OPNsense interface"
            ),
            level=ValidationLevel.ERROR,
        )

    # ------------------------------------------------------------------
    # ipaddr (operator-facing literal)
    # ------------------------------------------------------------------

    def _validate_ipaddr(self, gateway: ResourceConfig, protocol: str | None) -> None:
        """Validate the operator-facing ``ipaddr`` field.

        Allowed values are the literal ``"dynamic"`` (only valid for
        protocol-matched dynamic gateways) or an IP literal whose family
        matches ``protocol``.
        """
        if "ipaddr" not in gateway.config:
            return
        ipaddr = gateway.config["ipaddr"]
        if not isinstance(ipaddr, str):
            self.report.add_check(
                check_name=f"gateway_{gateway.name}_ipaddr",
                passed=False,
                message=(
                    f"gateway '{gateway.name}' ipaddr must be a string, got {type(ipaddr).__name__}"
                ),
                level=ValidationLevel.ERROR,
            )
            return
        if ipaddr in ("", "dynamic"):
            return
        if not _ip_matches_protocol(ipaddr, protocol):
            self.report.add_check(
                check_name=f"gateway_{gateway.name}_ipaddr",
                passed=False,
                message=(
                    f"gateway '{gateway.name}' ipaddr {ipaddr!r} is not a valid "
                    f"IP literal for protocol {protocol!r} (or the keyword 'dynamic')"
                ),
                level=ValidationLevel.ERROR,
            )

    # ------------------------------------------------------------------
    # gateway (next-hop IP)
    # ------------------------------------------------------------------

    def _validate_gateway_field(self, gateway: ResourceConfig, protocol: str | None) -> None:
        """Validate the next-hop ``gateway`` IP."""
        if "gateway" not in gateway.config:
            # Required iff ipaddr is not "dynamic"; the parser raises in
            # that case. Here we only validate format if present.
            return
        value = gateway.config["gateway"]
        if not isinstance(value, str):
            self.report.add_check(
                check_name=f"gateway_{gateway.name}_gateway",
                passed=False,
                message=(
                    f"gateway '{gateway.name}' gateway must be a string, got {type(value).__name__}"
                ),
                level=ValidationLevel.ERROR,
            )
            return
        if value == "":
            # Empty is only valid when ipaddr == "dynamic"; the parser
            # enforces that constraint and raises otherwise. The validator
            # leaves an empty string alone here.
            return
        if not _ip_matches_protocol(value, protocol):
            self.report.add_check(
                check_name=f"gateway_{gateway.name}_gateway",
                passed=False,
                message=(
                    f"gateway '{gateway.name}' gateway {value!r} is not a valid "
                    f"IP literal for protocol {protocol!r}"
                ),
                level=ValidationLevel.ERROR,
            )

    # ------------------------------------------------------------------
    # monitor (optional)
    # ------------------------------------------------------------------

    def _validate_monitor(self, gateway: ResourceConfig, protocol: str | None) -> None:
        """Validate the optional ``monitor`` address (IP literal or hostname)."""
        if "monitor" not in gateway.config:
            return
        value = gateway.config["monitor"]
        if not isinstance(value, str):
            self.report.add_check(
                check_name=f"gateway_{gateway.name}_monitor",
                passed=False,
                message=(
                    f"gateway '{gateway.name}' monitor must be a string, got {type(value).__name__}"
                ),
                level=ValidationLevel.ERROR,
            )
            return
        if value == "":
            return
        if _ip_matches_protocol(value, protocol):
            return
        if _HOSTNAME_RE.match(value):
            return
        self.report.add_check(
            check_name=f"gateway_{gateway.name}_monitor",
            passed=False,
            message=(
                f"gateway '{gateway.name}' monitor {value!r} is not a valid "
                f"IP literal for protocol {protocol!r} or a valid hostname"
            ),
            level=ValidationLevel.ERROR,
        )

    # ------------------------------------------------------------------
    # priority / weight
    # ------------------------------------------------------------------

    def _validate_priority(self, gateway: ResourceConfig) -> None:
        if "priority" not in gateway.config:
            return
        priority_raw = gateway.config["priority"]
        try:
            priority = int(priority_raw)
        except (TypeError, ValueError):
            self.report.add_check(
                check_name=f"gateway_{gateway.name}_priority",
                passed=False,
                message=(
                    f"gateway '{gateway.name}' priority must be an integer (got {priority_raw!r})"
                ),
                level=ValidationLevel.ERROR,
            )
            return
        if not 1 <= priority <= 255:
            self.report.add_check(
                check_name=f"gateway_{gateway.name}_priority",
                passed=False,
                message=f"gateway '{gateway.name}' priority {priority} out of range 1-255",
                level=ValidationLevel.ERROR,
            )

    def _validate_weight(self, gateway: ResourceConfig) -> None:
        if "weight" not in gateway.config:
            return
        weight_raw = gateway.config["weight"]
        try:
            weight = int(weight_raw)
        except (TypeError, ValueError):
            self.report.add_check(
                check_name=f"gateway_{gateway.name}_weight",
                passed=False,
                message=(
                    f"gateway '{gateway.name}' weight must be an integer (got {weight_raw!r})"
                ),
                level=ValidationLevel.ERROR,
            )
            return
        if weight < 1:
            self.report.add_check(
                check_name=f"gateway_{gateway.name}_weight",
                passed=False,
                message=f"gateway '{gateway.name}' weight {weight} must be >= 1",
                level=ValidationLevel.ERROR,
            )

    # ------------------------------------------------------------------
    # bool fields
    # ------------------------------------------------------------------

    def _validate_bool(self, gateway: ResourceConfig, field_name: str) -> None:
        if field_name not in gateway.config:
            return
        value = gateway.config[field_name]
        if not isinstance(value, bool):
            self.report.add_check(
                check_name=f"gateway_{gateway.name}_{field_name}",
                passed=False,
                message=(
                    f"gateway '{gateway.name}' {field_name} must be a boolean (true/false), "
                    f"got {type(value).__name__}"
                ),
                level=ValidationLevel.ERROR,
            )

    # ------------------------------------------------------------------
    # description
    # ------------------------------------------------------------------

    def _validate_description(self, gateway: ResourceConfig) -> None:
        if "description" not in gateway.config:
            return
        value = gateway.config["description"]
        if not isinstance(value, str):
            self.report.add_check(
                check_name=f"gateway_{gateway.name}_description",
                passed=False,
                message=(
                    f"gateway '{gateway.name}' description must be a string, "
                    f"got {type(value).__name__}"
                ),
                level=ValidationLevel.ERROR,
            )


def _ip_matches_protocol(value: str, protocol: str | None) -> bool:
    """Return True if ``value`` parses as an IP whose family matches ``protocol``.

    When ``protocol`` is None (protocol validation already failed), any
    valid IP literal counts — the protocol error already surfaced.
    """
    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        return False
    if protocol is None:
        return True
    if protocol == "inet":
        return isinstance(ip, ipaddress.IPv4Address)
    if protocol == "inet6":
        return isinstance(ip, ipaddress.IPv6Address)
    return False
