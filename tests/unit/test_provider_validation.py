"""Tests for provider validation methods."""

from unittest.mock import Mock, patch

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationReport
from infrafoundry.providers.proxmox import ProxmoxProvider


class TestProxmoxValidation:
    """Tests for Proxmox provider validation."""

    @pytest.fixture
    def proxmox_provider(self, tmp_path):
        """Create a Proxmox provider instance."""
        config_dir = tmp_path / "config"
        output_dir = tmp_path / "output"
        config_dir.mkdir()
        output_dir.mkdir()
        return ProxmoxProvider(config_dir, output_dir)

    @pytest.fixture
    def env_config(self):
        """Sample environment configuration."""
        return {
            "provider_settings": {
                "proxmox": {
                    "api_url": "https://pve01.example.com:8006",
                    "api_token": "PVEAPIToken=root@pam!test=12345678-1234-1234-1234-123456789abc",
                    "node": "pve01",
                }
            }
        }

    def test_validate_connectivity_missing_credentials(self, proxmox_provider):
        """Test validation fails when credentials are missing."""
        report = ValidationReport()
        env_config = {"provider_settings": {"proxmox": {}}}

        proxmox_provider.validate_connectivity(env_config, report)

        assert report.has_errors()
        summary = report.get_summary()
        assert summary["errors"] == 1

    @patch("requests.request")
    @patch("requests.get")
    def test_validate_connectivity_success(
        self, mock_get, mock_request, proxmox_provider, env_config
    ):
        """Test successful API connectivity validation."""
        # Mock successful API responses
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {"version": "7.4"}}

        # Both request (from helper) and get (from version check) return success
        mock_request.return_value = mock_response
        mock_get.return_value = mock_response

        report = ValidationReport()
        proxmox_provider.validate_connectivity(env_config, report)

        assert not report.has_errors()
        summary = report.get_summary()
        assert summary["passed"] >= 1

    @patch("requests.get")
    def test_validate_connectivity_api_error(self, mock_get, proxmox_provider, env_config):
        """Test validation handles API errors."""
        # Mock failed API response
        mock_response = Mock()
        mock_response.status_code = 401
        mock_get.return_value = mock_response

        report = ValidationReport()
        proxmox_provider.validate_connectivity(env_config, report)

        assert report.has_errors()

    @patch("requests.get")
    def test_validate_connectivity_timeout(self, mock_get, proxmox_provider, env_config):
        """Test validation handles connection timeout."""
        import requests

        mock_get.side_effect = requests.exceptions.Timeout()

        report = ValidationReport()
        proxmox_provider.validate_connectivity(env_config, report)

        assert report.has_errors()

    @patch("requests.get")
    def test_validate_connectivity_connection_error(self, mock_get, proxmox_provider, env_config):
        """Test validation handles connection errors."""
        import requests

        mock_get.side_effect = requests.exceptions.ConnectionError("Cannot connect")

        report = ValidationReport()
        proxmox_provider.validate_connectivity(env_config, report)

        assert report.has_errors()

    @patch("requests.get")
    def test_validate_references_template_exists(self, mock_get, proxmox_provider, env_config):
        """Test validation passes when referenced template exists."""
        # Mock API response with templates
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {"name": "ubuntu-22.04", "template": 1},
                {"name": "debian-12", "template": 1},
                {"name": "running-vm", "template": 0},
            ]
        }
        mock_get.return_value = mock_response

        # Create resources that reference templates
        resources = [
            ResourceConfig(
                provider="proxmox",
                type="vm",
                name="web-01",
                config={"template": "ubuntu-22.04", "cores": 2},
            ),
        ]

        report = ValidationReport()
        proxmox_provider.validate_references(resources, env_config, report)

        assert not report.has_errors()

    @patch("requests.get")
    def test_validate_references_template_missing(self, mock_get, proxmox_provider, env_config):
        """Test validation fails when referenced template doesn't exist."""
        # Mock API response without the required template
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {"name": "ubuntu-22.04", "template": 1},
            ]
        }
        mock_get.return_value = mock_response

        # Create resources that reference missing template
        resources = [
            ResourceConfig(
                provider="proxmox",
                type="vm",
                name="web-01",
                config={"template": "centos-9", "cores": 2},
            ),
        ]

        report = ValidationReport()
        proxmox_provider.validate_references(resources, env_config, report)

        assert report.has_errors()
        summary = report.get_summary()
        assert summary["errors"] >= 1

    def test_validate_references_no_credentials(self, proxmox_provider):
        """Test reference validation skips when no credentials."""
        report = ValidationReport()
        env_config = {"provider_settings": {"proxmox": {}}}
        resources = [
            ResourceConfig(
                provider="proxmox",
                type="vm",
                name="web-01",
                config={"template": "ubuntu-22.04"},
            ),
        ]

        # Should return early without making API calls
        proxmox_provider.validate_references(resources, env_config, report)

        # Should not have added any checks
        summary = report.get_summary()
        assert summary["total"] == 0

    @patch("requests.get")
    def test_validate_references_multiple_templates(self, mock_get, proxmox_provider, env_config):
        """Test validation of multiple template references."""
        # Mock API response with templates
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {"name": "ubuntu-22.04", "template": 1},
                {"name": "debian-12", "template": 1},
            ]
        }
        mock_get.return_value = mock_response

        # Create multiple VMs with different templates
        resources = [
            ResourceConfig(
                provider="proxmox",
                type="vm",
                name="web-01",
                config={"template": "ubuntu-22.04"},
            ),
            ResourceConfig(
                provider="proxmox",
                type="vm",
                name="db-01",
                config={"template": "debian-12"},
            ),
            ResourceConfig(
                provider="proxmox",
                type="vm",
                name="app-01",
                config={"template": "ubuntu-22.04"},  # Duplicate reference
            ),
        ]

        report = ValidationReport()
        proxmox_provider.validate_references(resources, env_config, report)

        assert not report.has_errors()
        # Should validate 2 unique templates
        summary = report.get_summary()
        assert summary["passed"] >= 2

    @patch("requests.get")
    def test_validate_references_api_error(self, mock_get, proxmox_provider, env_config):
        """Test validation handles API errors gracefully."""
        # Mock failed API response
        mock_response = Mock()
        mock_response.status_code = 500
        mock_get.return_value = mock_response

        resources = [
            ResourceConfig(
                provider="proxmox",
                type="vm",
                name="web-01",
                config={"template": "ubuntu-22.04"},
            ),
        ]

        report = ValidationReport()
        proxmox_provider.validate_references(resources, env_config, report)

        # Should have warnings about API failure
        summary = report.get_summary()
        assert summary["warnings"] >= 1
