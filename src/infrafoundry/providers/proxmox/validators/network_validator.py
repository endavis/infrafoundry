"""Network bridge validation for Proxmox."""

from __future__ import annotations

from typing import TYPE_CHECKING

from infrafoundry.core.exceptions import APIError
from infrafoundry.core.validation import ValidationLevel, ValidationReport

if TYPE_CHECKING:
    from infrafoundry.providers.proxmox.api_client import ProxmoxClient


class NetworkValidator:
    """Validates Proxmox network bridge availability."""

    def __init__(self, report: ValidationReport) -> None:
        """Initialize network validator.

        Args:
            report: ValidationReport to add results to
        """
        self.report = report

    def validate(self, client: ProxmoxClient, bridges: set[tuple[str, str]]) -> None:
        """Validate that network bridges exist.

        Args:
            client: Proxmox API client
            bridges: Set of (node, bridge) tuples to validate
        """
        checked_bridges: set[tuple[str, str]] = set()
        for node, bridge in bridges:
            if (node, bridge) in checked_bridges:
                continue
            checked_bridges.add((node, bridge))

            try:
                network_data = client.get_json(f"nodes/{node}/network")
            except APIError:
                self.report.add_check(
                    check_name=f"proxmox_bridge_{node}_{bridge}",
                    passed=False,
                    message=(f"Bridge '{bridge}' on node '{node}' not accessible"),
                    level=ValidationLevel.WARNING,
                )
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
