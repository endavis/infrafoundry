"""Unit tests for Proxmox NodeValidator."""

from unittest.mock import MagicMock

import pytest

from infrafoundry.core.validation import ValidationReport
from infrafoundry.core.validation_helpers import BaseAPIValidator
from infrafoundry.providers.proxmox.validators.node_validator import NodeValidator


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
    """Create a NodeValidator instance."""
    return NodeValidator(api_validator, report)


def test_validate_node_online(validator, api_validator, report):
    """Test validation of online node."""
    api_validator.fetch_json.return_value = {"data": {"uptime": 3600}}

    validator.validate(
        "https://proxmox.example.com/api2/json", {"Authorization": "token"}, {"pve1"}
    )

    api_validator.fetch_json.assert_called_once_with(
        url="https://proxmox.example.com/api2/json/nodes/pve1/status",
        headers={"Authorization": "token"},
        verify_ssl=False,
        timeout=10,
        check_name="proxmox_node_pve1",
        error_message="Node 'pve1' not accessible (status {status})",
    )
    report.add_check.assert_called_once()
    call_args = report.add_check.call_args[1]
    assert call_args["passed"] is True
    assert "pve1" in call_args["message"]
    assert "online" in call_args["message"]


def test_validate_node_not_accessible(validator, api_validator, report):
    """Test validation when node is not accessible."""
    api_validator.fetch_json.return_value = None

    validator.validate(
        "https://proxmox.example.com/api2/json", {"Authorization": "token"}, {"pve1"}
    )

    report.add_check.assert_not_called()


def test_validate_multiple_nodes(validator, api_validator, report):
    """Test validation of multiple nodes."""
    api_validator.fetch_json.side_effect = [
        {"data": {"uptime": 3600}},
        {"data": {"uptime": 7200}},
    ]

    validator.validate(
        "https://proxmox.example.com/api2/json", {"Authorization": "token"}, {"pve1", "pve2"}
    )

    assert api_validator.fetch_json.call_count == 2
    assert report.add_check.call_count == 2


def test_format_uptime_seconds(validator):
    """Test uptime formatting for seconds."""
    assert validator._format_uptime(30) == "30 seconds"


def test_format_uptime_minutes(validator):
    """Test uptime formatting for minutes."""
    assert validator._format_uptime(300) == "5 minutes"


def test_format_uptime_hours(validator):
    """Test uptime formatting for hours."""
    assert validator._format_uptime(7200) == "2 hours"
    assert validator._format_uptime(7260) == "2 hours, 1 minutes"


def test_format_uptime_days(validator):
    """Test uptime formatting for days."""
    assert validator._format_uptime(86400) == "1 days"
    assert validator._format_uptime(90000) == "1 days, 1 hours"


def test_validate_empty_nodes(validator, api_validator, report):
    """Test validation with empty node set."""
    validator.validate("https://proxmox.example.com/api2/json", {"Authorization": "token"}, set())

    api_validator.fetch_json.assert_not_called()
    report.add_check.assert_not_called()
