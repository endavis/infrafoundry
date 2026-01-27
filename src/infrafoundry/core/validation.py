"""Validation framework for pre-flight checks before infrastructure changes."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from infrafoundry.core.provider import ResourceConfig
    from infrafoundry.core.types import EnvironmentData


class ValidationLevel(Enum):
    """Severity level for validation issues."""

    INFO = "info"  # Informational, won't block deployment
    WARNING = "warning"  # Should be reviewed but won't block
    ERROR = "error"  # Will block deployment


@dataclass
class ValidationResult:
    """Result of a validation check."""

    check_name: str
    level: ValidationLevel
    passed: bool
    message: str
    details: dict[str, Any] | None = None

    def __repr__(self) -> str:
        """String representation of validation result."""
        status = "✓" if self.passed else "✗"
        return f"[{self.level.value.upper()}] {status} {self.check_name}: {self.message}"


class ValidationReport:
    """Collection of validation results."""

    def __init__(self) -> None:
        """Initialize empty validation report."""
        self.results: list[ValidationResult] = []

    def add(self, result: ValidationResult) -> None:
        """Add a validation result to the report."""
        self.results.append(result)

    def add_check(
        self,
        check_name: str,
        passed: bool,
        message: str,
        level: ValidationLevel = ValidationLevel.ERROR,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Add a validation check result.

        Args:
            check_name: Name of the validation check
            passed: Whether the check passed
            message: Description of the result
            level: Severity level (ERROR, WARNING, INFO)
            details: Additional details about the check
        """
        self.add(
            ValidationResult(
                check_name=check_name,
                level=level,
                passed=passed,
                message=message,
                details=details,
            )
        )

    def has_errors(self) -> bool:
        """Check if report contains any errors."""
        return any(not r.passed and r.level == ValidationLevel.ERROR for r in self.results)

    def has_warnings(self) -> bool:
        """Check if report contains any warnings."""
        return any(not r.passed and r.level == ValidationLevel.WARNING for r in self.results)

    def get_summary(self) -> dict[str, int]:
        """Get summary counts of validation results.

        Returns:
            Dict with counts of passed, errors, warnings, and info
        """
        return {
            "total": len(self.results),
            "passed": sum(1 for r in self.results if r.passed),
            "errors": sum(
                1 for r in self.results if not r.passed and r.level == ValidationLevel.ERROR
            ),
            "warnings": sum(
                1 for r in self.results if not r.passed and r.level == ValidationLevel.WARNING
            ),
            "info": sum(
                1 for r in self.results if not r.passed and r.level == ValidationLevel.INFO
            ),
        }

    def __repr__(self) -> str:
        """String representation of validation report."""
        summary = self.get_summary()
        lines = [
            "\nValidation Report:",
            f"  Total checks: {summary['total']}",
            f"  ✓ Passed: {summary['passed']}",
        ]
        if summary["errors"]:
            lines.append(f"  ✗ Errors: {summary['errors']}")
        if summary["warnings"]:
            lines.append(f"  ⚠ Warnings: {summary['warnings']}")
        if summary["info"]:
            lines.append(f"  (i) Info: {summary['info']}")

        lines.append("\nDetails:")
        for result in self.results:
            lines.append(f"  {result}")

        return "\n".join(lines)


@runtime_checkable
class ProviderValidator(Protocol):
    """Protocol defining the standard interface for provider validators.

    All provider validators should implement this protocol to ensure
    consistent validation behavior across providers.

    Attributes:
        env_config: Environment configuration including provider_settings
        report: ValidationReport to add results to

    Example:
        class MyProviderValidator:
            def __init__(
                self,
                env_config: EnvironmentData,
                report: ValidationReport,
            ) -> None:
                self.env_config = env_config
                self.report = report

            def validate_connectivity(self) -> None:
                # Check API connectivity
                ...

            def validate_references(self, resources: list[ResourceConfig]) -> None:
                # Validate resource references
                ...
    """

    env_config: EnvironmentData
    report: ValidationReport

    def validate_connectivity(self) -> None:
        """Validate connectivity to the provider's API.

        Should check:
        - Required credentials are present
        - API endpoint is reachable
        - Authentication is valid

        Results should be added to self.report.
        """
        ...

    def validate_references(self, resources: list[ResourceConfig]) -> None:
        """Validate resource references against live state or config.

        Should check:
        - Referenced resources exist (in config or live API)
        - No duplicate identifiers
        - Cross-resource references are valid

        Args:
            resources: List of resources to validate

        Results should be added to self.report.
        """
        ...
