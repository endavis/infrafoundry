"""Unit tests for OCI compartment validator."""

from __future__ import annotations

import pytest

from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.oci.validators.compartment_validator import CompartmentValidator


@pytest.fixture
def report():
    """Create a validation report."""
    return ValidationReport()


@pytest.fixture
def validator(report):
    """Create a CompartmentValidator instance."""
    return CompartmentValidator(report)


class TestCompartmentValidator:
    """Tests for CompartmentValidator.validate method."""

    def test_compartment_found(self, validator, report):
        """Compartment found in list produces SUCCESS with name."""
        compartments = [
            {"id": "ocid1.compartment.oc1..aaa", "name": "my-compartment"},
            {"id": "ocid1.compartment.oc1..bbb", "name": "other-compartment"},
        ]

        validator.validate("ocid1.compartment.oc1..aaa", compartments)

        assert len(report.results) == 1
        result = report.results[0]
        assert result.passed is True
        assert "my-compartment" in result.message
        assert "ocid1.compartment.oc1..aaa" in result.message

    def test_compartment_not_found(self, validator, report):
        """Compartment not found produces ERROR with available names."""
        compartments = [
            {"id": "ocid1.compartment.oc1..aaa", "name": "my-compartment"},
            {"id": "ocid1.compartment.oc1..bbb", "name": "other-compartment"},
        ]

        validator.validate("ocid1.compartment.oc1..missing", compartments)

        assert len(report.results) == 1
        result = report.results[0]
        assert result.passed is False
        assert result.level == ValidationLevel.ERROR
        assert "not found" in result.message
        assert "my-compartment" in result.message
        assert "other-compartment" in result.message

    def test_none_compartments_skips(self, validator, report):
        """None compartments (API failure) produces no checks."""
        validator.validate("ocid1.compartment.oc1..aaa", None)

        assert len(report.results) == 0

    def test_empty_compartment_list(self, validator, report):
        """Empty compartment list produces ERROR."""
        validator.validate("ocid1.compartment.oc1..aaa", [])

        assert len(report.results) == 1
        result = report.results[0]
        assert result.passed is False
        assert result.level == ValidationLevel.ERROR
        assert "(none)" in result.message
