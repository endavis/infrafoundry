"""DHCP static map validation for OPNsense."""

from typing import Any

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport


class DHCPValidator:
    """Validates OPNsense DHCP static map interface references."""

    def __init__(self, report: ValidationReport) -> None:
        """Initialize DHCP validator.

        Args:
            report: ValidationReport to add results to
        """
        self.report = report

    def validate(
        self,
        dhcp_maps: list[ResourceConfig],
        vlan_names: set[str],
        existing_interfaces: dict[str, Any],
    ) -> None:
        """Validate DHCP static maps reference valid interfaces.

        Args:
            dhcp_maps: List of DHCP static map resources
            vlan_names: Set of VLAN names in the configuration
            existing_interfaces: Existing interfaces from API
        """
        for dhcp_map in dhcp_maps:
            interface = dhcp_map.config.get("interface")
            if interface:
                # Check if it's in our VLAN config or exists in OPNsense
                if interface not in vlan_names and interface not in existing_interfaces:
                    self.report.add_check(
                        check_name=f"dhcp_static_map_{dhcp_map.name}_interface",
                        passed=False,
                        message=(
                            f"DHCP static map '{dhcp_map.name}' references "
                            f"undefined interface '{interface}'"
                        ),
                        level=ValidationLevel.WARNING,
                    )
                else:
                    self.report.add_check(
                        check_name=f"dhcp_static_map_{dhcp_map.name}_interface",
                        passed=True,
                        message=f"Interface '{interface}' found for DHCP map '{dhcp_map.name}'",
                        level=ValidationLevel.INFO,
                    )
