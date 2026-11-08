"""Node validation for Proxmox."""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from infrafoundry.core.exceptions import APIError
from infrafoundry.core.protocols import SpecializedValidator
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.proxmox.validators.context import ProxmoxLiveContext

if TYPE_CHECKING:
    pass


class NodeValidator(SpecializedValidator[ProxmoxLiveContext]):
    """Validates Proxmox node availability and status."""

    def __init__(self, report: ValidationReport) -> None:
        """Initialize node validator.

        Args:
            report: ValidationReport to add results to
        """
        self.report = report

    @override
    def validate(self, context: ProxmoxLiveContext) -> None:
        """Validate that nodes exist and are online.

        Args:
            context: Validation context carrying the inputs this validator checks.
        """
        client = context.client
        nodes = context.nodes
        for node in nodes:
            try:
                status_data = client.get_json(f"nodes/{node}/status")
            except APIError:
                self.report.add_check(
                    check_name=f"proxmox_node_{node}",
                    passed=False,
                    message=f"Node '{node}' not accessible",
                    level=ValidationLevel.WARNING,
                )
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
