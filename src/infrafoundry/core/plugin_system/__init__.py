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

__all__ = [
    "PluginConflictError",
    "PluginDiscoveryError",
    "PluginError",
    "PluginLoadError",
    "PluginMetadata",
    "PluginNotFoundError",
    "PluginType",
    "PluginTypeError",
    "PluginValidationError",
    "PluginVersionError",
    "ValidationResult",
]
