"""Network bridge validation for Proxmox."""

from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.core.validation_helpers import BaseAPIValidator


class NetworkValidator:
    """Validates Proxmox network bridge availability."""

    def __init__(self, api_validator: BaseAPIValidator, report: ValidationReport) -> None:
        """Initialize network validator.

        Args:
            api_validator: Shared API validator helper
            report: ValidationReport to add results to
        """
        self.api_validator = api_validator
        self.report = report

    def validate(
        self, api_url: str, headers: dict[str, str], bridges: set[tuple[str, str]]
    ) -> None:
        """Validate that network bridges exist.

        Args:
            api_url: Proxmox API base URL
            headers: HTTP headers with authorization
            bridges: Set of (node, bridge) tuples to validate
        """
        checked_bridges = set()
        for node, bridge in bridges:
            if (node, bridge) in checked_bridges:
                continue
            checked_bridges.add((node, bridge))

            network_data = self.api_validator.fetch_json(
                url=f"{api_url}/nodes/{node}/network",
                headers=headers,
                verify_ssl=False,
                timeout=10,
                check_name=f"proxmox_bridge_{node}_{bridge}",
                error_message=(
                    f"Bridge '{bridge}' on node '{node}' not accessible (status {{status}})"
                ),
                error_level=ValidationLevel.WARNING,
            )
            if not network_data:
                continue

            networks = network_data.get("data", [])
            bridge_info = next(
                (n for n in networks if n.get("type") == "bridge" and n.get("iface") == bridge),
                None,
            )
            if bridge_info:
                self.report.add_check(
                    check_name=f"proxmox_bridge_{node}_{bridge}",
                    passed=True,
                    message=f"Bridge '{bridge}' exists on node '{node}'",
                    level=ValidationLevel.INFO,
                )
            else:
                available = [n.get("iface") for n in networks if n.get("type") == "bridge"]
                self.report.add_check(
                    check_name=f"proxmox_bridge_{node}_{bridge}",
                    passed=False,
                    message=(
                        f"Bridge '{bridge}' not found on node '{node}'. "
                        f"Available bridges: {available}"
                    ),
                    level=ValidationLevel.ERROR,
                )
