"""Unit tests for ESXi VswitchReferenceValidator."""

from unittest.mock import MagicMock

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationReport
from infrafoundry.providers.esxi.validators.vswitch_reference_validator import (
    VswitchReferenceValidator,
)


@pytest.fixture
def report():
    """Create a mock validation report."""
    return MagicMock(spec=ValidationReport)


@pytest.fixture
def validator(report):
    """Create a VswitchReferenceValidator instance."""
    return VswitchReferenceValidator(report)


def _make_vswitch(name: str, host: str = "esxi-01") -> ResourceConfig:
    """Create a vswitch resource."""
    return ResourceConfig(name=name, type="vswitch", provider="esxi", config={"host": host})


def _make_portgroup(name: str, vswitch: str, host: str = "esxi-01") -> ResourceConfig:
    """Create a portgroup resource."""
    return ResourceConfig(
        name=name,
        type="portgroup",
        provider="esxi",
        config={"host": host, "vswitch": vswitch},
    )


def test_valid_reference(validator, report):
    """Test portgroup referencing existing vswitch on same host."""
    resources = [
        _make_vswitch("vSwitch1", "esxi-01"),
        _make_portgroup("pg-mgmt", "vSwitch1", "esxi-01"),
    ]
    validator.validate(resources)

    report.add_check.assert_called_once()
    call_args = report.add_check.call_args[1]
    assert call_args["passed"] is True
    assert "vSwitch1" in call_args["message"]


def test_invalid_reference_wrong_host(validator, report):
    """Test portgroup referencing vswitch on different host."""
    resources = [
        _make_vswitch("vSwitch1", "esxi-01"),
        _make_portgroup("pg-mgmt", "vSwitch1", "esxi-02"),
    ]
    validator.validate(resources)

    report.add_check.assert_called_once()
    call_args = report.add_check.call_args[1]
    assert call_args["passed"] is False
    assert "does not exist" in call_args["message"]


def test_invalid_reference_missing_vswitch(validator, report):
    """Test portgroup referencing non-existent vswitch."""
    resources = [
        _make_portgroup("pg-mgmt", "vSwitch99", "esxi-01"),
    ]
    validator.validate(resources)

    call_args = report.add_check.call_args[1]
    assert call_args["passed"] is False
    assert "vSwitch99" in call_args["message"]


def test_no_vswitch_reference(validator, report):
    """Test portgroup with empty vswitch reference."""
    resources = [
        ResourceConfig(
            name="pg-bad",
            type="portgroup",
            provider="esxi",
            config={"host": "esxi-01", "vswitch": ""},
        ),
    ]
    validator.validate(resources)

    call_args = report.add_check.call_args[1]
    assert call_args["passed"] is False
    assert "no vswitch reference" in call_args["message"]


def test_multiple_portgroups(validator, report):
    """Test multiple portgroups with mixed valid/invalid refs."""
    resources = [
        _make_vswitch("vSwitch1", "esxi-01"),
        _make_portgroup("pg-valid", "vSwitch1", "esxi-01"),
        _make_portgroup("pg-invalid", "vSwitch99", "esxi-01"),
    ]
    validator.validate(resources)

    assert report.add_check.call_count == 2
    calls = [c[1] for c in report.add_check.call_args_list]
    passed_values = [c["passed"] for c in calls]
    assert True in passed_values
    assert False in passed_values


def test_no_portgroups(validator, report):
    """Test with no portgroup resources."""
    resources = [
        _make_vswitch("vSwitch1", "esxi-01"),
    ]
    validator.validate(resources)
    report.add_check.assert_not_called()


def test_no_resources(validator, report):
    """Test with empty resource list."""
    validator.validate([])
    report.add_check.assert_not_called()
