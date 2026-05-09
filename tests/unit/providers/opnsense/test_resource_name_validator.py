"""Unit tests for OPNsense ResourceNameValidator."""

from unittest.mock import MagicMock

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.opnsense.validators.resource_name_validator import (
    ResourceNameValidator,
)


@pytest.fixture
def report():
    """Create a mock validation report."""
    return MagicMock(spec=ValidationReport)


@pytest.fixture
def validator(report):
    """Create a ResourceNameValidator instance."""
    return ResourceNameValidator(report)


def test_validate_unique_names(validator, report):
    """Test validation with all unique names."""
    resources = [
        ResourceConfig(name="alias1", type="firewall.aliases", provider="opnsense", config={}),
        ResourceConfig(name="alias2", type="firewall.aliases", provider="opnsense", config={}),
        ResourceConfig(name="vlan1", type="interfaces.vlans", provider="opnsense", config={}),
    ]

    validator.validate(resources)

    report.add_check.assert_not_called()


def test_validate_duplicate_names_same_type(validator, report):
    """Test validation with duplicate names in same type."""
    resources = [
        ResourceConfig(name="web_servers", type="firewall.aliases", provider="opnsense", config={}),
        ResourceConfig(name="db_servers", type="firewall.aliases", provider="opnsense", config={}),
        ResourceConfig(name="web_servers", type="firewall.aliases", provider="opnsense", config={}),
    ]

    validator.validate(resources)

    report.add_check.assert_called_once()
    call_args = report.add_check.call_args[1]
    assert call_args["passed"] is False
    assert "Duplicate" in call_args["message"]
    assert "web_servers" in call_args["message"]
    assert call_args["level"] == ValidationLevel.ERROR


def test_validate_same_name_different_types(validator, report):
    """Test validation with same name across different types (allowed)."""
    resources = [
        ResourceConfig(name="web", type="firewall.aliases", provider="opnsense", config={}),
        ResourceConfig(name="web", type="interfaces.vlans", provider="opnsense", config={}),
        ResourceConfig(name="web", type="firewall.rules", provider="opnsense", config={}),
    ]

    validator.validate(resources)

    # Same names across types are allowed
    report.add_check.assert_not_called()


def test_validate_multiple_duplicates_same_type(validator, report):
    """Test validation with multiple duplicate names in same type."""
    resources = [
        ResourceConfig(name="alias1", type="firewall.aliases", provider="opnsense", config={}),
        ResourceConfig(name="alias1", type="firewall.aliases", provider="opnsense", config={}),
        ResourceConfig(name="alias1", type="firewall.aliases", provider="opnsense", config={}),
    ]

    validator.validate(resources)

    # Should report duplicate twice (second and third occurrences)
    assert report.add_check.call_count == 2


def test_validate_duplicates_in_multiple_types(validator, report):
    """Test validation with duplicates in multiple types."""
    resources = [
        ResourceConfig(name="dup1", type="firewall.aliases", provider="opnsense", config={}),
        ResourceConfig(name="dup1", type="firewall.aliases", provider="opnsense", config={}),
        ResourceConfig(name="dup2", type="interfaces.vlans", provider="opnsense", config={}),
        ResourceConfig(name="dup2", type="interfaces.vlans", provider="opnsense", config={}),
    ]

    validator.validate(resources)

    assert report.add_check.call_count == 2


def test_validate_empty_resources(validator, report):
    """Test validation with no resources."""
    validator.validate([])

    report.add_check.assert_not_called()


def test_validate_single_resource(validator, report):
    """Test validation with single resource."""
    resources = [
        ResourceConfig(name="alias1", type="firewall.aliases", provider="opnsense", config={}),
    ]

    validator.validate(resources)

    report.add_check.assert_not_called()


def test_validate_many_unique_resources(validator, report):
    """Test validation with many unique resources."""
    resources = [
        ResourceConfig(name=f"alias{i}", type="firewall.aliases", provider="opnsense", config={})
        for i in range(100)
    ]

    validator.validate(resources)

    report.add_check.assert_not_called()


def test_validate_check_name_format(validator, report):
    """Test that check name includes resource type and name."""
    resources = [
        ResourceConfig(name="duplicate", type="firewall.aliases", provider="opnsense", config={}),
        ResourceConfig(name="duplicate", type="firewall.aliases", provider="opnsense", config={}),
    ]

    validator.validate(resources)

    call_args = report.add_check.call_args[1]
    assert "firewall.aliases" in call_args["check_name"]
    assert "duplicate" in call_args["check_name"]


def test_validate_case_sensitive_names(validator, report):
    """Test that name comparison is case-sensitive."""
    resources = [
        ResourceConfig(name="WebServers", type="firewall.aliases", provider="opnsense", config={}),
        ResourceConfig(name="webservers", type="firewall.aliases", provider="opnsense", config={}),
        ResourceConfig(name="WEBSERVERS", type="firewall.aliases", provider="opnsense", config={}),
    ]

    validator.validate(resources)

    # Names are case-sensitive, so no duplicates
    report.add_check.assert_not_called()
