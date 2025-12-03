"""Unit tests for OPNsense FirewallValidator."""

from unittest.mock import MagicMock

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationReport
from infrafoundry.providers.opnsense.validators.firewall_validator import FirewallValidator


@pytest.fixture
def report():
    """Create a mock validation report."""
    return MagicMock(spec=ValidationReport)


@pytest.fixture
def validator(report):
    """Create a FirewallValidator instance."""
    return FirewallValidator(report)


def test_validate_source_alias_found_in_config(validator, report):
    """Test validation of firewall rule with source alias in config."""
    rule = ResourceConfig(
        name="allow-web",
        type="firewall_rules",
        provider="opnsense",
        config={"source": {"alias": "web_servers"}, "destination": {}},
    )

    validator.validate([rule], {"web_servers"}, {})

    report.add_check.assert_called_once()
    call_args = report.add_check.call_args[1]
    assert call_args["passed"] is True
    assert "web_servers" in call_args["message"]


def test_validate_source_alias_found_in_existing(validator, report):
    """Test validation of firewall rule with source alias in existing aliases."""
    rule = ResourceConfig(
        name="allow-web",
        type="firewall_rules",
        provider="opnsense",
        config={"source": {"alias": "web_servers"}, "destination": {}},
    )

    validator.validate([rule], set(), {"web_servers": {"name": "web_servers"}})

    report.add_check.assert_called_once()
    call_args = report.add_check.call_args[1]
    assert call_args["passed"] is True


def test_validate_source_alias_not_found(validator, report):
    """Test validation of firewall rule with undefined source alias."""
    rule = ResourceConfig(
        name="allow-web",
        type="firewall_rules",
        provider="opnsense",
        config={"source": {"alias": "missing_alias"}, "destination": {}},
    )

    validator.validate([rule], set(), {})

    report.add_check.assert_called_once()
    call_args = report.add_check.call_args[1]
    assert call_args["passed"] is False
    assert "undefined" in call_args["message"]
    assert "missing_alias" in call_args["message"]


def test_validate_destination_alias_found(validator, report):
    """Test validation of firewall rule with destination alias."""
    rule = ResourceConfig(
        name="allow-db",
        type="firewall_rules",
        provider="opnsense",
        config={"source": {}, "destination": {"alias": "db_servers"}},
    )

    validator.validate([rule], {"db_servers"}, {})

    report.add_check.assert_called_once()
    call_args = report.add_check.call_args[1]
    assert call_args["passed"] is True
    assert "db_servers" in call_args["message"]


def test_validate_destination_alias_not_found(validator, report):
    """Test validation of firewall rule with undefined destination alias."""
    rule = ResourceConfig(
        name="allow-db",
        type="firewall_rules",
        provider="opnsense",
        config={"source": {}, "destination": {"alias": "missing_alias"}},
    )

    validator.validate([rule], set(), {})

    report.add_check.assert_called_once()
    call_args = report.add_check.call_args[1]
    assert call_args["passed"] is False
    assert "undefined" in call_args["message"]
    assert "missing_alias" in call_args["message"]


def test_validate_both_aliases_found(validator, report):
    """Test validation of firewall rule with both source and destination aliases."""
    rule = ResourceConfig(
        name="allow-web-to-db",
        type="firewall_rules",
        provider="opnsense",
        config={"source": {"alias": "web_servers"}, "destination": {"alias": "db_servers"}},
    )

    validator.validate([rule], {"web_servers", "db_servers"}, {})

    assert report.add_check.call_count == 2


def test_validate_no_aliases(validator, report):
    """Test validation of firewall rule without aliases."""
    rule = ResourceConfig(
        name="allow-all",
        type="firewall_rules",
        provider="opnsense",
        config={"source": {}, "destination": {}},
    )

    validator.validate([rule], set(), {})

    report.add_check.assert_not_called()


def test_validate_empty_rules(validator, report):
    """Test validation with no firewall rules."""
    validator.validate([], {"web_servers"}, {})

    report.add_check.assert_not_called()


def test_validate_multiple_rules(validator, report):
    """Test validation of multiple firewall rules."""
    rules = [
        ResourceConfig(
            name="rule1",
            type="firewall_rules",
            provider="opnsense",
            config={"source": {"alias": "web_servers"}, "destination": {}},
        ),
        ResourceConfig(
            name="rule2",
            type="firewall_rules",
            provider="opnsense",
            config={"source": {}, "destination": {"alias": "db_servers"}},
        ),
    ]

    validator.validate(rules, {"web_servers", "db_servers"}, {})

    assert report.add_check.call_count == 2


def test_validate_rule_with_empty_config(validator, report):
    """Test validation of firewall rule with empty config."""
    rule = ResourceConfig(
        name="rule1",
        type="firewall_rules",
        provider="opnsense",
        config={},
    )

    validator.validate([rule], set(), {})

    report.add_check.assert_not_called()
