"""Tests for plugin system exceptions."""

from infrafoundry.core.plugin_system.exceptions import (
    PluginConflictError,
    PluginDiscoveryError,
    PluginError,
    PluginLoadError,
    PluginNotFoundError,
    PluginTypeError,
    PluginValidationError,
    PluginVersionError,
)


class TestPluginError:
    """Tests for the base PluginError class."""

    def test_basic_error(self) -> None:
        """Test basic error creation."""
        error = PluginError("Something went wrong")
        assert str(error) == "Something went wrong"
        assert error.message == "Something went wrong"
        assert error.plugin_type is None
        assert error.plugin_name is None
        assert error.details == {}

    def test_error_with_context(self) -> None:
        """Test error with plugin type and name context."""
        error = PluginError("Something went wrong", plugin_type="provider", plugin_name="proxmox")
        assert "Something went wrong" in str(error)
        assert "provider" in str(error)
        assert "proxmox" in str(error)
        assert error.plugin_type == "provider"
        assert error.plugin_name == "proxmox"

    def test_error_with_details(self) -> None:
        """Test error with additional details."""
        error = PluginError(
            "Something went wrong",
            plugin_type="provider",
            details={"key1": "value1", "key2": "value2"},
        )
        error_str = str(error)
        assert "key1=value1" in error_str
        assert "key2=value2" in error_str


class TestPluginDiscoveryError:
    """Tests for PluginDiscoveryError."""

    def test_basic_discovery_error(self) -> None:
        """Test basic discovery error."""
        error = PluginDiscoveryError("Failed to discover plugins")
        assert "Failed to discover plugins" in str(error)

    def test_discovery_error_with_group(self) -> None:
        """Test discovery error with entry point group."""
        error = PluginDiscoveryError(
            "Failed to scan group", entry_point_group="infrafoundry.providers"
        )
        assert "Failed to scan group" in str(error)
        assert error.entry_point_group == "infrafoundry.providers"

    def test_discovery_error_with_failed_plugins(self) -> None:
        """Test discovery error with list of failed plugins."""
        error = PluginDiscoveryError(
            "Multiple plugins failed",
            failed_plugins=["plugin1", "plugin2", "plugin3"],
        )
        assert "Multiple plugins failed" in str(error)
        assert error.failed_plugins == ["plugin1", "plugin2", "plugin3"]


class TestPluginLoadError:
    """Tests for PluginLoadError."""

    def test_basic_load_error(self) -> None:
        """Test basic load error."""
        error = PluginLoadError("Failed to load plugin")
        assert "Failed to load plugin" in str(error)

    def test_load_error_with_context(self) -> None:
        """Test load error with full context."""
        cause = ImportError("No module named 'foo'")
        error = PluginLoadError(
            "Import failed",
            plugin_type="provider",
            plugin_name="proxmox",
            entry_point="infrafoundry_proxmox:register",
            cause=cause,
        )
        assert "Import failed" in str(error)
        assert error.plugin_type == "provider"
        assert error.plugin_name == "proxmox"
        assert error.entry_point == "infrafoundry_proxmox:register"
        assert error.cause == cause


class TestPluginValidationError:
    """Tests for PluginValidationError."""

    def test_basic_validation_error(self) -> None:
        """Test basic validation error."""
        error = PluginValidationError("Validation failed")
        assert "Validation failed" in str(error)
        assert error.validation_errors == []

    def test_validation_error_with_errors(self) -> None:
        """Test validation error with specific errors."""
        errors = ["Missing method: create", "Missing method: delete"]
        error = PluginValidationError(
            "Plugin invalid",
            plugin_type="provider",
            plugin_name="proxmox",
            validation_errors=errors,
        )
        assert "Plugin invalid" in str(error)
        assert error.validation_errors == errors
        error_str = str(error)
        assert "create" in error_str
        assert "delete" in error_str


class TestPluginNotFoundError:
    """Tests for PluginNotFoundError."""

    def test_basic_not_found_error(self) -> None:
        """Test basic not found error."""
        error = PluginNotFoundError("Plugin not found")
        assert "Plugin not found" in str(error)
        assert error.available_plugins == []

    def test_not_found_error_with_suggestions(self) -> None:
        """Test not found error with available plugins."""
        available = ["proxmox", "lxd", "terraform"]
        error = PluginNotFoundError(
            "Plugin 'aws' not found",
            plugin_type="provider",
            plugin_name="aws",
            available_plugins=available,
        )
        assert "Plugin 'aws' not found" in str(error)
        assert error.available_plugins == available


class TestPluginConflictError:
    """Tests for PluginConflictError."""

    def test_basic_conflict_error(self) -> None:
        """Test basic conflict error."""
        error = PluginConflictError("Plugin already registered")
        assert "Plugin already registered" in str(error)

    def test_conflict_error_with_versions(self) -> None:
        """Test conflict error with version information."""
        error = PluginConflictError(
            "Version conflict",
            plugin_type="provider",
            plugin_name="proxmox",
            existing_version="1.0.0",
            new_version="2.0.0",
        )
        assert "Version conflict" in str(error)
        assert error.existing_version == "1.0.0"
        assert error.new_version == "2.0.0"
        error_str = str(error)
        assert "1.0.0" in error_str
        assert "2.0.0" in error_str


class TestPluginTypeError:
    """Tests for PluginTypeError."""

    def test_basic_type_error(self) -> None:
        """Test basic type error."""
        error = PluginTypeError("Plugin type not found")
        assert "Plugin type not found" in str(error)

    def test_type_error_with_available_types(self) -> None:
        """Test type error with available types."""
        available = ["provider", "reporter", "analyzer"]
        error = PluginTypeError(
            "Type 'foo' not found",
            plugin_type_name="foo",
            available_types=available,
        )
        assert "Type 'foo' not found" in str(error)
        assert error.plugin_type_name == "foo"
        assert error.available_types == available


class TestPluginVersionError:
    """Tests for PluginVersionError."""

    def test_basic_version_error(self) -> None:
        """Test basic version error."""
        error = PluginVersionError("Version incompatible")
        assert "Version incompatible" in str(error)

    def test_version_error_with_requirements(self) -> None:
        """Test version error with version requirements."""
        error = PluginVersionError(
            "Incompatible version",
            plugin_type="provider",
            plugin_name="proxmox",
            plugin_version="1.0.0",
            required_version=">=2.0.0",
        )
        assert "Incompatible version" in str(error)
        assert error.plugin_version == "1.0.0"
        assert error.required_version == ">=2.0.0"
        error_str = str(error)
        assert "1.0.0" in error_str
        assert ">=2.0.0" in error_str
