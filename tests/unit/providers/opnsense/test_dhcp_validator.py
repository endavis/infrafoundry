"""Unit tests for OPNsense DHCPValidator."""

from unittest.mock import MagicMock

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.opnsense.validators.dhcp_validator import DHCPValidator


@pytest.fixture
def report():
    """Create a mock validation report."""
    return MagicMock(spec=ValidationReport)


@pytest.fixture
def validator(report):
    """Create a DHCPValidator instance."""
    return DHCPValidator(report)


def test_validate_interface_found_in_vlans(validator, report):
    """Test validation of DHCP map with interface in VLAN config."""
    dhcp_map = ResourceConfig(
        name="server1",
        type="dhcp_static_maps",
        provider="opnsense",
        config={"interface": "vlan100"},
    )

    validator.validate([dhcp_map], {"vlan100"}, {})

    report.add_check.assert_called_once()
    call_args = report.add_check.call_args[1]
    assert call_args["passed"] is True
    assert "vlan100" in call_args["message"]


def test_validate_interface_found_in_existing(validator, report):
    """Test validation of DHCP map with interface in existing interfaces."""
    dhcp_map = ResourceConfig(
        name="server1",
        type="dhcp_static_maps",
        provider="opnsense",
        config={"interface": "lan"},
    )

    validator.validate([dhcp_map], set(), {"lan": {"device": "em0"}})

    report.add_check.assert_called_once()
    call_args = report.add_check.call_args[1]
    assert call_args["passed"] is True


def test_validate_interface_not_found(validator, report):
    """Test validation of DHCP map with undefined interface."""
    dhcp_map = ResourceConfig(
        name="server1",
        type="dhcp_static_maps",
        provider="opnsense",
        config={"interface": "missing_interface"},
    )

    validator.validate([dhcp_map], set(), {})

    report.add_check.assert_called_once()
    call_args = report.add_check.call_args[1]
    assert call_args["passed"] is False
    assert "undefined" in call_args["message"]
    assert "missing_interface" in call_args["message"]
    assert call_args["level"] == ValidationLevel.WARNING


def test_validate_no_interface_specified(validator, report):
    """Test validation of DHCP map without interface."""
    dhcp_map = ResourceConfig(
        name="server1",
        type="dhcp_static_maps",
        provider="opnsense",
        config={},
    )

    validator.validate([dhcp_map], set(), {})

    report.add_check.assert_not_called()


def test_validate_empty_dhcp_maps(validator, report):
    """Test validation with no DHCP maps."""
    validator.validate([], {"vlan100"}, {})

    report.add_check.assert_not_called()


def test_validate_multiple_dhcp_maps(validator, report):
    """Test validation of multiple DHCP maps."""
    dhcp_maps = [
        ResourceConfig(
            name="server1",
            type="dhcp_static_maps",
            provider="opnsense",
            config={"interface": "vlan100"},
        ),
        ResourceConfig(
            name="server2",
            type="dhcp_static_maps",
            provider="opnsense",
            config={"interface": "lan"},
        ),
    ]

    validator.validate(dhcp_maps, {"vlan100"}, {"lan": {}})

    assert report.add_check.call_count == 2


def test_validate_mixed_results(validator, report):
    """Test validation with mixed success and failure."""
    dhcp_maps = [
        ResourceConfig(
            name="server1",
            type="dhcp_static_maps",
            provider="opnsense",
            config={"interface": "vlan100"},
        ),
        ResourceConfig(
            name="server2",
            type="dhcp_static_maps",
            provider="opnsense",
            config={"interface": "missing"},
        ),
    ]

    validator.validate(dhcp_maps, {"vlan100"}, {})

    assert report.add_check.call_count == 2
    # First should pass, second should fail
    first_call = report.add_check.call_args_list[0][1]
    second_call = report.add_check.call_args_list[1][1]
    assert first_call["passed"] is True
    assert second_call["passed"] is False
