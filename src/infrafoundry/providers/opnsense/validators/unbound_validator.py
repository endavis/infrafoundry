"""Unbound DNS host override validation for OPNsense."""

import ipaddress

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport


class UnboundValidator:
    """Validates OPNsense Unbound DNS host override configurations."""

    def __init__(self, report: ValidationReport) -> None:
        """Initialize Unbound validator.

        Args:
            report: ValidationReport to add results to
        """
        self.report = report

    def validate(self, resources: list[ResourceConfig]) -> None:
        """Validate Unbound host override resources.

        Checks that required fields (hostname, domain) are present and non-empty,
        and that server IP addresses (if provided) are valid.

        Args:
            resources: List of unbound_host_override resources to validate
        """
        for resource in resources:
            self._validate_hostname(resource)
            self._validate_domain(resource)
            self._validate_server(resource)

    def _validate_hostname(self, resource: ResourceConfig) -> None:
        """Validate hostname field is present and non-empty.

        Args:
            resource: Resource to validate
        """
        hostname = resource.config.get("hostname")
        if not hostname:
            self.report.add_check(
                check_name=f"unbound_host_override_{resource.name}_hostname",
                passed=False,
                message=(
                    f"Unbound host override '{resource.name}' is missing required field 'hostname'"
                ),
                level=ValidationLevel.ERROR,
            )
        else:
            self.report.add_check(
                check_name=f"unbound_host_override_{resource.name}_hostname",
                passed=True,
                message=(f"Hostname '{hostname}' set for override '{resource.name}'"),
                level=ValidationLevel.INFO,
            )

    def _validate_domain(self, resource: ResourceConfig) -> None:
        """Validate domain field is present and non-empty.

        Args:
            resource: Resource to validate
        """
        domain = resource.config.get("domain")
        if not domain:
            self.report.add_check(
                check_name=f"unbound_host_override_{resource.name}_domain",
                passed=False,
                message=(
                    f"Unbound host override '{resource.name}' is missing required field 'domain'"
                ),
                level=ValidationLevel.ERROR,
            )
        else:
            self.report.add_check(
                check_name=f"unbound_host_override_{resource.name}_domain",
                passed=True,
                message=(f"Domain '{domain}' set for override '{resource.name}'"),
                level=ValidationLevel.INFO,
            )

    def _validate_server(self, resource: ResourceConfig) -> None:
        """Validate server IP address if provided.

        Args:
            resource: Resource to validate
        """
        server = resource.config.get("server")
        if not server:
            return

        try:
            ipaddress.ip_address(server)
            self.report.add_check(
                check_name=f"unbound_host_override_{resource.name}_server",
                passed=True,
                message=(f"Server IP '{server}' is valid for override '{resource.name}'"),
                level=ValidationLevel.INFO,
            )
        except ValueError:
            self.report.add_check(
                check_name=f"unbound_host_override_{resource.name}_server",
                passed=False,
                message=(
                    f"Unbound host override '{resource.name}' has invalid "
                    f"server IP address '{server}'"
                ),
                level=ValidationLevel.ERROR,
            )
