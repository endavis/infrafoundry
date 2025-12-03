"""Resource validation utilities."""

import json
import logging
from typing import Any

from infrafoundry.core.validation import ValidationLevel, ValidationReport

logger = logging.getLogger(__name__)


class ResourceValidator:
    """Validates resource references and dependencies."""

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

        self._add_resource_missing_error(
            check_name, resource_type, resource_name, existing_resources, parent_resource
        )
        return False

    def validate_schema(
        self,
        resource: dict[str, Any],
        schema: dict[str, Any],
        check_name: str,
    ) -> bool:
        """Validate a resource dict against a JSON Schema-like mapping.

        This is a lightweight structural check to guard against obvious
        misconfigurations before deeper provider validation. It intentionally
        avoids external dependencies; callers can pass a subset of JSON Schema:
        - ``type`` for expected Python type (str, int, list, dict, bool)
        - ``required`` list of required keys (for object types)

        Args:
            resource: Resource configuration mapping.
            schema: Schema mapping with keys like ``type`` and ``required``.
            check_name: Validation check name for report entries.

        Returns:
            True when resource satisfies the schema, False otherwise.
        """
        expected_type = schema.get("type")
        if expected_type and not isinstance(resource, expected_type):
            self.report.add_check(
                check_name=check_name,
                passed=False,
                message=(
                    f"Invalid type for resource. Expected {expected_type.__name__}, "
                    f"got {type(resource).__name__}"
                ),
                level=ValidationLevel.ERROR,
            )
            return False

        required_fields = schema.get("required", [])
        missing = [field for field in required_fields if field not in resource]
        if missing:
            self.report.add_check(
                check_name=check_name,
                passed=False,
                message=f"Missing required fields: {', '.join(missing)}",
                level=ValidationLevel.ERROR,
                details={"required": required_fields, "resource": resource},
            )
            return False

        self.report.add_check(
            check_name=check_name,
            passed=True,
            message="Resource schema validation passed",
            level=ValidationLevel.INFO,
            details={"schema": json.dumps(schema, default=str), "resource": resource},
        )
        return True

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

    def _add_resource_missing_error(
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
