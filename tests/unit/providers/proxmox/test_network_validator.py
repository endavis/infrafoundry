"""Unit tests for Proxmox NetworkValidator."""

from unittest.mock import MagicMock

import pytest

from infrafoundry.core.exceptions import APIError
from infrafoundry.core.validation import ValidationReport
from infrafoundry.providers.proxmox.api_client import ProxmoxClient
from infrafoundry.providers.proxmox.validators.network_validator import NetworkValidator


@pytest.fixture
def report():
    """Create a mock validation report."""
    return MagicMock(spec=ValidationReport)


@pytest.fixture
def client():
    """Create a mock Proxmox API client."""
    return MagicMock(spec=ProxmoxClient)


@pytest.fixture
def validator(report):
    """Create a NetworkValidator instance."""
    return NetworkValidator(report)


def test_validate_bridge_exists(validator, client, report):
    """Test validation of existing bridge."""
    client.get_json.return_value = {
        "data": [
            {"type": "bridge", "iface": "vmbr0"},
        ]
    }

    validator.validate(client, {("pve1", "vmbr0")})

    report.add_check.assert_called_once()
    call_args = report.add_check.call_args[1]
    assert call_args["passed"] is True
    assert "vmbr0" in call_args["message"]
    assert "exists" in call_args["message"]


def test_validate_bridge_not_found(validator, client, report):
    """Test validation of non-existent bridge."""
    client.get_json.return_value = {
        "data": [
            {"type": "bridge", "iface": "vmbr0"},
        ]
    }

    validator.validate(client, {("pve1", "vmbr1")})

    report.add_check.assert_called_once()
    call_args = report.add_check.call_args[1]
    assert call_args["passed"] is False
    assert "not found" in call_args["message"]
    assert "vmbr0" in str(call_args["message"])  # Shows available bridges


def test_validate_non_bridge_interfaces_ignored(validator, client, report):
    """Test that non-bridge interfaces are ignored."""
    client.get_json.return_value = {
        "data": [
            {"type": "eth", "iface": "eth0"},
            {"type": "bridge", "iface": "vmbr0"},
        ]
    }

    validator.validate(client, {("pve1", "vmbr0")})

    # Should find vmbr0 (bridge type)
    call_args = report.add_check.call_args[1]
    assert call_args["passed"] is True


def test_validate_api_fetch_failure(validator, client, report):
    """Test validation when API fetch fails."""
    client.get_json.side_effect = APIError("failed", provider="proxmox")

    validator.validate(client, {("pve1", "vmbr0")})

    report.add_check.assert_called_once()
    call_args = report.add_check.call_args[1]
    assert call_args["passed"] is False
    assert "not accessible" in call_args["message"]


def test_validate_duplicate_bridges(validator, client, report):
    """Test that duplicate bridges are only checked once."""
    client.get_json.return_value = {
        "data": [
            {"type": "bridge", "iface": "vmbr0"},
        ]
    }

    validator.validate(client, {("pve1", "vmbr0"), ("pve1", "vmbr0")})

    # Should only check once despite duplicate in set
    client.get_json.assert_called_once()
    report.add_check.assert_called_once()


def test_validate_multiple_bridges(validator, client, report):
    """Test validation of multiple bridges."""
    client.get_json.side_effect = [
        {"data": [{"type": "bridge", "iface": "vmbr0"}]},
        {"data": [{"type": "bridge", "iface": "vmbr1"}]},
    ]

    validator.validate(client, {("pve1", "vmbr0"), ("pve2", "vmbr1")})

    assert client.get_json.call_count == 2
    assert report.add_check.call_count == 2


def test_validate_empty_bridges(validator, client, report):
    """Test validation with empty bridge set."""
    validator.validate(client, set())

    client.get_json.assert_not_called()
    report.add_check.assert_not_called()
