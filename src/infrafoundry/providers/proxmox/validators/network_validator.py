"""Network bridge validation for Proxmox.

A bridge passes when it is a Linux bridge on the node or an applied SDN vnet
(#1154). SDN vnets are not listed in ``nodes/<node>/network``.
"""

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

    def validate(
        self,
        client: ProxmoxClient,
        bridges: set[tuple[str, str]],
        declared_vnets: frozenset[str] = frozenset(),
    ) -> None:
        """Validate that network bridges exist.

        Args:
            client: Proxmox API client
            bridges: Set of (node, bridge) tuples to validate
            declared_vnets: IDs of ``sdn_vnet`` resources in the validated set.
                A bridge that is one of these but not applied yet is a warning,
                not an error, since the same apply creates it.
        """
        applied_vnets: set[str] | None = None
        checked_bridges: set[tuple[str, str]] = set()
        for node, bridge in sorted(bridges):
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
                continue

            if applied_vnets is None:
                applied_vnets = self._applied_vnets(client)
            if bridge in applied_vnets:
                self.report.add_check(
                    check_name=f"proxmox_bridge_{node}_{bridge}",
                    passed=True,
                    message=f"Bridge '{bridge}' is an applied SDN vnet",
                    level=ValidationLevel.INFO,
                )
            elif bridge in declared_vnets:
                self.report.add_check(
                    check_name=f"proxmox_bridge_{node}_{bridge}",
                    passed=False,
                    message=(
                        f"Bridge '{bridge}' is a declared SDN vnet not yet applied; "
                        f"the apply creates it before node '{node}' needs it"
                    ),
                    level=ValidationLevel.WARNING,
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

    @staticmethod
    def _applied_vnets(client: ProxmoxClient) -> set[str]:
        """Return the IDs of SDN vnets in the cluster's running config.

        ``running=1`` leaves out vnets that are configured but not yet applied,
        whose bridges do not exist on the nodes. A cluster without SDN, or an
        unreadable endpoint, yields an empty set.
        """
        try:
            data = client.get_json("cluster/sdn/vnets", params={"running": 1})
        except APIError:
            return set()
        return {str(v["vnet"]) for v in data.get("data") or [] if v.get("vnet")}
