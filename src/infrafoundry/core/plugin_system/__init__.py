"""Generic plugin system infrastructure.

This module provides a type-agnostic plugin system that supports multiple
plugin types (providers, secret backends, reporters, analyzers, etc.).

The plugin system uses a two-layer architecture:
1. Generic infrastructure (this module) - type-agnostic discovery and lifecycle
2. Plugin type implementations - define protocols and validation for their category

Example:
    >>> from infrafoundry.core.plugin_system import get_registry, discover_plugins
    >>> registry = get_registry()
    >>> discover_plugins()  # Discovers all plugin types and plugins
    >>> providers = registry.list("provider")
"""

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
from infrafoundry.core.plugin_system.plugin_type import (
    PluginMetadata,
    PluginType,
    ValidationResult,
)
from infrafoundry.core.plugin_system.plugin_type_registry import (
    PluginTypeRegistry,
    get_type_registry,
)
from infrafoundry.core.plugin_system.registry import (
    PluginRegistry,
    get_registry,
)

__all__ = [
    "PluginConflictError",
    "PluginDiscoveryError",
    "PluginError",
    "PluginLoadError",
    "PluginMetadata",
    "PluginNotFoundError",
    "PluginRegistry",
    "PluginType",
    "PluginTypeError",
    "PluginTypeRegistry",
    "PluginValidationError",
    "PluginVersionError",
    "ValidationResult",
    "get_registry",
    "get_type_registry",
]
