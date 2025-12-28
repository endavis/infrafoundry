"""Generic plugin registry.

This module provides a type-agnostic registry for storing and retrieving
plugins of any type. The registry maintains plugins grouped by type,
allowing efficient lookups and listings.

Example:
    >>> from infrafoundry.core.plugin_system import get_registry
    >>> registry = get_registry()
    >>> registry.register(proxmox_metadata)
    >>> proxmox = registry.get("provider", "proxmox")
    >>> all_providers = registry.list_by_type("provider")
"""

import logging

from infrafoundry.core.plugin_system.exceptions import (
    PluginConflictError,
    PluginNotFoundError,
)
from infrafoundry.core.plugin_system.plugin_type import PluginMetadata

logger = logging.getLogger(__name__)


class PluginRegistry:
    """Generic registry for all plugins.

    This registry stores plugins of any type, organizing them by
    plugin type and name. It provides methods for registration,
    lookup, and listing plugins.

    Storage structure: {plugin_type: {plugin_name: PluginMetadata}}

    Example:
        >>> registry = PluginRegistry()
        >>> registry.register(proxmox_metadata)
        >>> registry.register(pdf_reporter_metadata)
        >>> providers = registry.list_by_type("provider")
        >>> all_plugins = registry.list_all()
    """

    def __init__(self) -> None:
        """Initialize plugin registry."""
        # Storage: {plugin_type: {plugin_name: PluginMetadata}}
        self._plugins: dict[str, dict[str, PluginMetadata]] = {}

    def register(self, metadata: PluginMetadata) -> None:
        """Register a plugin.

        Args:
            metadata: Plugin metadata to register

        Raises:
            PluginConflictError: If plugin with same name and type already registered

        Example:
            >>> registry.register(proxmox_metadata)
        """
        plugin_type = metadata.plugin_type
        plugin_name = metadata.name

        # Initialize type category if needed
        if plugin_type not in self._plugins:
            self._plugins[plugin_type] = {}

        # Check for duplicates
        if plugin_name in self._plugins[plugin_type]:
            existing = self._plugins[plugin_type][plugin_name]
            raise PluginConflictError(
                f"Plugin '{plugin_name}' ({plugin_type}) is already registered",
                plugin_type=plugin_type,
                plugin_name=plugin_name,
                existing_version=existing.version,
                new_version=metadata.version,
            )

        self._plugins[plugin_type][plugin_name] = metadata
        logger.info(f"Registered plugin: {plugin_name} ({plugin_type}) v{metadata.version}")

    def get(self, plugin_type: str, plugin_name: str) -> PluginMetadata:
        """Get a plugin by type and name.

        Args:
            plugin_type: Plugin type (e.g., "provider", "reporter")
            plugin_name: Plugin name (e.g., "proxmox", "pdf")

        Returns:
            Plugin metadata for the requested plugin

        Raises:
            PluginNotFoundError: If plugin not found

        Example:
            >>> proxmox = registry.get("provider", "proxmox")
            >>> print(proxmox.version)
            '0.1.0'
        """
        if plugin_type not in self._plugins:
            raise PluginNotFoundError(
                f"No plugins of type '{plugin_type}' are registered",
                plugin_type=plugin_type,
                plugin_name=plugin_name,
                available_plugins=[],
            )

        if plugin_name not in self._plugins[plugin_type]:
            available = list(self._plugins[plugin_type].keys())
            raise PluginNotFoundError(
                f"Plugin '{plugin_name}' ({plugin_type}) not found",
                plugin_type=plugin_type,
                plugin_name=plugin_name,
                available_plugins=available,
            )

        return self._plugins[plugin_type][plugin_name]

    def has_plugin(self, plugin_type: str, plugin_name: str) -> bool:
        """Check if a plugin is registered.

        Args:
            plugin_type: Plugin type (e.g., "provider")
            plugin_name: Plugin name (e.g., "proxmox")

        Returns:
            True if the plugin is registered, False otherwise

        Example:
            >>> if registry.has_plugin("provider", "proxmox"):
            ...     proxmox = registry.get("provider", "proxmox")
        """
        return plugin_type in self._plugins and plugin_name in self._plugins[plugin_type]

    def list_by_type(self, plugin_type: str) -> list[PluginMetadata]:
        """List all plugins of a specific type.

        Args:
            plugin_type: Plugin type to list (e.g., "provider", "reporter")

        Returns:
            List of plugin metadata for all plugins of the specified type.
            Returns empty list if no plugins of that type are registered.

        Example:
            >>> providers = registry.list_by_type("provider")
            >>> for provider in providers:
            ...     print(f"{provider.name} v{provider.version}")
        """
        if plugin_type not in self._plugins:
            return []

        return list(self._plugins[plugin_type].values())

    def list_all(self) -> dict[str, list[PluginMetadata]]:
        """List all plugins grouped by type.

        Returns:
            Dictionary mapping plugin type to list of plugin metadata

        Example:
            >>> all_plugins = registry.list_all()
            >>> for plugin_type, plugins in all_plugins.items():
            ...     print(f"{plugin_type}: {len(plugins)} plugins")
        """
        return {
            plugin_type: list(plugins.values()) for plugin_type, plugins in self._plugins.items()
        }

    def list_types(self) -> list[str]:
        """List all plugin types that have registered plugins.

        Returns:
            List of plugin type names that have at least one registered plugin

        Example:
            >>> types = registry.list_types()
            >>> print(types)
            ['provider', 'reporter', 'analyzer']
        """
        return list(self._plugins.keys())

    def unregister(self, plugin_type: str, plugin_name: str) -> None:
        """Unregister a plugin.

        This is primarily useful for testing.

        Args:
            plugin_type: Plugin type (e.g., "provider")
            plugin_name: Plugin name (e.g., "proxmox")

        Raises:
            PluginNotFoundError: If plugin not found

        Example:
            >>> registry.unregister("provider", "proxmox")
        """
        if plugin_type not in self._plugins:
            raise PluginNotFoundError(
                f"No plugins of type '{plugin_type}' are registered",
                plugin_type=plugin_type,
                plugin_name=plugin_name,
            )

        if plugin_name not in self._plugins[plugin_type]:
            available = list(self._plugins[plugin_type].keys())
            raise PluginNotFoundError(
                f"Plugin '{plugin_name}' ({plugin_type}) not found",
                plugin_type=plugin_type,
                plugin_name=plugin_name,
                available_plugins=available,
            )

        del self._plugins[plugin_type][plugin_name]
        logger.info(f"Unregistered plugin: {plugin_name} ({plugin_type})")

        # Clean up empty type category
        if not self._plugins[plugin_type]:
            del self._plugins[plugin_type]

    def clear(self) -> None:
        """Clear all registered plugins.

        This is primarily useful for testing.

        Example:
            >>> registry.clear()
            >>> assert len(registry.list_all()) == 0
        """
        self._plugins.clear()
        logger.info("Cleared all plugins from registry")


# Global singleton instance
_registry: PluginRegistry | None = None


def get_registry() -> PluginRegistry:
    """Get the global plugin registry.

    Returns:
        The global singleton PluginRegistry instance

    Example:
        >>> registry = get_registry()
        >>> registry.register(my_plugin_metadata)
    """
    global _registry
    if _registry is None:
        _registry = PluginRegistry()
    return _registry


def _reset_registry() -> None:
    """Reset the global plugin registry.

    This is primarily useful for testing to ensure a clean state.

    Warning:
        This should only be used in tests. Production code should
        never call this function.
    """
    global _registry
    _registry = None
