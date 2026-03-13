"""Security scanner base classes and types."""

from __future__ import annotations

import json
import shutil
import subprocess  # nosec B404 - required for running checkov
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, override

from infrafoundry.core.base_manager import BaseManager


class ScanSeverity(StrEnum):
    """Severity levels for security violations."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


@dataclass
class SecurityViolation:
    """A single security violation found during scanning."""

    check_id: str
    check_name: str
    severity: ScanSeverity
    resource: str
    file_path: str
    description: str
    guideline: str | None = None
    line_range: tuple[int, int] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert violation to dictionary."""
        return {
            "check_id": self.check_id,
            "check_name": self.check_name,
            "severity": self.severity.value,
            "resource": self.resource,
            "file_path": self.file_path,
            "description": self.description,
            "guideline": self.guideline,
            "line_range": self.line_range,
        }


@dataclass
class ScanResult:
    """Result of a security scan."""

    passed: bool
    violations: list[SecurityViolation] = field(default_factory=list)
    passed_checks: int = 0
    failed_checks: int = 0
    skipped_checks: int = 0
    scan_duration_seconds: float = 0.0
    scanner_version: str | None = None
    error: str | None = None

    @property
    def total_checks(self) -> int:
        """Total number of checks performed."""
        return self.passed_checks + self.failed_checks + self.skipped_checks

    def get_violations_by_severity(self, severity: ScanSeverity) -> list[SecurityViolation]:
        """Get violations filtered by severity."""
        return [v for v in self.violations if v.severity == severity]

    def to_dict(self) -> dict[str, Any]:
        """Convert result to dictionary."""
        return {
            "passed": self.passed,
            "violations": [v.to_dict() for v in self.violations],
            "passed_checks": self.passed_checks,
            "failed_checks": self.failed_checks,
            "skipped_checks": self.skipped_checks,
            "total_checks": self.total_checks,
            "scan_duration_seconds": self.scan_duration_seconds,
            "scanner_version": self.scanner_version,
            "error": self.error,
        }


class SecurityScanner(BaseManager):
    """Security scanner using Checkov for Terraform/Ansible configurations.

    Scans generated infrastructure configurations for security issues,
    misconfigurations, and compliance violations.
    """

    def __init__(
        self,
        severity_threshold: ScanSeverity = ScanSeverity.HIGH,
        skip_checks: list[str] | None = None,
        frameworks: list[str] | None = None,
    ) -> None:
        """Initialize security scanner.

        Args:
            severity_threshold: Minimum severity to fail on (default: HIGH)
            skip_checks: List of check IDs to skip
            frameworks: Frameworks to scan (default: terraform, ansible)
        """
        super().__init__()
        self.severity_threshold = severity_threshold
        self.skip_checks = skip_checks or []
        self.frameworks = frameworks or ["terraform", "ansible"]
        self._checkov_path: str | None = None

    @override
    def cleanup(self) -> None:
        """Clean up scanner resources.

        SecurityScanner has no persistent resources to clean up.
        """
        pass

    @property
    def checkov_path(self) -> str:
        """Get path to checkov executable."""
        if self._checkov_path is None:
            path = shutil.which("checkov")
            if path is None:
                raise FileNotFoundError(
                    "checkov not found on PATH. Install with: pip install checkov"
                )
            self._checkov_path = path
        return self._checkov_path

    def is_available(self) -> bool:
        """Check if checkov is installed and available."""
        try:
            _ = self.checkov_path
            return True
        except FileNotFoundError:
            return False

    def get_version(self) -> str | None:
        """Get checkov version."""
        try:
            result = subprocess.run(  # nosec B603 - using list args, not shell
                [self.checkov_path, "--version"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            return result.stdout.strip() if result.returncode == 0 else None
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return None

    def scan(self, directory: Path, timeout: int = 300) -> ScanResult:
        """Scan a directory for security issues.

        Args:
            directory: Directory to scan (should contain terraform/ansible files)
            timeout: Maximum scan time in seconds

        Returns:
            ScanResult with violations and summary
        """
        import time

        start_time = time.time()

        if not directory.exists():
            return ScanResult(
                passed=False,
                error=f"Directory not found: {directory}",
            )

        try:
            result = self._run_checkov(directory, timeout)
            result.scan_duration_seconds = time.time() - start_time
            result.scanner_version = self.get_version()
            return result
        except FileNotFoundError as exc:
            return ScanResult(
                passed=False,
                error=str(exc),
                scan_duration_seconds=time.time() - start_time,
            )
        except subprocess.TimeoutExpired:
            return ScanResult(
                passed=False,
                error=f"Scan timed out after {timeout} seconds",
                scan_duration_seconds=timeout,
            )
        except Exception as exc:
            self._log_error(f"Security scan failed: {exc}")
            return ScanResult(
                passed=False,
                error=str(exc),
                scan_duration_seconds=time.time() - start_time,
            )

    def _run_checkov(self, directory: Path, timeout: int) -> ScanResult:
        """Run checkov and parse results."""
        cmd = [
            self.checkov_path,
            "-d",
            str(directory),
            "-o",
            "json",
            "--compact",
            "--quiet",
        ]

        # Add framework filters
        for framework in self.frameworks:
            cmd.extend(["--framework", framework])

        # Add skip checks
        for check_id in self.skip_checks:
            cmd.extend(["--skip-check", check_id])

        self._log_debug(f"Running: {' '.join(cmd)}")

        result = subprocess.run(  # nosec B603 - using list args, not shell
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=directory,
        )

        # Checkov returns non-zero if it finds issues
        return self._parse_checkov_output(result.stdout, result.stderr)

    def _parse_checkov_output(self, stdout: str, stderr: str) -> ScanResult:
        """Parse checkov JSON output into ScanResult."""
        if not stdout.strip():
            # No output might mean no files to scan
            if "No files to scan" in stderr or not stderr:
                return ScanResult(passed=True)
            return ScanResult(passed=False, error=stderr)

        try:
            data = json.loads(stdout)
        except json.JSONDecodeError as exc:
            self._log_warning(f"Failed to parse checkov output: {exc}")
            return ScanResult(passed=False, error=f"Invalid checkov output: {exc}")

        violations: list[SecurityViolation] = []
        passed_checks = 0
        failed_checks = 0
        skipped_checks = 0

        # Handle both single result and array of results
        results_list = data if isinstance(data, list) else [data]

        for result_block in results_list:
            if not isinstance(result_block, dict):
                continue

            # Handle check_type results (terraform, ansible, etc.)
            check_results = result_block.get("results", {})

            # Count passed checks
            for _passed_check in check_results.get("passed_checks", []):
                passed_checks += 1

            # Count skipped checks
            for _skipped_check in check_results.get("skipped_checks", []):
                skipped_checks += 1

            # Process failed checks
            for failed_check in check_results.get("failed_checks", []):
                failed_checks += 1
                violation = self._parse_violation(failed_check)
                if violation:
                    violations.append(violation)

        # Determine if scan passed based on severity threshold
        threshold_order = [
            ScanSeverity.CRITICAL,
            ScanSeverity.HIGH,
            ScanSeverity.MEDIUM,
            ScanSeverity.LOW,
            ScanSeverity.INFO,
        ]
        threshold_idx = threshold_order.index(self.severity_threshold)
        blocking_severities = set(threshold_order[: threshold_idx + 1])

        blocking_violations = [v for v in violations if v.severity in blocking_severities]
        passed = len(blocking_violations) == 0

        return ScanResult(
            passed=passed,
            violations=violations,
            passed_checks=passed_checks,
            failed_checks=failed_checks,
            skipped_checks=skipped_checks,
        )

    def _parse_violation(self, check_data: dict[str, Any]) -> SecurityViolation | None:
        """Parse a single failed check into a SecurityViolation."""
        try:
            severity_str = check_data.get("check_result", {}).get("severity", "medium")
            severity_str = severity_str.lower() if severity_str else "medium"

            # Map checkov severity to our enum
            severity_map = {
                "critical": ScanSeverity.CRITICAL,
                "high": ScanSeverity.HIGH,
                "medium": ScanSeverity.MEDIUM,
                "low": ScanSeverity.LOW,
                "info": ScanSeverity.INFO,
                "none": ScanSeverity.INFO,
            }
            severity = severity_map.get(severity_str, ScanSeverity.MEDIUM)

            # Extract line range if available
            line_range = None
            if "file_line_range" in check_data:
                lines = check_data["file_line_range"]
                if isinstance(lines, list) and len(lines) >= 2:
                    line_range = (lines[0], lines[1])

            return SecurityViolation(
                check_id=check_data.get("check_id", "UNKNOWN"),
                check_name=check_data.get("check_name", "Unknown check"),
                severity=severity,
                resource=check_data.get("resource", "unknown"),
                file_path=check_data.get("file_path", "unknown"),
                description=check_data.get("check_name", ""),
                guideline=check_data.get("guideline"),
                line_range=line_range,
            )
        except Exception as exc:
            self._log_warning(f"Failed to parse violation: {exc}")
            return None
