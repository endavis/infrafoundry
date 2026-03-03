"""Unit tests for ESXi HostConnectivityValidator."""

from unittest.mock import MagicMock, patch

import pytest

from infrafoundry.core.validation import ValidationReport
from infrafoundry.providers.esxi.validators.host_connectivity_validator import (
    HostConnectivityValidator,
)


@pytest.fixture
def report():
    """Create a mock validation report."""
    return MagicMock(spec=ValidationReport)


@pytest.fixture
def validator(report):
    """Create a HostConnectivityValidator instance."""
    return HostConnectivityValidator(report, timeout=1.0)


def test_validate_host_reachable(validator, report):
    """Test validation of reachable host."""
    mock_conn = MagicMock()
    with patch("socket.create_connection", return_value=mock_conn):
        validator.validate("esxi-host-01")

    report.add_check.assert_called_once()
    call_args = report.add_check.call_args[1]
    assert call_args["passed"] is True
    assert "reachable" in call_args["message"]
    assert "esxi-host-01" in call_args["message"]
    mock_conn.close.assert_called_once()


def test_validate_host_unreachable(validator, report):
    """Test validation of unreachable host."""
    with patch("socket.create_connection", side_effect=OSError("Connection refused")):
        validator.validate("esxi-host-01")

    report.add_check.assert_called_once()
    call_args = report.add_check.call_args[1]
    assert call_args["passed"] is False
    assert "not reachable" in call_args["message"]
    assert "esxi-host-01" in call_args["message"]


def test_validate_custom_port(validator, report):
    """Test validation with custom port."""
    mock_conn = MagicMock()
    with patch("socket.create_connection", return_value=mock_conn) as mock_create:
        validator.validate("esxi-host-01", port=443)

    mock_create.assert_called_once_with(("esxi-host-01", 443), timeout=1.0)
    call_args = report.add_check.call_args[1]
    assert "port 443" in call_args["message"]


def test_validate_timeout_error(validator, report):
    """Test validation when connection times out."""
    with patch("socket.create_connection", side_effect=OSError("Connection timed out")):
        validator.validate("esxi-host-01")

    call_args = report.add_check.call_args[1]
    assert call_args["passed"] is False
    assert "timed out" in call_args["message"]


def test_validate_check_name_includes_hostname(validator, report):
    """Test that check name includes the hostname."""
    mock_conn = MagicMock()
    with patch("socket.create_connection", return_value=mock_conn):
        validator.validate("esxi-01")

    call_args = report.add_check.call_args[1]
    assert call_args["check_name"] == "esxi_host_connectivity_esxi-01"
