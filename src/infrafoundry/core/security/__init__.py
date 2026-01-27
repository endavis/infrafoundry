"""Security scanning module for infrastructure configurations.

This module provides security scanning capabilities for generated
Terraform and Ansible configurations using tools like Checkov.
"""

from infrafoundry.core.security.scanner import (
    ScanResult,
    ScanSeverity,
    SecurityScanner,
    SecurityViolation,
)

__all__ = [
    "ScanResult",
    "ScanSeverity",
    "SecurityScanner",
    "SecurityViolation",
]
