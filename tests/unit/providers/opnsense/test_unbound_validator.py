"""Unit tests for OPNsense UnboundValidator."""

from unittest.mock import MagicMock

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.opnsense.validators.unbound_validator import UnboundValidator


@pytest.fixture
def report():
    """Create a mock validation report."""
    return MagicMock(spec=ValidationReport)


@pytest.fixture
def validator(report):
    """Create an UnboundValidator instance."""
    return UnboundValidator(report)


def test_validate_valid_override(validator, report):
    """Test validation of a valid host override with all fields."""
    override = ResourceConfig(
        name="web-server",
        type="unbound_host_override",
        provider="opnsense",
        config={
            "hostname": "web",
            "domain": "example.com",
            "server": "192.168.1.10",
        },
    )

    validator.validate([override])

    # hostname, domain, server = 3 checks
    assert report.add_check.call_count == 3
    for call in report.add_check.call_args_list:
        assert call[1]["passed"] is True


def test_validate_missing_hostname(validator, report):
    """Test validation fails when hostname is missing."""
    override = ResourceConfig(
        name="bad-override",
        type="unbound_host_override",
        provider="opnsense",
        config={
            "domain": "example.com",
        },
    )

    validator.validate([override])

    # Find the hostname check
    hostname_call = None
    for call in report.add_check.call_args_list:
        if "hostname" in call[1]["check_name"] and "hostname" in call[1]["message"]:
            hostname_call = call[1]
            break

    assert hostname_call is not None
    assert hostname_call["passed"] is False
    assert hostname_call["level"] == ValidationLevel.ERROR
    assert "missing" in hostname_call["message"]


def test_validate_missing_domain(validator, report):
    """Test validation fails when domain is missing."""
    override = ResourceConfig(
        name="bad-override",
        type="unbound_host_override",
        provider="opnsense",
        config={
            "hostname": "web",
        },
    )

    validator.validate([override])

    # Find the domain check
    domain_call = None
    for call in report.add_check.call_args_list:
        if "domain" in call[1]["check_name"]:
            domain_call = call[1]
            break

    assert domain_call is not None
    assert domain_call["passed"] is False
    assert domain_call["level"] == ValidationLevel.ERROR
    assert "missing" in domain_call["message"]


def test_validate_empty_hostname(validator, report):
    """Test validation fails when hostname is empty string."""
    override = ResourceConfig(
        name="bad-override",
        type="unbound_host_override",
        provider="opnsense",
        config={
            "hostname": "",
            "domain": "example.com",
        },
    )

    validator.validate([override])

    hostname_call = None
    for call in report.add_check.call_args_list:
        if "hostname" in call[1]["check_name"] and "hostname" in call[1]["message"]:
            hostname_call = call[1]
            break

    assert hostname_call is not None
    assert hostname_call["passed"] is False


def test_validate_invalid_server_ip(validator, report):
    """Test validation fails when server is not a valid IP address."""
    override = ResourceConfig(
        name="bad-ip",
        type="unbound_host_override",
        provider="opnsense",
        config={
            "hostname": "web",
            "domain": "example.com",
            "server": "not-an-ip",
        },
    )

    validator.validate([override])

    server_call = None
    for call in report.add_check.call_args_list:
        if "server" in call[1]["check_name"]:
            server_call = call[1]
            break

    assert server_call is not None
    assert server_call["passed"] is False
    assert server_call["level"] == ValidationLevel.ERROR
    assert "invalid" in server_call["message"]


def test_validate_valid_ipv6_server(validator, report):
    """Test validation passes with valid IPv6 server address."""
    override = ResourceConfig(
        name="ipv6-override",
        type="unbound_host_override",
        provider="opnsense",
        config={
            "hostname": "web",
            "domain": "example.com",
            "server": "2001:db8::1",
        },
    )

    validator.validate([override])

    server_call = None
    for call in report.add_check.call_args_list:
        if "server" in call[1]["check_name"]:
            server_call = call[1]
            break

    assert server_call is not None
    assert server_call["passed"] is True


def test_validate_no_server_field(validator, report):
    """Test validation passes when server field is not provided (optional)."""
    override = ResourceConfig(
        name="no-server",
        type="unbound_host_override",
        provider="opnsense",
        config={
            "hostname": "web",
            "domain": "example.com",
        },
    )

    validator.validate([override])

    # Only hostname and domain checks (no server check)
    assert report.add_check.call_count == 2
    for call in report.add_check.call_args_list:
        assert call[1]["passed"] is True


def test_validate_empty_resources(validator, report):
    """Test validation with no resources produces no checks."""
    validator.validate([])

    report.add_check.assert_not_called()


def test_validate_multiple_resources(validator, report):
    """Test validation of multiple resources."""
    overrides = [
        ResourceConfig(
            name="web",
            type="unbound_host_override",
            provider="opnsense",
            config={
                "hostname": "web",
                "domain": "example.com",
                "server": "192.168.1.10",
            },
        ),
        ResourceConfig(
            name="mail",
            type="unbound_host_override",
            provider="opnsense",
            config={
                "hostname": "mail",
                "domain": "example.com",
                "server": "192.168.1.20",
            },
        ),
    ]

    validator.validate(overrides)

    # 3 checks per resource (hostname, domain, server) * 2 resources = 6
    assert report.add_check.call_count == 6


def test_validate_mixed_valid_and_invalid(validator, report):
    """Test validation with mixed valid and invalid resources."""
    overrides = [
        ResourceConfig(
            name="good",
            type="unbound_host_override",
            provider="opnsense",
            config={
                "hostname": "web",
                "domain": "example.com",
                "server": "192.168.1.10",
            },
        ),
        ResourceConfig(
            name="bad",
            type="unbound_host_override",
            provider="opnsense",
            config={
                "hostname": "",
                "domain": "",
                "server": "not-valid",
            },
        ),
    ]

    validator.validate(overrides)

    # First resource: 3 passes. Second resource: 3 failures.
    assert report.add_check.call_count == 6

    passed_calls = [c for c in report.add_check.call_args_list if c[1]["passed"] is True]
    failed_calls = [c for c in report.add_check.call_args_list if c[1]["passed"] is False]
    assert len(passed_calls) == 3
    assert len(failed_calls) == 3
