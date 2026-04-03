"""Unit tests for Proxmox NodeValidator."""

from unittest.mock import MagicMock

import pytest

from infrafoundry.core.exceptions import APIError
from infrafoundry.core.validation import ValidationReport
from infrafoundry.providers.proxmox.api_client import ProxmoxClient
from infrafoundry.providers.proxmox.validators.node_validator import NodeValidator


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
    """Create a NodeValidator instance."""
    return NodeValidator(report)


def test_validate_node_online(validator, client, report):
    """Test validation of online node."""
    client.get_json.return_value = {"data": {"uptime": 3600}}

    validator.validate(client, {"pve1"})

    client.get_json.assert_called_once_with("nodes/pve1/status")
    report.add_check.assert_called_once()
    call_args = report.add_check.call_args[1]
    assert call_args["passed"] is True
    assert "pve1" in call_args["message"]
    assert "online" in call_args["message"]


def test_validate_node_not_accessible(validator, client, report):
    """Test validation when node is not accessible."""
    client.get_json.side_effect = APIError("not accessible", provider="proxmox")

    validator.validate(client, {"pve1"})

    report.add_check.assert_called_once()
    call_args = report.add_check.call_args[1]
    assert call_args["passed"] is False
    assert "not accessible" in call_args["message"]


def test_validate_multiple_nodes(validator, client, report):
    """Test validation of multiple nodes."""
    client.get_json.side_effect = [
        {"data": {"uptime": 3600}},
        {"data": {"uptime": 7200}},
    ]

    validator.validate(client, {"pve1", "pve2"})

    assert client.get_json.call_count == 2
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


def test_validate_empty_nodes(validator, client, report):
    """Test validation with empty node set."""
    validator.validate(client, set())

    client.get_json.assert_not_called()
    report.add_check.assert_not_called()
