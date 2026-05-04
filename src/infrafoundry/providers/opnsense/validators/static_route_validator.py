"""Static-route validation for OPNsense (ADR-0014, #722).

Plan-time validation for the ``static_routes`` resource type. The validator
is deliberately split from the service-side ``static_route_configs_from_resources``
parser: the parser raises on hard schema violations (missing required fields,
non-bool booleans), while the validator surfaces softer cross-resource
reference issues (unknown gateway) and field-shape problems (malformed CIDR,
host-bits-set CIDR, IP-vs-protocol mismatch) as ``ValidationReport`` entries.

Cross-reference targets:

- ``network``: must parse as an IPv4 or IPv6 network in CIDR notation
  (no host bits set).
- ``gateway``: must reference either a managed ``gateways`` resource
  declared in YAML *or* a live system gateway (e.g., ``WAN_DHCP``,
  ``WAN_DHCP6``) returned by OPNsense's ``searchGateway``. This mirrors
  the gateway validator's interface-acceptance pattern — operators can
  reference dynamic gateways without first declaring them as managed.
- Protocol match: the network's IP family must match the referenced
  gateway's IP protocol family (IPv4 network → IPv4 gateway, IPv6 network →
  IPv6 gateway). The validator enforces this for managed gateways (where
  ``protocol`` is in YAML); for live system gateways the heuristic is the
  trailing ``6`` convention (e.g., ``WAN_DHCP6`` is treated as IPv6).
"""

from __future__ import annotations

import ipaddress

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport


class StaticRouteValidator:
    """Validates OPNsense static-route resources against managed + live state."""

    def __init__(self, report: ValidationReport) -> None:
        """Initialize validator.

        Args:
            report: ValidationReport to add results to.
        """
        self.report = report

    def validate(
        self,
        static_routes: list[ResourceConfig],
        managed_gateways: list[ResourceConfig],
        gateway_names: set[str],
        existing_gateways: set[str],
    ) -> None:
        """Validate static-route resources.

        Args:
            static_routes: ``static_routes`` ``ResourceConfig`` entries.
            managed_gateways: ``gateways`` ``ResourceConfig`` entries —
                used to resolve the gateway's IP protocol for the protocol-
                match check.
            gateway_names: Set of managed gateway names declared in YAML.
            existing_gateways: Set of live gateway names returned by
                OPNsense's ``searchGateway`` (managed + dynamic).
        """
        gateway_protocols = _index_managed_gateway_protocols(managed_gateways)
        for route in static_routes:
            self._validate_one(
                route,
                gateway_names=gateway_names,
                existing_gateways=existing_gateways,
                gateway_protocols=gateway_protocols,
            )

    def _validate_one(
        self,
        route: ResourceConfig,
        *,
        gateway_names: set[str],
        existing_gateways: set[str],
        gateway_protocols: dict[str, str],
    ) -> None:
        """Run all checks for a single static-route entry."""
        network = self._validate_network(route)
        gateway = self._validate_gateway(
            route,
            gateway_names=gateway_names,
            existing_gateways=existing_gateways,
        )
        if network is not None and gateway is not None:
            self._validate_protocol_match(route, network, gateway, gateway_protocols)
        self._validate_bool(route, "enabled")
        self._validate_bool(route, "lock")
        self._validate_description(route)

    # ------------------------------------------------------------------
    # network (CIDR)
    # ------------------------------------------------------------------

    def _validate_network(
        self, route: ResourceConfig
    ) -> ipaddress.IPv4Network | ipaddress.IPv6Network | None:
        """Validate the ``network`` CIDR. Returns the parsed network or None."""
        network_raw = route.config.get("network")
        if network_raw is None:
            self.report.add_check(
                check_name=f"static_route_{route.name}_network",
                passed=False,
                message=f"static_route '{route.name}' missing required field 'network'",
                level=ValidationLevel.ERROR,
            )
            return None
        if not isinstance(network_raw, str) or not network_raw:
            self.report.add_check(
                check_name=f"static_route_{route.name}_network",
                passed=False,
                message=f"static_route '{route.name}' network must be a non-empty string",
                level=ValidationLevel.ERROR,
            )
            return None
        try:
            # ``strict=True`` rejects host bits set (e.g., ``10.0.0.1/24``).
            return ipaddress.ip_network(network_raw, strict=True)
        except ValueError as exc:
            self.report.add_check(
                check_name=f"static_route_{route.name}_network",
                passed=False,
                message=(
                    f"static_route '{route.name}' network {network_raw!r} "
                    f"is not a valid CIDR: {exc}"
                ),
                level=ValidationLevel.ERROR,
            )
            return None

    # ------------------------------------------------------------------
    # gateway (cross-ref into managed + live)
    # ------------------------------------------------------------------

    def _validate_gateway(
        self,
        route: ResourceConfig,
        *,
        gateway_names: set[str],
        existing_gateways: set[str],
    ) -> str | None:
        """Validate the ``gateway`` cross-reference. Returns the value or None."""
        gateway = route.config.get("gateway")
        if gateway is None:
            self.report.add_check(
                check_name=f"static_route_{route.name}_gateway",
                passed=False,
                message=f"static_route '{route.name}' missing required field 'gateway'",
                level=ValidationLevel.ERROR,
            )
            return None
        if not isinstance(gateway, str) or not gateway:
            self.report.add_check(
                check_name=f"static_route_{route.name}_gateway",
                passed=False,
                message=f"static_route '{route.name}' gateway must be a non-empty string",
                level=ValidationLevel.ERROR,
            )
            return None
        if gateway in gateway_names or gateway in existing_gateways:
            self.report.add_check(
                check_name=f"static_route_{route.name}_gateway",
                passed=True,
                message=f"Gateway '{gateway}' resolved for static_route '{route.name}'",
                level=ValidationLevel.INFO,
            )
            return gateway
        self.report.add_check(
            check_name=f"static_route_{route.name}_gateway",
            passed=False,
            message=(
                f"static_route '{route.name}' references unknown gateway '{gateway}'; "
                f"expected a managed 'gateways' resource name or a live OPNsense gateway"
            ),
            level=ValidationLevel.ERROR,
        )
        return None

    # ------------------------------------------------------------------
    # protocol match (network family vs gateway family)
    # ------------------------------------------------------------------

    def _validate_protocol_match(
        self,
        route: ResourceConfig,
        network: ipaddress.IPv4Network | ipaddress.IPv6Network,
        gateway: str,
        gateway_protocols: dict[str, str],
    ) -> None:
        """Validate that ``network``'s family matches the gateway's protocol.

        For managed gateways the protocol is read from YAML. For live
        system gateways the heuristic is the trailing ``6`` convention
        (e.g., ``WAN_DHCP6`` → IPv6, ``WAN_DHCP`` → IPv4).
        """
        gateway_protocol = gateway_protocols.get(gateway)
        if gateway_protocol is None:
            # Live system gateway — apply the trailing-6 heuristic.
            gateway_protocol = "inet6" if gateway.endswith("6") else "inet"

        is_v4_network = isinstance(network, ipaddress.IPv4Network)
        wants_v4 = gateway_protocol == "inet"
        if is_v4_network == wants_v4:
            return
        self.report.add_check(
            check_name=f"static_route_{route.name}_protocol_match",
            passed=False,
            message=(
                f"static_route '{route.name}' network family does not match gateway "
                f"'{gateway}' protocol: network is {'IPv4' if is_v4_network else 'IPv6'} "
                f"but gateway protocol is {gateway_protocol!r}"
            ),
            level=ValidationLevel.ERROR,
        )

    # ------------------------------------------------------------------
    # bool fields
    # ------------------------------------------------------------------

    def _validate_bool(self, route: ResourceConfig, field_name: str) -> None:
        if field_name not in route.config:
            return
        value = route.config[field_name]
        if not isinstance(value, bool):
            self.report.add_check(
                check_name=f"static_route_{route.name}_{field_name}",
                passed=False,
                message=(
                    f"static_route '{route.name}' {field_name} must be a boolean (true/false), "
                    f"got {type(value).__name__}"
                ),
                level=ValidationLevel.ERROR,
            )

    # ------------------------------------------------------------------
    # description
    # ------------------------------------------------------------------

    def _validate_description(self, route: ResourceConfig) -> None:
        if "description" not in route.config:
            return
        value = route.config["description"]
        if not isinstance(value, str):
            self.report.add_check(
                check_name=f"static_route_{route.name}_description",
                passed=False,
                message=(
                    f"static_route '{route.name}' description must be a string, "
                    f"got {type(value).__name__}"
                ),
                level=ValidationLevel.ERROR,
            )


def _index_managed_gateway_protocols(
    managed_gateways: list[ResourceConfig],
) -> dict[str, str]:
    """Build ``{gateway_name: protocol}`` from managed gateway resources.

    Skips entries with malformed protocol values — those have their own
    validator failures from ``GatewayValidator`` and we don't want to
    double-report.
    """
    result: dict[str, str] = {}
    for gateway in managed_gateways:
        protocol = gateway.config.get("protocol")
        if isinstance(protocol, str) and protocol in ("inet", "inet6"):
            result[gateway.name] = protocol
    return result
