"""Registry for plugin types.

This module provides a registry for plugin types (not plugins themselves).
The registry maintains the set of available plugin types and allows the
generic plugin system to discover and manage plugins across all types.

Example:
    >>> from infrafoundry.core.plugin_system import get_type_registry
    >>> registry = get_type_registry()
    >>> registry.register_type(provider_plugin_type)
    >>> provider_type = registry.get_type("provider")
    >>> all_types = registry.list_types()
"""

import logging

from infrafoundry.core.plugin_system.exceptions import PluginTypeError
from infrafoundry.core.plugin_system.plugin_type import PluginType

logger = logging.getLogger(__name__)


class PluginTypeRegistry:
    """Registry of plugin types.

    This registry maintains the set of available plugin types.
    Plugin types register themselves at startup, allowing the generic
    plugin system to discover and manage plugins without knowing
    their specific types.

    Example:
        >>> registry = PluginTypeRegistry()
        >>> registry.register_type(provider_type)
        >>> registry.register_type(secret_backend_type)
        >>> types = registry.list_types()
        >>> print(types)
        ['provider', 'secret_backend']
    """

    def __init__(self) -> None:
        """Initialize plugin type registry."""
        self._types: dict[str, PluginType] = {}

    def register_type(self, plugin_type: PluginType) -> None:
        """Register a plugin type.

        Args:
            plugin_type: Plugin type to register

        Raises:
            PluginTypeError: If type with same name already registered

        Example:
            >>> registry.register_type(provider_plugin_type)
        """
        type_name = plugin_type.type_name

        if type_name in self._types:
            raise PluginTypeError(
                f"Plugin type '{type_name}' is already registered",
                plugin_type_name=type_name,
                available_types=self.list_types(),
            )

        self._types[type_name] = plugin_type
        logger.info(f"Registered plugin type: {type_name}")

    def get_type(self, type_name: str) -> PluginType:
        """Get a registered plugin type.

        Args:
            type_name: Name of the plugin type to retrieve

        Returns:
            The requested plugin type

        Raises:
            PluginTypeError: If plugin type not found

        Example:
            >>> provider_type = registry.get_type("provider")
            >>> print(provider_type.entry_point_group)
            'infrafoundry.providers'
        """
        if type_name not in self._types:
            raise PluginTypeError(
                f"Plugin type '{type_name}' is not registered",
                plugin_type_name=type_name,
                available_types=self.list_types(),
            )

        return self._types[type_name]

    def has_type(self, type_name: str) -> bool:
        """Check if a plugin type is registered.

        Args:
            type_name: Name of the plugin type to check

        Returns:
            True if the plugin type is registered, False otherwise

        Example:
            >>> if registry.has_type("provider"):
            ...     provider = registry.get_type("provider")
        """
        return type_name in self._types

    def list_types(self) -> list[str]:
        """List all registered plugin type names.

        Returns:
            List of registered plugin type names

        Example:
            >>> types = registry.list_types()
            >>> print(types)
            ['provider', 'secret_backend']
        """
        return list(self._types.keys())

    def get_all_types(self) -> list[PluginType]:
        """Get all registered plugin types.

        Returns:
            List of all registered plugin type instances

        Example:
            >>> for plugin_type in registry.get_all_types():
            ...     print(f"{plugin_type.type_name}: {plugin_type.entry_point_group}")
        """
        return list(self._types.values())

    def unregister_type(self, type_name: str) -> None:
        """Unregister a plugin type.

        This is primarily useful for testing.

        Args:
            type_name: Name of the plugin type to unregister

        Raises:
            PluginTypeError: If plugin type not found

        Example:
            >>> registry.unregister_type("provider")
        """
        if type_name not in self._types:
            raise PluginTypeError(
                f"Plugin type '{type_name}' is not registered",
                plugin_type_name=type_name,
                available_types=self.list_types(),
            )

        del self._types[type_name]
        logger.info(f"Unregistered plugin type: {type_name}")

    def clear(self) -> None:
        """Clear all registered plugin types.

        This is primarily useful for testing.

        Example:
            >>> registry.clear()
            >>> assert len(registry.list_types()) == 0
        """
        self._types.clear()
        logger.info("Cleared all plugin types")


# Global singleton instance
_type_registry: PluginTypeRegistry | None = None


def get_type_registry() -> PluginTypeRegistry:
    """Get the global plugin type registry.

    Returns:
        The global singleton PluginTypeRegistry instance

    Example:
        >>> registry = get_type_registry()
        >>> registry.register_type(my_plugin_type)
    """
    global _type_registry
    if _type_registry is None:
        _type_registry = PluginTypeRegistry()
    return _type_registry


def _reset_type_registry() -> None:
    """Reset the global plugin type registry.

    This is primarily useful for testing to ensure a clean state.

    Warning:
        This should only be used in tests. Production code should
        never call this function.
    """
    global _type_registry
    _type_registry = None
