"""SSH connectivity validation for ESXi hosts."""

import socket

from infrafoundry.core.validation import ValidationLevel, ValidationReport


class HostConnectivityValidator:
    """Validates SSH connectivity to ESXi hosts.

    Uses socket.create_connection to check if port 22 is reachable
    on each configured ESXi host.
    """

    def __init__(self, report: ValidationReport, *, timeout: float = 5.0) -> None:
        """Initialize host connectivity validator.

        Args:
            report: ValidationReport to add results to
            timeout: Connection timeout in seconds
        """
        self.report = report
        self.timeout = timeout

    def validate(self, hostname: str, port: int = 22) -> None:
        """Validate that an ESXi host is reachable via SSH.

        Args:
            hostname: Host name or IP address to check
            port: Port to check (default: 22 for SSH)
        """
        check_name = f"esxi_host_connectivity_{hostname}"
        try:
            conn = socket.create_connection((hostname, port), timeout=self.timeout)
            conn.close()
            self.report.add_check(
                check_name=check_name,
                passed=True,
                message=f"ESXi host '{hostname}' is reachable on port {port}",
                level=ValidationLevel.INFO,
            )
        except OSError as exc:
            self.report.add_check(
                check_name=check_name,
                passed=False,
                message=(f"ESXi host '{hostname}' is not reachable on port {port}: {exc}"),
                level=ValidationLevel.ERROR,
            )
