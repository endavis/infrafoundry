"""Unit tests for Proxmox StorageValidator."""

from unittest.mock import MagicMock

import pytest

from infrafoundry.core.validation import ValidationReport
from infrafoundry.core.validation_helpers import BaseAPIValidator
from infrafoundry.providers.proxmox.validators.storage_validator import StorageValidator


@pytest.fixture
def report():
    """Create a mock validation report."""
    return MagicMock(spec=ValidationReport)


@pytest.fixture
def api_validator():
    """Create a mock API validator."""
    return MagicMock(spec=BaseAPIValidator)


@pytest.fixture
def validator(api_validator, report):
    """Create a StorageValidator instance."""
    return StorageValidator(api_validator, report)


def test_validate_active_storage(validator, api_validator, report):
    """Test validation of active storage."""
    api_validator.fetch_json.return_value = {
        "data": [
            {"storage": "local", "active": 1, "type": "dir"},
        ]
    }

    validator.validate(
        "https://proxmox.example.com/api2/json",
        {"Authorization": "token"},
        {("pve1", "local")},
    )

    report.add_check.assert_called_once()
    call_args = report.add_check.call_args[1]
    assert call_args["passed"] is True
    assert "local" in call_args["message"]
    assert "active" in call_args["message"]


def test_validate_inactive_storage(validator, api_validator, report):
    """Test validation of inactive storage."""
    api_validator.fetch_json.return_value = {
        "data": [
            {"storage": "local", "active": 0, "type": "dir"},
        ]
    }

    validator.validate(
        "https://proxmox.example.com/api2/json",
        {"Authorization": "token"},
        {("pve1", "local")},
    )

    report.add_check.assert_called_once()
    call_args = report.add_check.call_args[1]
    assert call_args["passed"] is False
    assert "inactive" in call_args["message"]


def test_validate_missing_storage(validator, api_validator, report):
    """Test validation of non-existent storage."""
    api_validator.fetch_json.return_value = {
        "data": [
            {"storage": "local", "active": 1, "type": "dir"},
        ]
    }

    validator.validate(
        "https://proxmox.example.com/api2/json",
        {"Authorization": "token"},
        {("pve1", "missing-storage")},
    )

    report.add_check.assert_called_once()
    call_args = report.add_check.call_args[1]
    assert call_args["passed"] is False
    assert "not found" in call_args["message"]


def test_validate_api_fetch_failure(validator, api_validator, report):
    """Test validation when API fetch fails."""
    api_validator.fetch_json.return_value = None

    validator.validate(
        "https://proxmox.example.com/api2/json",
        {"Authorization": "token"},
        {("pve1", "local")},
    )

    report.add_check.assert_not_called()


def test_validate_duplicate_storage_pools(validator, api_validator, report):
    """Test that duplicate storage pools are only checked once."""
    api_validator.fetch_json.return_value = {
        "data": [
            {"storage": "local", "active": 1, "type": "dir"},
        ]
    }

    validator.validate(
        "https://proxmox.example.com/api2/json",
        {"Authorization": "token"},
        {("pve1", "local"), ("pve1", "local")},
    )

    # Should only check once despite duplicate in set
    api_validator.fetch_json.assert_called_once()
    report.add_check.assert_called_once()


def test_validate_multiple_storage_pools(validator, api_validator, report):
    """Test validation of multiple storage pools."""
    api_validator.fetch_json.side_effect = [
        {"data": [{"storage": "local", "active": 1, "type": "dir"}]},
        {"data": [{"storage": "shared", "active": 1, "type": "nfs"}]},
    ]

    validator.validate(
        "https://proxmox.example.com/api2/json",
        {"Authorization": "token"},
        {("pve1", "local"), ("pve2", "shared")},
    )

    assert api_validator.fetch_json.call_count == 2
    assert report.add_check.call_count == 2


def test_validate_empty_storage_pools(validator, api_validator, report):
    """Test validation with empty storage pool set."""
    validator.validate(
        "https://proxmox.example.com/api2/json",
        {"Authorization": "token"},
        set(),
    )

    api_validator.fetch_json.assert_not_called()
    report.add_check.assert_not_called()
