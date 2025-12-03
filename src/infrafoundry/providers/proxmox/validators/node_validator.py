"""Node validation for Proxmox."""

from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.core.validation_helpers import BaseAPIValidator


class NodeValidator:
    """Validates Proxmox node availability and status."""

    def __init__(self, api_validator: BaseAPIValidator, report: ValidationReport) -> None:
        """Initialize node validator.

        Args:
            api_validator: Shared API validator helper
            report: ValidationReport to add results to
        """
        self.api_validator = api_validator
        self.report = report

    def validate(self, api_url: str, headers: dict[str, str], nodes: set[str]) -> None:
        """Validate that nodes exist and are online.

        Args:
            api_url: Proxmox API base URL
            headers: HTTP headers with authorization
            nodes: Set of node names to validate
        """
        for node in nodes:
            status_data = self.api_validator.fetch_json(
                url=f"{api_url}/nodes/{node}/status",
                headers=headers,
                verify_ssl=False,
                timeout=10,
                check_name=f"proxmox_node_{node}",
                error_message=f"Node '{node}' not accessible (status {{status}})",
            )
            if not status_data:
                continue

            status = status_data.get("data", {})
            uptime_seconds = status.get("uptime", 0)
            uptime_formatted = self._format_uptime(uptime_seconds)
            self.report.add_check(
                check_name=f"proxmox_node_{node}",
                passed=True,
                message=f"Node '{node}' is online (uptime: {uptime_formatted})",
                level=ValidationLevel.INFO,
            )

    def _format_uptime(self, seconds: int) -> str:
        """Convert uptime in seconds to human-readable format.

        Args:
            seconds: Uptime in seconds

        Returns:
            Human-readable uptime string (e.g., "29 days, 3 hours, 15 minutes")
        """
        if seconds < 60:
            return f"{seconds} seconds"

        minutes = seconds // 60
        if minutes < 60:
            return f"{minutes} minutes"

        hours = minutes // 60
        remaining_minutes = minutes % 60
        if hours < 24:
            if remaining_minutes > 0:
                return f"{hours} hours, {remaining_minutes} minutes"
            return f"{hours} hours"

        days = hours // 24
        remaining_hours = hours % 24
        if remaining_hours > 0:
            return f"{days} days, {remaining_hours} hours"
        return f"{days} days"
