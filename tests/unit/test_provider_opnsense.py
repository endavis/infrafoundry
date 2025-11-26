"""Unit tests for OPNsense provider reset and migrate functionality."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from infrafoundry.providers.opnsense import OPNsenseProvider


class TestOPNsenseProviderReset:
    """Tests for OPNsense provider reset methods (delegation to manager)."""

    @pytest.fixture
    def provider(self):
        """Create OPNsense provider instance for testing."""
        return OPNsenseProvider(config_dir=Path("."), output_dir=Path("."))

    @pytest.fixture
    def mock_manager(self):
        """Mock KeaDHCPManager for component operations."""
        with patch("infrafoundry.providers.opnsense.components.kea_dhcp.KeaDHCPManager") as mock:
            mock_instance = MagicMock()
            mock.return_value = mock_instance
            yield mock_instance

    def test_reset_kea_dhcpv4_delegates_to_manager(self, provider, mock_manager):
        """Test reset_kea_dhcpv4 delegates to manager."""
        provider.reset_kea_dhcpv4("test_env")
        mock_manager.reset_dhcpv4.assert_called_once_with("test_env", "opnsense")

    def test_reset_kea_dhcpv4_handles_errors(self, provider, mock_manager):
        """Test reset_kea_dhcpv4 propagates errors from manager."""
        mock_manager.reset_dhcpv4.side_effect = ValueError("Test error")

        with pytest.raises(ValueError, match="Test error"):
            provider.reset_kea_dhcpv4("test_env")

    def test_reset_kea_dhcpv6_delegates_to_manager(self, provider, mock_manager):
        """Test reset_kea_dhcpv6 delegates to manager."""
        provider.reset_kea_dhcpv6("test_env")
        mock_manager.reset_dhcpv6.assert_called_once_with("test_env", "opnsense")

    def test_reset_kea_dhcpv6_handles_errors(self, provider, mock_manager):
        """Test reset_kea_dhcpv6 propagates errors from manager."""
        mock_manager.reset_dhcpv6.side_effect = ValueError("Test error")

        with pytest.raises(ValueError, match="Test error"):
            provider.reset_kea_dhcpv6("test_env")


class TestOPNsenseProviderMigrate:
    """Tests for OPNsense provider migrate methods (delegation to manager)."""

    @pytest.fixture
    def provider(self):
        """Create OPNsense provider instance for testing."""
        return OPNsenseProvider(config_dir=Path("."), output_dir=Path("."))

    @pytest.fixture
    def mock_manager(self):
        """Mock KeaDHCPManager for component operations."""
        with patch("infrafoundry.providers.opnsense.components.kea_dhcp.KeaDHCPManager") as mock:
            mock_instance = MagicMock()
            mock.return_value = mock_instance
            yield mock_instance

    def test_migrate_kea_dhcp_delegates_to_manager(self, provider, mock_manager):
        """Test migrate_kea_dhcp delegates to manager and returns YAML."""
        mock_manager.migrate.return_value = "resources:\n  - type: test\n"

        result = provider.migrate_kea_dhcp("test_env")

        mock_manager.migrate.assert_called_once_with("test_env", "opnsense")
        assert result == "resources:\n  - type: test\n"

    def test_migrate_kea_dhcp_handles_errors(self, provider, mock_manager):
        """Test migrate_kea_dhcp propagates errors from manager."""
        mock_manager.migrate.side_effect = ValueError("Test error")

        with pytest.raises(ValueError, match="Test error"):
            provider.migrate_kea_dhcp("test_env")


class TestOPNsenseProviderBasic:
    """Basic OPNsense provider tests."""

    def test_provider_initialization(self):
        """Test provider initializes correctly."""
        provider = OPNsenseProvider(config_dir=Path("."), output_dir=Path("."))
        assert provider.config_dir == Path(".")
        assert provider.output_dir == Path(".")

    def test_provider_name(self):
        """Test provider name is correct."""
        provider = OPNsenseProvider(config_dir=Path("."), output_dir=Path("."))
        assert provider.name == "opnsense"
