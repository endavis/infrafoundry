"""VLAN validation for OPNsense."""

from typing import Any

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport


class VLANValidator:
    """Validates OPNsense VLAN parent interface references."""

    def __init__(self, report: ValidationReport) -> None:
        """Initialize VLAN validator.

        Args:
            report: ValidationReport to add results to
        """
        self.report = report

    def validate(
        self,
        vlans: list[ResourceConfig],
        existing_interfaces: dict[str, Any],
    ) -> None:
        """Validate VLANs configuration.

        Args:
            vlans: List of VLAN resources
            existing_interfaces: Existing interfaces from API
        """
        for vlan in vlans:
            parent_if = vlan.config.get("parent")

            # Check if parent interface exists
            if parent_if and parent_if not in existing_interfaces:
                self.report.add_check(
                    check_name=f"vlan_{vlan.name}_parent",
                    passed=False,
                    message=(
                        f"VLAN '{vlan.name}' references undefined parent interface '{parent_if}'"
                    ),
                    level=ValidationLevel.ERROR,
                )
            elif parent_if:
                self.report.add_check(
                    check_name=f"vlan_{vlan.name}_parent",
                    passed=True,
                    message=f"Parent interface '{parent_if}' found for VLAN '{vlan.name}'",
                    level=ValidationLevel.INFO,
                )
