"""OVF deployment validation for ESXi provider."""

import re
from pathlib import Path

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport

MAC_ADDRESS_PATTERN = re.compile(r"^[0-9A-Fa-f]{2}(:[0-9A-Fa-f]{2}){5}$")


class OvfDeploymentValidator:
    """Validates OVF deployment resource configurations.

    Checks that OVF deployment resources have all required fields
    and that network mappings are properly defined.
    """

    def __init__(self, report: ValidationReport) -> None:
        """Initialize OVF deployment validator.

        Args:
            report: ValidationReport to add results to
        """
        self.report = report

    def validate(self, resources: list[ResourceConfig]) -> None:
        """Validate OVF deployment resources.

        Args:
            resources: List of all resources to validate
        """
        for resource in resources:
            if resource.type != "ovf_deployment":
                continue
            self._validate_resource(resource)

    def _validate_resource(self, resource: ResourceConfig) -> None:
        """Validate a single OVF deployment resource.

        Args:
            resource: The OVF deployment resource to validate
        """
        config = resource.config

        # Validate required: host
        host = config.get("host", "")
        self.report.add_check(
            check_name=f"esxi_ovf_deployment_host_{resource.name}",
            passed=bool(host),
            message=(
                f"OVF deployment '{resource.name}' has host '{host}'"
                if host
                else f"OVF deployment '{resource.name}' is missing required field 'host'"
            ),
            level=ValidationLevel.INFO if host else ValidationLevel.ERROR,
        )

        # Validate required: ovf_source
        ovf_source = config.get("ovf_source", "")
        self.report.add_check(
            check_name=f"esxi_ovf_deployment_ovf_source_{resource.name}",
            passed=bool(ovf_source),
            message=(
                f"OVF deployment '{resource.name}' has ovf_source '{ovf_source}'"
                if ovf_source
                else f"OVF deployment '{resource.name}' is missing required field 'ovf_source'"
            ),
            level=ValidationLevel.INFO if ovf_source else ValidationLevel.ERROR,
        )

        # Warn if ovf_source file doesn't exist locally
        if ovf_source and not Path(ovf_source).exists():
            self.report.add_check(
                check_name=f"esxi_ovf_deployment_ovf_source_exists_{resource.name}",
                passed=True,
                message=(
                    f"OVF deployment '{resource.name}' ovf_source '{ovf_source}' "
                    f"not found locally (may be valid if path is on remote host)"
                ),
                level=ValidationLevel.WARNING,
            )

        # Validate required: disk_store
        disk_store = config.get("disk_store", "")
        self.report.add_check(
            check_name=f"esxi_ovf_deployment_disk_store_{resource.name}",
            passed=bool(disk_store),
            message=(
                f"OVF deployment '{resource.name}' has disk_store '{disk_store}'"
                if disk_store
                else f"OVF deployment '{resource.name}' is missing required field 'disk_store'"
            ),
            level=ValidationLevel.INFO if disk_store else ValidationLevel.ERROR,
        )

        # Validate required: network_map (must be non-empty dict)
        network_map = config.get("network_map")
        if not network_map or not isinstance(network_map, dict):
            self.report.add_check(
                check_name=f"esxi_ovf_deployment_network_map_{resource.name}",
                passed=False,
                message=(
                    f"OVF deployment '{resource.name}' is missing required field "
                    f"'network_map' or it is empty"
                ),
                level=ValidationLevel.ERROR,
            )
        else:
            # Check that all network_map values are non-empty
            empty_values = [k for k, v in network_map.items() if not v]
            if empty_values:
                self.report.add_check(
                    check_name=f"esxi_ovf_deployment_network_map_{resource.name}",
                    passed=False,
                    message=(
                        f"OVF deployment '{resource.name}' has empty port group names "
                        f"for network mappings: {', '.join(empty_values)}"
                    ),
                    level=ValidationLevel.ERROR,
                )
            else:
                self.report.add_check(
                    check_name=f"esxi_ovf_deployment_network_map_{resource.name}",
                    passed=True,
                    message=(
                        f"OVF deployment '{resource.name}' has valid network_map "
                        f"with {len(network_map)} mapping(s)"
                    ),
                    level=ValidationLevel.INFO,
                )

        # Validate optional: mac_map
        mac_map = config.get("mac_map")
        if mac_map and isinstance(mac_map, dict):
            self._validate_mac_map(resource, mac_map, network_map)

    def _validate_mac_map(
        self,
        resource: ResourceConfig,
        mac_map: dict[str, str],
        network_map: dict[str, str] | None,
    ) -> None:
        """Validate mac_map entries against network_map and MAC address format.

        Args:
            resource: The OVF deployment resource being validated
            mac_map: Dict mapping OVF network names to MAC addresses
            network_map: Dict mapping OVF network names to portgroup names
        """
        # Validate keys are a subset of network_map keys
        network_map_keys = (
            set(network_map.keys()) if network_map and isinstance(network_map, dict) else set()
        )
        invalid_keys = [k for k in mac_map if k not in network_map_keys]
        if invalid_keys:
            self.report.add_check(
                check_name=f"esxi_ovf_deployment_mac_map_keys_{resource.name}",
                passed=False,
                message=(
                    f"OVF deployment '{resource.name}' mac_map has keys not in "
                    f"network_map: {', '.join(invalid_keys)}"
                ),
                level=ValidationLevel.ERROR,
            )

        # Validate MAC address format
        invalid_macs = {k: v for k, v in mac_map.items() if not MAC_ADDRESS_PATTERN.match(v)}
        if invalid_macs:
            details = ", ".join(f"{k}={v}" for k, v in invalid_macs.items())
            self.report.add_check(
                check_name=f"esxi_ovf_deployment_mac_map_format_{resource.name}",
                passed=False,
                message=(
                    f"OVF deployment '{resource.name}' mac_map has invalid MAC "
                    f"address format (expected XX:XX:XX:XX:XX:XX): {details}"
                ),
                level=ValidationLevel.ERROR,
            )

        if not invalid_keys and not invalid_macs:
            self.report.add_check(
                check_name=f"esxi_ovf_deployment_mac_map_{resource.name}",
                passed=True,
                message=(
                    f"OVF deployment '{resource.name}' has valid mac_map "
                    f"with {len(mac_map)} mapping(s)"
                ),
                level=ValidationLevel.INFO,
            )
