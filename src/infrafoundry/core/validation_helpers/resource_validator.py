"""Resource reference validation for infrastructure providers.

This module validates that resources referenced by other resources actually exist.
"""

import logging

from infrafoundry.core.validation import ValidationLevel, ValidationReport

logger = logging.getLogger(__name__)


class ResourceValidator:
    """Validates resource references and dependencies.

    Checks that resources referenced by other resources (e.g., templates,
    networks, aliases) actually exist in the configuration.

    Example:
        validator = ResourceValidator("proxmox", report)
        exists = validator.validate_resource_exists(
            resource_type="template",
            resource_name="ubuntu-22.04",
            existing_resources={"ubuntu-22.04", "debian-12"},
            parent_resource="web-server-01"
        )
    """

    def __init__(self, provider_name: str, report: ValidationReport) -> None:
        """Initialize resource validator.

        Args:
            provider_name: Provider name for check naming
            report: ValidationReport to add results to
        """
        self.provider_name = provider_name
        self.report = report

    def validate_resource_exists(
        self,
        resource_type: str,
        resource_name: str,
        existing_resources: set[str],
        parent_resource: str | None = None,
    ) -> bool:
        """Validate that a referenced resource exists.

        Args:
            resource_type: Type of resource (e.g., "template", "vlan", "alias")
            resource_name: Name of the resource being checked
            existing_resources: Set of existing resource names
            parent_resource: Optional parent resource name for context

        Returns:
            True if resource exists, False otherwise
        """
        check_name = f"{self.provider_name}_{resource_type}_{resource_name}"

        if resource_name in existing_resources:
            self._add_resource_exists_success(
                check_name, resource_type, resource_name, parent_resource
            )
            return True

        self.add_resource_missing_error(
            check_name, resource_type, resource_name, existing_resources, parent_resource
        )
        return False

    def _add_resource_exists_success(
        self,
        check_name: str,
        resource_type: str,
        resource_name: str,
        parent_resource: str | None,
    ) -> None:
        """Add success check for existing resource.

        Args:
            check_name: Validation check name
            resource_type: Type of resource
            resource_name: Name of resource
            parent_resource: Optional parent resource name
        """
        msg = f"{resource_type.title()} '{resource_name}' exists"
        if parent_resource:
            msg += f" (referenced by {parent_resource})"

        self.report.add_check(
            check_name=check_name,
            passed=True,
            message=msg,
            level=ValidationLevel.INFO,
        )

    def add_resource_missing_error(
        self,
        check_name: str,
        resource_type: str,
        resource_name: str,
        existing_resources: set[str],
        parent_resource: str | None,
    ) -> None:
        """Add error check for missing resource.

        Args:
            check_name: Validation check name
            resource_type: Type of resource
            resource_name: Name of resource
        existing_resources: Set of existing resources
        parent_resource: Optional parent resource name
        """
        msg = f"{resource_type.title()} '{resource_name}' not found"
        if parent_resource:
            msg += f" (referenced by {parent_resource})"

        self.report.add_check(
            check_name=check_name,
            passed=False,
            message=msg,
            level=ValidationLevel.ERROR,
            details={
                "resource_type": resource_type,
                "resource_name": resource_name,
                "existing_resources": list(existing_resources),
            },
        )
