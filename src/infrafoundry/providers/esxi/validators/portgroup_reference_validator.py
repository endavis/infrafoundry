"""Portgroup reference validation for ESXi VMs."""

from typing import Any

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport


class PortgroupReferenceValidator:
    """Validates that VMs reference portgroups on the same host.

    Checks that every VM's network interface references a portgroup
    resource that exists on the same ESXi host within the resource list.
    """

    def __init__(self, report: ValidationReport) -> None:
        """Initialize portgroup reference validator.

        Args:
            report: ValidationReport to add results to
        """
        self.report = report

    def validate(self, resources: list[ResourceConfig]) -> None:
        """Validate VM-to-portgroup references.

        Args:
            resources: List of all resources to cross-reference
        """
        # Build a set of (host, portgroup_name) from portgroup resources
        portgroup_set: set[tuple[str, str]] = set()
        for resource in resources:
            if resource.type == "portgroup":
                host = resource.config.get("host", "")
                portgroup_set.add((host, resource.name))

        # Check each VM's network interfaces reference valid portgroups
        for resource in resources:
            if resource.type != "vm":
                continue

            host = resource.config.get("host", "")
            network = resource.config.get("network")
            if not network:
                continue

            nic_list: list[dict[str, Any]] = []
            if isinstance(network, dict):
                nic_list = [network]
            elif isinstance(network, list):
                nic_list = [n for n in network if isinstance(n, dict)]

            for nic in nic_list:
                portgroup_ref = nic.get("portgroup", "")
                if not portgroup_ref:
                    continue

                check_name = f"esxi_vm_portgroup_{resource.name}_{portgroup_ref}"

                if (host, portgroup_ref) in portgroup_set:
                    self.report.add_check(
                        check_name=check_name,
                        passed=True,
                        message=(
                            f"VM '{resource.name}' references portgroup "
                            f"'{portgroup_ref}' on host '{host}'"
                        ),
                        level=ValidationLevel.INFO,
                    )
                else:
                    self.report.add_check(
                        check_name=check_name,
                        passed=False,
                        message=(
                            f"VM '{resource.name}' references portgroup "
                            f"'{portgroup_ref}' which does not exist on host '{host}'"
                        ),
                        level=ValidationLevel.ERROR,
                    )
