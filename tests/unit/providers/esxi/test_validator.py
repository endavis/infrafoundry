"""Unit tests for ESXi EsxiValidator (integration of sub-validators)."""

from unittest.mock import MagicMock, patch

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationReport
from infrafoundry.core.validation_helpers import BaseAPIValidator
from infrafoundry.providers.esxi.validator import EsxiValidator


@pytest.fixture
def report():
    """Create a mock validation report."""
    return MagicMock(spec=ValidationReport)


def _make_env_config(hosts: dict | None = None) -> dict:
    """Create an environment config dict."""
    esxi_settings: dict = {}
    if hosts is not None:
        esxi_settings["hosts"] = hosts
    return {"provider_settings": {"esxi": esxi_settings}}


class TestComposition:
    """Tests for validator composition."""

    def test_api_validator_initialized(self, report):
        """BaseAPIValidator is composed during init."""
        env_config = _make_env_config(hosts={"esxi-01": {}})
        validator = EsxiValidator(env_config, report)
        assert isinstance(validator.api_validator, BaseAPIValidator)

    def test_provider_settings_accessible(self, report):
        """Provider settings are accessible via api_validator."""
        env_config = _make_env_config(hosts={"esxi-01": {"hostname": "192.168.1.10"}})
        validator = EsxiValidator(env_config, report)
        assert validator.provider_settings.get("hosts") is not None


class TestValidateConnectivity:
    """Tests for EsxiValidator.validate_connectivity."""

    def test_no_hosts_configured(self, report):
        """Should report error when no hosts are configured."""
        env_config = _make_env_config(hosts={})
        validator = EsxiValidator(env_config, report)
        validator.validate_connectivity()

        report.add_check.assert_called_once()
        call_args = report.add_check.call_args[1]
        assert call_args["passed"] is False
        assert "No ESXi hosts configured" in call_args["message"]

    @patch("socket.create_connection")
    def test_hosts_connectivity_checked(self, mock_conn, report):
        """Should check connectivity for each configured host."""
        mock_conn.return_value = MagicMock()
        env_config = _make_env_config(
            hosts={
                "esxi-01": {"hostname": "192.168.1.10"},
                "esxi-02": {"hostname": "192.168.1.11"},
            }
        )
        validator = EsxiValidator(env_config, report)
        validator.validate_connectivity()

        assert report.add_check.call_count == 2

    @patch("socket.create_connection")
    def test_host_uses_name_as_default_hostname(self, mock_conn, report):
        """Should use host name as hostname if not explicitly set."""
        mock_conn.return_value = MagicMock()
        env_config = _make_env_config(hosts={"esxi-01": {}})
        validator = EsxiValidator(env_config, report)
        validator.validate_connectivity()

        mock_conn.assert_called_once()
        # The hostname passed to create_connection should be "esxi-01"
        actual_hostname = mock_conn.call_args[0][0][0]
        assert actual_hostname == "esxi-01"


class TestValidateReferences:
    """Tests for EsxiValidator.validate_references."""

    def test_validates_vswitch_and_portgroup_refs(self, report):
        """Should validate both vswitch and portgroup references."""
        env_config = _make_env_config(hosts={"esxi-01": {}})
        validator = EsxiValidator(env_config, report)

        resources = [
            ResourceConfig(
                name="vSwitch1",
                type="vswitch",
                provider="esxi",
                config={"host": "esxi-01"},
            ),
            ResourceConfig(
                name="pg-mgmt",
                type="portgroup",
                provider="esxi",
                config={"host": "esxi-01", "vswitch": "vSwitch1"},
            ),
            ResourceConfig(
                name="vm1",
                type="vm",
                provider="esxi",
                config={
                    "host": "esxi-01",
                    "name": "vm1",
                    "network": [{"portgroup": "pg-mgmt"}],
                },
            ),
        ]
        validator.validate_references(resources)

        # Should have checks from both validators
        assert report.add_check.call_count == 2
        calls = [c[1] for c in report.add_check.call_args_list]
        assert all(c["passed"] for c in calls)

    def test_empty_resources(self, report):
        """Should handle empty resource list gracefully."""
        env_config = _make_env_config(hosts={"esxi-01": {}})
        validator = EsxiValidator(env_config, report)
        validator.validate_references([])
        report.add_check.assert_not_called()
