"""Unit tests for OPNsense VLANValidator."""

from unittest.mock import MagicMock

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.opnsense.validators.vlan_validator import VLANValidator


@pytest.fixture
def report():
    """Create a mock validation report."""
    return MagicMock(spec=ValidationReport)


@pytest.fixture
def validator(report):
    """Create a VLANValidator instance."""
    return VLANValidator(report)


def test_validate_parent_interface_found(validator, report):
    """Test validation of VLAN with existing parent interface."""
    vlan = ResourceConfig(
        name="vlan100",
        type="vlans",
        provider="opnsense",
        config={"parent": "em0"},
    )

    validator.validate([vlan], {"em0": {"device": "em0"}})

    report.add_check.assert_called_once()
    call_args = report.add_check.call_args[1]
    assert call_args["passed"] is True
    assert "em0" in call_args["message"]
    assert "vlan100" in call_args["message"]


def test_validate_parent_interface_not_found(validator, report):
    """Test validation of VLAN with undefined parent interface."""
    vlan = ResourceConfig(
        name="vlan100",
        type="vlans",
        provider="opnsense",
        config={"parent": "missing_interface"},
    )

    validator.validate([vlan], {})

    report.add_check.assert_called_once()
    call_args = report.add_check.call_args[1]
    assert call_args["passed"] is False
    assert "undefined" in call_args["message"]
    assert "missing_interface" in call_args["message"]
    assert call_args["level"] == ValidationLevel.ERROR


def test_validate_no_parent_interface(validator, report):
    """Test validation of VLAN without parent interface."""
    vlan = ResourceConfig(
        name="vlan100",
        type="vlans",
        provider="opnsense",
        config={},
    )

    validator.validate([vlan], {})

    report.add_check.assert_not_called()


def test_validate_empty_vlans(validator, report):
    """Test validation with no VLANs."""
    validator.validate([], {"em0": {}})

    report.add_check.assert_not_called()


def test_validate_multiple_vlans(validator, report):
    """Test validation of multiple VLANs."""
    vlans = [
        ResourceConfig(
            name="vlan100",
            type="vlans",
            provider="opnsense",
            config={"parent": "em0"},
        ),
        ResourceConfig(
            name="vlan200",
            type="vlans",
            provider="opnsense",
            config={"parent": "em1"},
        ),
    ]

    validator.validate(vlans, {"em0": {}, "em1": {}})

    assert report.add_check.call_count == 2


def test_validate_mixed_results(validator, report):
    """Test validation with mixed success and failure."""
    vlans = [
        ResourceConfig(
            name="vlan100",
            type="vlans",
            provider="opnsense",
            config={"parent": "em0"},
        ),
        ResourceConfig(
            name="vlan200",
            type="vlans",
            provider="opnsense",
            config={"parent": "missing"},
        ),
    ]

    validator.validate(vlans, {"em0": {}})

    assert report.add_check.call_count == 2
    # First should pass, second should fail
    first_call = report.add_check.call_args_list[0][1]
    second_call = report.add_check.call_args_list[1][1]
    assert first_call["passed"] is True
    assert second_call["passed"] is False


def test_validate_vlan_with_empty_config(validator, report):
    """Test validation of VLAN with empty config."""
    vlan = ResourceConfig(
        name="vlan100",
        type="vlans",
        provider="opnsense",
        config={},
    )

    validator.validate([vlan], {"em0": {}})

    report.add_check.assert_not_called()


def test_validate_same_parent_multiple_vlans(validator, report):
    """Test multiple VLANs using the same parent interface."""
    vlans = [
        ResourceConfig(
            name="vlan100",
            type="vlans",
            provider="opnsense",
            config={"parent": "em0"},
        ),
        ResourceConfig(
            name="vlan200",
            type="vlans",
            provider="opnsense",
            config={"parent": "em0"},
        ),
        ResourceConfig(
            name="vlan300",
            type="vlans",
            provider="opnsense",
            config={"parent": "em0"},
        ),
    ]

    validator.validate(vlans, {"em0": {}})

    assert report.add_check.call_count == 3
    # All should pass
    for call in report.add_check.call_args_list:
        assert call[1]["passed"] is True
