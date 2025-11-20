"""Validation framework for pre-flight checks before infrastructure changes."""

from dataclasses import dataclass
from enum import Enum
from typing import Any


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
