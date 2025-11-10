"""Tests for validation framework."""

import pytest

from infrafoundry.core.validation import (
    ValidationLevel,
    ValidationReport,
    ValidationResult,
)


class TestValidationResult:
    """Tests for ValidationResult."""

    def test_create_result(self):
        """Test creating a validation result."""
        result = ValidationResult(
            check_name="test_check",
            level=ValidationLevel.ERROR,
            passed=False,
            message="Test failed",
        )

        assert result.check_name == "test_check"
        assert result.level == ValidationLevel.ERROR
        assert not result.passed
        assert result.message == "Test failed"
        assert result.details is None

    def test_result_with_details(self):
        """Test validation result with details."""
        result = ValidationResult(
            check_name="test_check",
            level=ValidationLevel.WARNING,
            passed=False,
            message="Warning message",
            details={"key": "value", "count": 42},
        )

        assert result.details == {"key": "value", "count": 42}

    def test_result_repr(self):
        """Test string representation of result."""
        result = ValidationResult(
            check_name="connectivity",
            level=ValidationLevel.ERROR,
            passed=False,
            message="Connection failed",
        )

        repr_str = repr(result)
        assert "[ERROR]" in repr_str
        assert "✗" in repr_str
        assert "connectivity" in repr_str
        assert "Connection failed" in repr_str


class TestValidationReport:
    """Tests for ValidationReport."""

    def test_empty_report(self):
        """Test creating an empty report."""
        report = ValidationReport()

        assert len(report.results) == 0
        assert not report.has_errors()
        assert not report.has_warnings()

    def test_add_result(self):
        """Test adding results to report."""
        report = ValidationReport()

        result = ValidationResult(
            check_name="test",
            level=ValidationLevel.INFO,
            passed=True,
            message="Test passed",
        )
        report.add(result)

        assert len(report.results) == 1
        assert report.results[0] == result

    def test_add_check(self):
        """Test adding check via convenience method."""
        report = ValidationReport()

        report.add_check(
            check_name="api_connectivity",
            passed=True,
            message="Connected successfully",
            level=ValidationLevel.INFO,
        )

        assert len(report.results) == 1
        assert report.results[0].check_name == "api_connectivity"
        assert report.results[0].passed
        assert report.results[0].level == ValidationLevel.INFO

    def test_has_errors(self):
        """Test error detection."""
        report = ValidationReport()

        # Add passing check - no errors
        report.add_check(
            check_name="test1",
            passed=True,
            message="OK",
            level=ValidationLevel.INFO,
        )
        assert not report.has_errors()

        # Add error - should detect
        report.add_check(
            check_name="test2",
            passed=False,
            message="Failed",
            level=ValidationLevel.ERROR,
        )
        assert report.has_errors()

    def test_has_warnings(self):
        """Test warning detection."""
        report = ValidationReport()

        # No warnings initially
        assert not report.has_warnings()

        # Add warning
        report.add_check(
            check_name="test",
            passed=False,
            message="Warning",
            level=ValidationLevel.WARNING,
        )
        assert report.has_warnings()
        assert not report.has_errors()  # Warning, not error

    def test_get_summary(self):
        """Test getting summary counts."""
        report = ValidationReport()

        report.add_check("test1", True, "OK", ValidationLevel.INFO)
        report.add_check("test2", False, "Error", ValidationLevel.ERROR)
        report.add_check("test3", False, "Warning", ValidationLevel.WARNING)
        report.add_check("test4", True, "OK", ValidationLevel.INFO)

        summary = report.get_summary()

        assert summary["total"] == 4
        assert summary["passed"] == 2
        assert summary["errors"] == 1
        assert summary["warnings"] == 1
        assert summary["info"] == 0  # Info checks that failed

    def test_report_repr(self):
        """Test string representation of report."""
        report = ValidationReport()

        report.add_check("test1", True, "OK")
        report.add_check("test2", False, "Failed", ValidationLevel.ERROR)

        repr_str = repr(report)

        assert "Validation Report" in repr_str
        assert "Total checks: 2" in repr_str
        assert "Passed: 1" in repr_str
        assert "Errors: 1" in repr_str
