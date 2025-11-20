"""Helper utilities for adding validation checks to reports.

This module provides convenience methods for adding success and error checks
to validation reports with consistent formatting.
"""

import logging
from typing import Any

from infrafoundry.core.validation import ValidationLevel, ValidationReport

logger = logging.getLogger(__name__)


class ValidationReportHelper:
    """Convenience methods for adding checks to validation reports.

    Provides standardized success and error reporting to reduce boilerplate
    code in validation logic.

    Example:
        helper = ValidationReportHelper(report)
        helper.add_success_check(
            "proxmox_version",
            "Proxmox VE 8.1 detected"
        )
        helper.add_error_check(
            "proxmox_storage",
            "Storage pool 'local-lvm' not found",
            details={"available_pools": ["local", "nfs-backup"]}
        )
    """

    def __init__(self, report: ValidationReport) -> None:
        """Initialize report helper.

        Args:
            report: ValidationReport to add checks to
        """
        self.report = report

    def add_success_check(
        self,
        check_name: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Add a success validation check.

        Helper method for consistent success reporting.

        Args:
            check_name: Name of the validation check
            message: Success message
            details: Optional additional details
        """
        self.report.add_check(
            check_name=check_name,
            passed=True,
            message=message,
            level=ValidationLevel.INFO,
            details=details,
        )

    def add_error_check(
        self,
        check_name: str,
        message: str,
        level: ValidationLevel = ValidationLevel.ERROR,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Add an error validation check.

        Helper method for consistent error reporting.

        Args:
            check_name: Name of the validation check
            message: Error message
            level: Validation level (ERROR or WARNING)
            details: Optional additional details
        """
        self.report.add_check(
            check_name=check_name,
            passed=False,
            message=message,
            level=level,
            details=details,
        )

    def add_warning_check(
        self,
        check_name: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Add a warning validation check.

        Convenience method for warnings (passed=False, level=WARNING).

        Args:
            check_name: Name of the validation check
            message: Warning message
            details: Optional additional details
        """
        self.add_error_check(
            check_name=check_name,
            message=message,
            level=ValidationLevel.WARNING,
            details=details,
        )
