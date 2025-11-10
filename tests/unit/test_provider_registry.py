"""Tests for provider registry."""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from infrafoundry.core.provider import ProviderBase
from infrafoundry.core.provider_registry import ProviderRegistry


class TestProviderRegistry:
    """Tests for ProviderRegistry."""

    @pytest.fixture
    def registry(self, tmp_path):
        """Create a provider registry instance."""
        config_dir = tmp_path / "config"
        output_dir = tmp_path / "output"
        config_dir.mkdir()
        output_dir.mkdir()
        return ProviderRegistry(config_dir, output_dir)

    def test_init(self, tmp_path):
        """Test registry initialization."""
        config_dir = tmp_path / "config"
        output_dir = tmp_path / "output"
        config_dir.mkdir()
        output_dir.mkdir()

        registry = ProviderRegistry(config_dir, output_dir)

        assert registry.config_dir == config_dir
        assert registry.output_dir == output_dir
        assert registry._providers == {}

    def test_register_provider(self, registry):
        """Test registering a provider."""
        mock_provider = Mock(spec=ProviderBase)
        mock_provider.name = "test_provider"

        registry.register_provider(mock_provider)

        assert registry.has_provider("test_provider")
        assert registry.get_provider("test_provider") == mock_provider

    def test_get_provider_not_found(self, registry):
        """Test getting a non-existent provider."""
        result = registry.get_provider("nonexistent")
        assert result is None

    def test_has_provider(self, registry):
        """Test checking provider existence."""
        mock_provider = Mock(spec=ProviderBase)
        mock_provider.name = "test_provider"

        assert not registry.has_provider("test_provider")

        registry.register_provider(mock_provider)

        assert registry.has_provider("test_provider")

    def test_get_all_providers(self, registry):
        """Test getting all registered providers."""
        mock_provider1 = Mock(spec=ProviderBase)
        mock_provider1.name = "provider1"

        mock_provider2 = Mock(spec=ProviderBase)
        mock_provider2.name = "provider2"

        registry.register_provider(mock_provider1)
        registry.register_provider(mock_provider2)

        providers = registry.get_all_providers()

        assert len(providers) == 2
        assert "provider1" in providers
        assert "provider2" in providers
        assert providers["provider1"] == mock_provider1
        assert providers["provider2"] == mock_provider2

    def test_get_all_providers_returns_copy(self, registry):
        """Test that get_all_providers returns a copy."""
        mock_provider = Mock(spec=ProviderBase)
        mock_provider.name = "test_provider"

        registry.register_provider(mock_provider)

        providers1 = registry.get_all_providers()
        providers2 = registry.get_all_providers()

        # Modify one copy
        providers1["new_provider"] = Mock()

        # Original should be unaffected
        assert "new_provider" not in providers2
        assert not registry.has_provider("new_provider")

    @patch("infrafoundry.core.provider_registry.importlib.import_module")
    def test_discover_and_register_proxmox(self, mock_import, registry):
        """Test discovering and registering Proxmox provider."""
        # Mock the Proxmox provider
        mock_module = Mock()
        mock_provider_instance = Mock(spec=ProviderBase)
        mock_provider_instance.name = "proxmox"

        class MockProxmoxProvider(ProviderBase):
            def __init__(self, config_dir: Path, output_dir: Path):
                super().__init__("proxmox", config_dir, output_dir)

            def validate_config(self, config):
                return True

            def generate_terraform(self, resources):
                pass

            def generate_ansible(self, resources):
                pass

            def get_resource_types(self):
                return ["vm"]

        mock_module.ProxmoxProvider = MockProxmoxProvider
        mock_import.return_value = mock_module

        # Mock dir() to return our provider class
        with patch.object(mock_module, "__dir__", return_value=["ProxmoxProvider"]):
            registry._discover_and_register_provider("proxmox")

        assert registry.has_provider("proxmox")

    @patch("infrafoundry.core.provider_registry.importlib.import_module")
    def test_discover_import_error(self, mock_import, registry):
        """Test handling import errors during discovery."""
        mock_import.side_effect = ImportError("Module not found")

        # Should not raise exception
        registry._discover_and_register_provider("nonexistent")

        # Provider should not be registered
        assert not registry.has_provider("nonexistent")

    def test_find_provider_class(self, registry):
        """Test finding provider class in module."""
        # Create a mock module with a provider class
        mock_module = Mock()

        class MockProvider(ProviderBase):
            def __init__(self, config_dir: Path, output_dir: Path):
                super().__init__("mock", config_dir, output_dir)

            def validate_config(self, config):
                return True

            def generate_terraform(self, resources):
                pass

            def generate_ansible(self, resources):
                pass

            def get_resource_types(self):
                return ["test"]

        # Add the class to the mock module
        mock_module.MockProvider = MockProvider
        mock_module.SomeOtherClass = str  # Non-provider class
        mock_module.some_variable = "test"

        # Use dir() to list attributes
        with patch.object(
            mock_module, "__dir__", return_value=["MockProvider", "SomeOtherClass", "some_variable"]
        ):
            result = registry._find_provider_class(mock_module, "mock")

        assert result == MockProvider

    def test_find_provider_class_not_found(self, registry):
        """Test finding provider class when none exists."""
        mock_module = Mock()
        mock_module.SomeClass = str  # Not a provider

        with patch.object(mock_module, "__dir__", return_value=["SomeClass"]):
            result = registry._find_provider_class(mock_module, "test")

        assert result is None

    def test_discover_all_no_providers_dir(self, registry):
        """Test discovery when providers directory doesn't exist."""
        with patch("pathlib.Path.exists", return_value=False):
            # Should not raise exception
            registry.discover_and_register_all()

        # No providers should be registered
        assert len(registry.get_all_providers()) == 0
