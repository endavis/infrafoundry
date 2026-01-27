"""Unit tests for security scanner."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from infrafoundry.core.security import (
    ScanResult,
    ScanSeverity,
    SecurityScanner,
    SecurityViolation,
)


class TestScanSeverity:
    """Tests for ScanSeverity enum."""

    def test_severity_values(self):
        """Test severity enum values."""
        assert ScanSeverity.CRITICAL.value == "critical"
        assert ScanSeverity.HIGH.value == "high"
        assert ScanSeverity.MEDIUM.value == "medium"
        assert ScanSeverity.LOW.value == "low"
        assert ScanSeverity.INFO.value == "info"


class TestSecurityViolation:
    """Tests for SecurityViolation dataclass."""

    def test_create_violation(self):
        """Test creating a security violation."""
        violation = SecurityViolation(
            check_id="CKV_AWS_1",
            check_name="Ensure S3 bucket has encryption",
            severity=ScanSeverity.HIGH,
            resource="aws_s3_bucket.test",
            file_path="/path/to/main.tf",
            description="S3 bucket should have encryption enabled",
            guideline="https://docs.checkov.io/docs/CKV_AWS_1",
            line_range=(10, 20),
        )
        assert violation.check_id == "CKV_AWS_1"
        assert violation.severity == ScanSeverity.HIGH

    def test_violation_to_dict(self):
        """Test converting violation to dictionary."""
        violation = SecurityViolation(
            check_id="CKV_AWS_1",
            check_name="Test check",
            severity=ScanSeverity.MEDIUM,
            resource="resource.test",
            file_path="/test.tf",
            description="Test description",
        )
        result = violation.to_dict()
        assert result["check_id"] == "CKV_AWS_1"
        assert result["severity"] == "medium"
        assert result["guideline"] is None


class TestScanResult:
    """Tests for ScanResult dataclass."""

    def test_create_passed_result(self):
        """Test creating a passed scan result."""
        result = ScanResult(passed=True, passed_checks=10)
        assert result.passed is True
        assert result.total_checks == 10

    def test_create_failed_result(self):
        """Test creating a failed scan result."""
        violation = SecurityViolation(
            check_id="CKV_AWS_1",
            check_name="Test",
            severity=ScanSeverity.HIGH,
            resource="test",
            file_path="/test.tf",
            description="Test",
        )
        result = ScanResult(
            passed=False,
            violations=[violation],
            passed_checks=5,
            failed_checks=1,
        )
        assert result.passed is False
        assert result.total_checks == 6
        assert len(result.violations) == 1

    def test_get_violations_by_severity(self):
        """Test filtering violations by severity."""
        violations = [
            SecurityViolation(
                check_id="CKV_1",
                check_name="Test1",
                severity=ScanSeverity.HIGH,
                resource="r1",
                file_path="/t1.tf",
                description="D1",
            ),
            SecurityViolation(
                check_id="CKV_2",
                check_name="Test2",
                severity=ScanSeverity.LOW,
                resource="r2",
                file_path="/t2.tf",
                description="D2",
            ),
            SecurityViolation(
                check_id="CKV_3",
                check_name="Test3",
                severity=ScanSeverity.HIGH,
                resource="r3",
                file_path="/t3.tf",
                description="D3",
            ),
        ]
        result = ScanResult(passed=False, violations=violations)
        high_violations = result.get_violations_by_severity(ScanSeverity.HIGH)
        assert len(high_violations) == 2

    def test_result_to_dict(self):
        """Test converting result to dictionary."""
        result = ScanResult(
            passed=True,
            passed_checks=10,
            failed_checks=0,
            skipped_checks=2,
            scan_duration_seconds=5.5,
            scanner_version="2.0.0",
        )
        d = result.to_dict()
        assert d["passed"] is True
        assert d["total_checks"] == 12
        assert d["scan_duration_seconds"] == 5.5


class TestSecurityScanner:
    """Tests for SecurityScanner class."""

    def test_init_defaults(self):
        """Test scanner initialization with defaults."""
        scanner = SecurityScanner()
        assert scanner.severity_threshold == ScanSeverity.HIGH
        assert scanner.skip_checks == []
        assert scanner.frameworks == ["terraform", "ansible"]

    def test_init_custom(self):
        """Test scanner initialization with custom options."""
        scanner = SecurityScanner(
            severity_threshold=ScanSeverity.MEDIUM,
            skip_checks=["CKV_AWS_1", "CKV_AWS_2"],
            frameworks=["terraform"],
        )
        assert scanner.severity_threshold == ScanSeverity.MEDIUM
        assert scanner.skip_checks == ["CKV_AWS_1", "CKV_AWS_2"]
        assert scanner.frameworks == ["terraform"]

    def test_is_available_when_checkov_installed(self):
        """Test is_available returns True when checkov is found."""
        scanner = SecurityScanner()
        with patch("shutil.which", return_value="/usr/bin/checkov"):
            assert scanner.is_available() is True

    def test_is_available_when_checkov_not_installed(self):
        """Test is_available returns False when checkov is not found."""
        scanner = SecurityScanner()
        with patch("shutil.which", return_value=None):
            assert scanner.is_available() is False

    def test_checkov_path_raises_when_not_found(self):
        """Test checkov_path raises FileNotFoundError when not found."""
        scanner = SecurityScanner()
        with patch("shutil.which", return_value=None):
            with pytest.raises(FileNotFoundError) as exc_info:
                _ = scanner.checkov_path
            assert "checkov not found" in str(exc_info.value)

    def test_get_version_success(self):
        """Test getting checkov version."""
        scanner = SecurityScanner()
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "2.3.0"

        with (
            patch("shutil.which", return_value="/usr/bin/checkov"),
            patch("subprocess.run", return_value=mock_result),
        ):
            version = scanner.get_version()
            assert version == "2.3.0"

    def test_get_version_failure(self):
        """Test getting version when checkov not available."""
        scanner = SecurityScanner()
        with patch("shutil.which", return_value=None):
            version = scanner.get_version()
            assert version is None

    def test_scan_directory_not_found(self):
        """Test scanning a non-existent directory."""
        scanner = SecurityScanner()
        result = scanner.scan(Path("/nonexistent/path"))
        assert result.passed is False
        assert "not found" in result.error

    def test_scan_success(self, tmp_path: Path):
        """Test successful scan with no violations."""
        scanner = SecurityScanner()

        # Create test terraform file
        (tmp_path / "main.tf").write_text("resource {}")

        mock_result = MagicMock()
        mock_result.stdout = (
            '{"results": {"passed_checks": [], "failed_checks": [], "skipped_checks": []}}'
        )
        mock_result.stderr = ""

        with (
            patch("shutil.which", return_value="/usr/bin/checkov"),
            patch("subprocess.run", return_value=mock_result),
        ):
            result = scanner.scan(tmp_path)
            assert result.passed is True

    def test_scan_with_violations(self, tmp_path: Path):
        """Test scan that finds violations."""
        scanner = SecurityScanner()

        # Create test terraform file
        (tmp_path / "main.tf").write_text("resource {}")

        checkov_output = {
            "results": {
                "passed_checks": [{"check_id": "CKV_1"}],
                "failed_checks": [
                    {
                        "check_id": "CKV_AWS_2",
                        "check_name": "Test check failed",
                        "check_result": {"severity": "HIGH"},
                        "resource": "aws_s3_bucket.test",
                        "file_path": "/main.tf",
                    }
                ],
                "skipped_checks": [],
            }
        }

        mock_result = MagicMock()
        mock_result.stdout = str(checkov_output).replace("'", '"')
        mock_result.stderr = ""

        with (
            patch("shutil.which", return_value="/usr/bin/checkov"),
            patch("subprocess.run", return_value=mock_result),
        ):
            result = scanner.scan(tmp_path)
            assert result.passed is False
            assert result.failed_checks == 1
            assert result.passed_checks == 1

    def test_scan_timeout(self, tmp_path: Path):
        """Test scan timeout handling."""
        import subprocess

        scanner = SecurityScanner()
        (tmp_path / "main.tf").write_text("resource {}")

        with (
            patch("shutil.which", return_value="/usr/bin/checkov"),
            patch("subprocess.run", side_effect=subprocess.TimeoutExpired("checkov", 10)),
        ):
            result = scanner.scan(tmp_path, timeout=10)
            assert result.passed is False
            assert "timed out" in result.error

    def test_cleanup(self):
        """Test cleanup method."""
        scanner = SecurityScanner()
        # Should not raise
        scanner.cleanup()

    def test_parse_checkov_empty_output(self):
        """Test parsing empty checkov output."""
        scanner = SecurityScanner()
        result = scanner._parse_checkov_output("", "")
        assert result.passed is True

    def test_severity_threshold_filtering(self, tmp_path: Path):
        """Test that violations below threshold don't fail scan."""
        scanner = SecurityScanner(severity_threshold=ScanSeverity.HIGH)

        (tmp_path / "main.tf").write_text("resource {}")

        # Only LOW severity violation
        checkov_output = {
            "results": {
                "passed_checks": [],
                "failed_checks": [
                    {
                        "check_id": "CKV_1",
                        "check_name": "Low severity check",
                        "check_result": {"severity": "LOW"},
                        "resource": "test",
                        "file_path": "/main.tf",
                    }
                ],
                "skipped_checks": [],
            }
        }

        mock_result = MagicMock()
        mock_result.stdout = str(checkov_output).replace("'", '"')
        mock_result.stderr = ""

        with (
            patch("shutil.which", return_value="/usr/bin/checkov"),
            patch("subprocess.run", return_value=mock_result),
        ):
            result = scanner.scan(tmp_path)
            # Should pass because LOW is below HIGH threshold
            assert result.passed is True
            # But violation should still be recorded
            assert len(result.violations) == 1
