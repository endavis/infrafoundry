"""Unit tests for HelmValidator."""

from __future__ import annotations

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.kubernetes.validators.helm_validator import HelmValidator


@pytest.fixture
def validation_report():
    """Create a ValidationReport instance."""
    return ValidationReport()


@pytest.fixture
def validator(validation_report):
    """Create a HelmValidator instance."""
    return HelmValidator(validation_report)


@pytest.mark.unit
class TestHelmValidator:
    """Tests for HelmValidator."""

    def test_valid_release(self, validator, validation_report):
        """Test that a valid helm release with chart and repository succeeds."""
        releases = [
            ResourceConfig(
                provider="kubernetes",
                type="helm_releases",
                name="nginx",
                config={
                    "chart": "nginx",
                    "repository": "https://charts.bitnami.com/bitnami",
                },
            ),
        ]
        validator.validate(releases)
        assert any(r.passed and "nginx" in r.message for r in validation_report.results)
        assert not validation_report.has_errors()

    def test_missing_chart(self, validator, validation_report):
        """Test that missing chart field produces ERROR."""
        releases = [
            ResourceConfig(
                provider="kubernetes",
                type="helm_releases",
                name="bad-release",
                config={"repository": "https://charts.example.com"},
            ),
        ]
        validator.validate(releases)
        assert any(
            not r.passed and r.level == ValidationLevel.ERROR and "chart" in r.message
            for r in validation_report.results
        )

    def test_missing_repository(self, validator, validation_report):
        """Test that missing repository field produces ERROR."""
        releases = [
            ResourceConfig(
                provider="kubernetes",
                type="helm_releases",
                name="bad-release",
                config={"chart": "my-chart"},
            ),
        ]
        validator.validate(releases)
        assert any(
            not r.passed and r.level == ValidationLevel.ERROR and "repository" in r.message
            for r in validation_report.results
        )

    def test_missing_both(self, validator, validation_report):
        """Test that missing both chart and repository produce two ERRORs."""
        releases = [
            ResourceConfig(
                provider="kubernetes",
                type="helm_releases",
                name="empty-release",
                config={},
            ),
        ]
        validator.validate(releases)
        errors = [r for r in validation_report.results if not r.passed]
        assert len(errors) == 2

    def test_empty_releases(self, validator, validation_report):
        """Test that empty releases list produces no checks."""
        validator.validate([])
        assert len(validation_report.results) == 0
