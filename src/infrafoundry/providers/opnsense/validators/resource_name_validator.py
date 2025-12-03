"""Resource name uniqueness validation for OPNsense."""

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport


class ResourceNameValidator:
    """Validates OPNsense resource name uniqueness."""

    def __init__(self, report: ValidationReport) -> None:
        """Initialize resource name validator.

        Args:
            report: ValidationReport to add results to
        """
        self.report = report

    def validate(self, resources: list[ResourceConfig]) -> None:
        """Check for duplicate resource names within each type.

        Args:
            resources: List of resources to check
        """
        # Group by type
        by_type: dict[str, list[str]] = {}
        for resource in resources:
            if resource.type not in by_type:
                by_type[resource.type] = []
            by_type[resource.type].append(resource.name)

        # Check for duplicates
        for resource_type, names in by_type.items():
            seen = set()
            for name in names:
                if name in seen:
                    self.report.add_check(
                        check_name=f"opnsense_{resource_type}_duplicate_{name}",
                        passed=False,
                        message=f"Duplicate {resource_type} name: '{name}'",
                        level=ValidationLevel.ERROR,
                    )
                seen.add(name)
