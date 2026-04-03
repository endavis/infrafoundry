"""Unit tests for Proxmox StorageValidator."""

from unittest.mock import MagicMock

import pytest

from infrafoundry.core.exceptions import APIError
from infrafoundry.core.validation import ValidationReport
from infrafoundry.providers.proxmox.api_client import ProxmoxClient
from infrafoundry.providers.proxmox.validators.storage_validator import StorageValidator


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
    """Create a StorageValidator instance."""
    return StorageValidator(report)


def test_validate_active_storage(validator, client, report):
    """Test validation of active storage."""
    client.get_json.return_value = {
        "data": [
            {"storage": "local", "active": 1, "type": "dir"},
        ]
    }

    validator.validate(client, {("pve1", "local")})

    report.add_check.assert_called_once()
    call_args = report.add_check.call_args[1]
    assert call_args["passed"] is True
    assert "local" in call_args["message"]
    assert "active" in call_args["message"]


def test_validate_inactive_storage(validator, client, report):
    """Test validation of inactive storage."""
    client.get_json.return_value = {
        "data": [
            {"storage": "local", "active": 0, "type": "dir"},
        ]
    }

    validator.validate(client, {("pve1", "local")})

    report.add_check.assert_called_once()
    call_args = report.add_check.call_args[1]
    assert call_args["passed"] is False
    assert "inactive" in call_args["message"]


def test_validate_missing_storage(validator, client, report):
    """Test validation of non-existent storage."""
    client.get_json.return_value = {
        "data": [
            {"storage": "local", "active": 1, "type": "dir"},
        ]
    }

    validator.validate(client, {("pve1", "missing-storage")})

    report.add_check.assert_called_once()
    call_args = report.add_check.call_args[1]
    assert call_args["passed"] is False
    assert "not found" in call_args["message"]


def test_validate_api_fetch_failure(validator, client, report):
    """Test validation when API fetch fails."""
    client.get_json.side_effect = APIError("failed", provider="proxmox")

    validator.validate(client, {("pve1", "local")})

    report.add_check.assert_called_once()
    call_args = report.add_check.call_args[1]
    assert call_args["passed"] is False
    assert "not accessible" in call_args["message"]


def test_validate_duplicate_storage_pools(validator, client, report):
    """Test that duplicate storage pools are only checked once."""
    client.get_json.return_value = {
        "data": [
            {"storage": "local", "active": 1, "type": "dir"},
        ]
    }

    validator.validate(client, {("pve1", "local"), ("pve1", "local")})

    # Should only check once despite duplicate in set
    client.get_json.assert_called_once()
    report.add_check.assert_called_once()


def test_validate_multiple_storage_pools(validator, client, report):
    """Test validation of multiple storage pools."""
    client.get_json.side_effect = [
        {"data": [{"storage": "local", "active": 1, "type": "dir"}]},
        {"data": [{"storage": "shared", "active": 1, "type": "nfs"}]},
    ]

    validator.validate(client, {("pve1", "local"), ("pve2", "shared")})

    assert client.get_json.call_count == 2
    assert report.add_check.call_count == 2


def test_validate_empty_storage_pools(validator, client, report):
    """Test validation with empty storage pool set."""
    validator.validate(client, set())

    client.get_json.assert_not_called()
    report.add_check.assert_not_called()
