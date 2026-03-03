"""Vswitch reference validation for ESXi portgroups."""

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport


class VswitchReferenceValidator:
    """Validates that portgroups reference vswitches on the same host.

    Checks that every portgroup's 'vswitch' field references a vswitch
    resource that exists on the same ESXi host within the resource list.
    """

    def __init__(self, report: ValidationReport) -> None:
        """Initialize vswitch reference validator.

        Args:
            report: ValidationReport to add results to
        """
        self.report = report

    def validate(self, resources: list[ResourceConfig]) -> None:
        """Validate portgroup-to-vswitch references.

        Args:
            resources: List of all resources to cross-reference
        """
        # Build a set of (host, vswitch_name) from vswitch resources
        vswitch_set: set[tuple[str, str]] = set()
        for resource in resources:
            if resource.type == "vswitch":
                host = resource.config.get("host", "")
                vswitch_set.add((host, resource.name))

        # Check each portgroup references a valid vswitch on same host
        for resource in resources:
            if resource.type != "portgroup":
                continue

            host = resource.config.get("host", "")
            vswitch_ref = resource.config.get("vswitch", "")
            check_name = f"esxi_portgroup_vswitch_{resource.name}"

            if not vswitch_ref:
                self.report.add_check(
                    check_name=check_name,
                    passed=False,
                    message=(f"Portgroup '{resource.name}' has no vswitch reference"),
                    level=ValidationLevel.ERROR,
                )
                continue

            if (host, vswitch_ref) in vswitch_set:
                self.report.add_check(
                    check_name=check_name,
                    passed=True,
                    message=(
                        f"Portgroup '{resource.name}' references vswitch "
                        f"'{vswitch_ref}' on host '{host}'"
                    ),
                    level=ValidationLevel.INFO,
                )
            else:
                self.report.add_check(
                    check_name=check_name,
                    passed=False,
                    message=(
                        f"Portgroup '{resource.name}' references vswitch "
                        f"'{vswitch_ref}' which does not exist on host '{host}'"
                    ),
                    level=ValidationLevel.ERROR,
                )
