"""Unit tests for OPNsense provider reset and migrate functionality."""

import warnings
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
    """Tests for the deprecated ``migrate_kea_dhcp`` shim.

    After #726 the shim delegates through the extractor registry rather
    than constructing a manager directly. These tests verify the shim
    still returns the manager's YAML payload and emits the
    ``DeprecationWarning``; the registry-driven dispatch contract is
    covered in ``tests/unit/providers/opnsense/test_provider_extractors.py``.
    """

    @pytest.fixture
    def provider(self):
        """Create OPNsense provider instance for testing."""
        return OPNsenseProvider(config_dir=Path("."), output_dir=Path("."))

    def test_migrate_kea_dhcp_delegates_via_registry(self, provider):
        """``migrate_kea_dhcp`` returns the registry extractor's YAML."""
        from infrafoundry.core.extractors import get_extractor

        extractor = get_extractor("opnsense", "kea_dhcp")

        with (
            patch.object(extractor.manager_class, "__init__", return_value=None),
            patch.object(
                extractor.manager_class,
                "migrate",
                return_value="resources:\n  - type: test\n",
            ),
            warnings.catch_warnings(record=True) as caught,
        ):
            warnings.simplefilter("always")
            result = provider.migrate_kea_dhcp("test_env")

        assert result == "resources:\n  - type: test\n"
        deprecations = [w for w in caught if issubclass(w.category, DeprecationWarning)]
        assert len(deprecations) >= 1

    def test_migrate_kea_dhcp_handles_errors(self, provider):
        """``migrate_kea_dhcp`` propagates errors from the manager."""
        from infrafoundry.core.extractors import get_extractor

        extractor = get_extractor("opnsense", "kea_dhcp")

        with (
            patch.object(extractor.manager_class, "__init__", return_value=None),
            patch.object(
                extractor.manager_class,
                "migrate",
                side_effect=ValueError("Test error"),
            ),
            pytest.raises(ValueError, match="Test error"),
        ):
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
