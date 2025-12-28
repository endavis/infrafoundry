"""Tests for plugin type registry."""

import pytest

from infrafoundry.core.plugin_system.exceptions import PluginTypeError
from infrafoundry.core.plugin_system.plugin_type import (
    PluginMetadata,
    ValidationResult,
)
from infrafoundry.core.plugin_system.plugin_type_registry import (
    PluginTypeRegistry,
    _reset_type_registry,
    get_type_registry,
)


class MockPluginType:
    """Mock plugin type for testing."""

    def __init__(self, type_name: str, entry_point_group: str) -> None:
        """Initialize mock plugin type."""
        self._type_name = type_name
        self._entry_point_group = entry_point_group

    @property
    def type_name(self) -> str:
        """Return type name."""
        return self._type_name

    @property
    def entry_point_group(self) -> str:
        """Return entry point group."""
        return self._entry_point_group

    def load_plugin(self, entry_point: object) -> PluginMetadata:
        """Mock load_plugin."""
        return PluginMetadata(
            name="test",
            version="1.0.0",
            plugin_type=self._type_name,
            description="Test plugin",
            implementation=object,
        )

    def validate_plugin(self, metadata: PluginMetadata) -> ValidationResult:
        """Mock validate_plugin."""
        return ValidationResult(valid=True)

    def register_cli(self, app: object, plugins: list[PluginMetadata]) -> None:
        """Mock register_cli."""
        pass


class TestPluginTypeRegistry:
    """Tests for PluginTypeRegistry."""

    def test_register_type(self) -> None:
        """Test registering a plugin type."""
        registry = PluginTypeRegistry()
        plugin_type = MockPluginType("provider", "infrafoundry.providers")

        registry.register_type(plugin_type)

        assert registry.has_type("provider")
        assert registry.get_type("provider") == plugin_type

    def test_register_duplicate_type(self) -> None:
        """Test registering a duplicate plugin type raises error."""
        registry = PluginTypeRegistry()
        plugin_type1 = MockPluginType("provider", "infrafoundry.providers")
        plugin_type2 = MockPluginType("provider", "infrafoundry.providers")

        registry.register_type(plugin_type1)

        with pytest.raises(PluginTypeError) as exc_info:
            registry.register_type(plugin_type2)

        assert "already registered" in str(exc_info.value)
        assert exc_info.value.plugin_type_name == "provider"

    def test_get_type(self) -> None:
        """Test retrieving a plugin type."""
        registry = PluginTypeRegistry()
        plugin_type = MockPluginType("provider", "infrafoundry.providers")

        registry.register_type(plugin_type)
        retrieved = registry.get_type("provider")

        assert retrieved == plugin_type
        assert retrieved.type_name == "provider"
        assert retrieved.entry_point_group == "infrafoundry.providers"

    def test_get_nonexistent_type(self) -> None:
        """Test retrieving a nonexistent plugin type raises error."""
        registry = PluginTypeRegistry()

        with pytest.raises(PluginTypeError) as exc_info:
            registry.get_type("nonexistent")

        assert "not registered" in str(exc_info.value)
        assert exc_info.value.plugin_type_name == "nonexistent"

    def test_has_type(self) -> None:
        """Test checking if a type is registered."""
        registry = PluginTypeRegistry()
        plugin_type = MockPluginType("provider", "infrafoundry.providers")

        assert not registry.has_type("provider")

        registry.register_type(plugin_type)

        assert registry.has_type("provider")
        assert not registry.has_type("nonexistent")

    def test_list_types(self) -> None:
        """Test listing all registered type names."""
        registry = PluginTypeRegistry()
        provider_type = MockPluginType("provider", "infrafoundry.providers")
        reporter_type = MockPluginType("reporter", "infrafoundry.reporters")

        assert registry.list_types() == []

        registry.register_type(provider_type)
        assert registry.list_types() == ["provider"]

        registry.register_type(reporter_type)
        assert set(registry.list_types()) == {"provider", "reporter"}

    def test_get_all_types(self) -> None:
        """Test getting all registered plugin type instances."""
        registry = PluginTypeRegistry()
        provider_type = MockPluginType("provider", "infrafoundry.providers")
        reporter_type = MockPluginType("reporter", "infrafoundry.reporters")

        assert registry.get_all_types() == []

        registry.register_type(provider_type)
        assert registry.get_all_types() == [provider_type]

        registry.register_type(reporter_type)
        assert set(registry.get_all_types()) == {provider_type, reporter_type}

    def test_unregister_type(self) -> None:
        """Test unregistering a plugin type."""
        registry = PluginTypeRegistry()
        plugin_type = MockPluginType("provider", "infrafoundry.providers")

        registry.register_type(plugin_type)
        assert registry.has_type("provider")

        registry.unregister_type("provider")
        assert not registry.has_type("provider")

    def test_unregister_nonexistent_type(self) -> None:
        """Test unregistering a nonexistent type raises error."""
        registry = PluginTypeRegistry()

        with pytest.raises(PluginTypeError) as exc_info:
            registry.unregister_type("nonexistent")

        assert "not registered" in str(exc_info.value)

    def test_clear(self) -> None:
        """Test clearing all registered types."""
        registry = PluginTypeRegistry()
        provider_type = MockPluginType("provider", "infrafoundry.providers")
        reporter_type = MockPluginType("reporter", "infrafoundry.reporters")

        registry.register_type(provider_type)
        registry.register_type(reporter_type)
        assert len(registry.list_types()) == 2

        registry.clear()
        assert len(registry.list_types()) == 0


class TestGlobalTypeRegistry:
    """Tests for global type registry singleton."""

    def setup_method(self) -> None:
        """Reset global registry before each test."""
        _reset_type_registry()

    def teardown_method(self) -> None:
        """Reset global registry after each test."""
        _reset_type_registry()

    def test_get_type_registry_singleton(self) -> None:
        """Test that get_type_registry returns the same instance."""
        registry1 = get_type_registry()
        registry2 = get_type_registry()

        assert registry1 is registry2

    def test_get_type_registry_persistence(self) -> None:
        """Test that registered types persist across calls."""
        registry1 = get_type_registry()
        plugin_type = MockPluginType("provider", "infrafoundry.providers")
        registry1.register_type(plugin_type)

        registry2 = get_type_registry()
        assert registry2.has_type("provider")
        assert registry2.get_type("provider") == plugin_type

    def test_reset_type_registry(self) -> None:
        """Test resetting the global registry."""
        registry1 = get_type_registry()
        plugin_type = MockPluginType("provider", "infrafoundry.providers")
        registry1.register_type(plugin_type)

        _reset_type_registry()

        registry2 = get_type_registry()
        assert not registry2.has_type("provider")
        assert registry2 is not registry1
