"""Generic plugin discovery.

This module provides a type-agnostic plugin discovery engine that can
discover plugins of any type. The discovery engine delegates type-specific
loading and validation to PluginType implementations.

Example:
    >>> from infrafoundry.core.plugin_system import get_type_registry
    >>> from infrafoundry.core.plugin_system.discovery import PluginDiscovery
    >>>
    >>> discovery = PluginDiscovery()
    >>> type_registry = get_type_registry()
    >>>
    >>> # Discover plugins for a specific type
    >>> provider_type = type_registry.get_type("provider")
    >>> providers = discovery.discover_plugins(provider_type)
    >>>
    >>> # Discover plugins for all types
    >>> all_plugins = discovery.discover_all(type_registry.get_all_types())
"""

import logging
from importlib.metadata import entry_points
from typing import TYPE_CHECKING

from infrafoundry.core.plugin_system.exceptions import (
    PluginDiscoveryError,
    PluginLoadError,
)
from infrafoundry.core.plugin_system.plugin_type import PluginMetadata, PluginType

if TYPE_CHECKING:
    from infrafoundry.core.plugin_system.registry import PluginRegistry

logger = logging.getLogger(__name__)


class PluginDiscovery:
    """Generic plugin discovery engine.

    This engine is completely type-agnostic. It knows how to scan
    entry points and coordinate with PluginType implementations,
    but has no knowledge of providers, reporters, or other specific
    plugin types.

    Example:
        >>> discovery = PluginDiscovery()
        >>> plugins = discovery.discover_plugins(provider_type)
        >>> for plugin in plugins:
        ...     print(f"{plugin.name} v{plugin.version}")
    """

    def discover_plugins(self, plugin_type: PluginType) -> list[PluginMetadata]:
        """Discover all plugins for a given plugin type.

        This method scans the entry point group specified by the plugin type,
        loads each plugin using the plugin type's load_plugin() method,
        validates each plugin, and returns the list of valid plugins.

        Args:
            plugin_type: Plugin type to discover plugins for

        Returns:
            List of discovered and validated plugin metadata

        Raises:
            PluginDiscoveryError: If discovery process fails critically

        Example:
            >>> provider_type = type_registry.get_type("provider")
            >>> providers = discovery.discover_plugins(provider_type)
            >>> print(f"Found {len(providers)} providers")
        """
        discovered = []
        failed = []
        group = plugin_type.entry_point_group

        logger.info(f"Discovering plugins for '{plugin_type.type_name}' (group: {group})")

        try:
            # Get all entry points for this group
            eps = entry_points(group=group)
        except Exception as e:
            raise PluginDiscoveryError(
                f"Failed to scan entry point group '{group}'",
                entry_point_group=group,
            ) from e

        for ep in eps:
            try:
                # Let the plugin type load the plugin
                metadata = plugin_type.load_plugin(ep)

                # Validate the plugin
                validation = plugin_type.validate_plugin(metadata)

                if not validation.valid:
                    logger.error(
                        f"Plugin {ep.name} validation failed: {', '.join(validation.errors)}"
                    )
                    failed.append(ep.name)
                    continue

                if validation.warnings:
                    for warning in validation.warnings:
                        logger.warning(f"Plugin {ep.name}: {warning}")

                discovered.append(metadata)
                logger.info(
                    f"Discovered plugin: {ep.name} ({plugin_type.type_name}) v{metadata.version}"
                )

            except PluginLoadError as e:
                logger.error(f"Failed to load plugin {ep.name}: {e}")
                failed.append(ep.name)
                continue
            except Exception as e:
                logger.error(f"Unexpected error loading plugin {ep.name}: {e}")
                failed.append(ep.name)
                continue

        logger.info(
            f"Discovered {len(discovered)} {plugin_type.type_name} plugin(s) ({len(failed)} failed)"
        )

        return discovered

    def discover_all(self, plugin_types: list[PluginType]) -> dict[str, list[PluginMetadata]]:
        """Discover plugins for all plugin types.

        This method discovers plugins for multiple plugin types in a single
        call, organizing the results by plugin type.

        Args:
            plugin_types: List of plugin types to discover

        Returns:
            Dictionary mapping plugin type name to list of plugins

        Example:
            >>> all_types = type_registry.get_all_types()
            >>> all_plugins = discovery.discover_all(all_types)
            >>> for type_name, plugins in all_plugins.items():
            ...     print(f"{type_name}: {len(plugins)} plugins")
        """
        all_plugins = {}

        for plugin_type in plugin_types:
            try:
                plugins = self.discover_plugins(plugin_type)
                all_plugins[plugin_type.type_name] = plugins
            except PluginDiscoveryError as e:
                logger.error(f"Failed to discover {plugin_type.type_name} plugins: {e}")
                all_plugins[plugin_type.type_name] = []
                continue

        return all_plugins

    def discover_and_register(
        self,
        plugin_type: PluginType,
        registry: "PluginRegistry",
    ) -> int:
        """Discover plugins and register them in the registry.

        This is a convenience method that combines discovery and registration.

        Args:
            plugin_type: Plugin type to discover
            registry: Plugin registry to register plugins in

        Returns:
            Number of plugins successfully registered

        Example:
            >>> from infrafoundry.core.plugin_system import get_registry
            >>> registry = get_registry()
            >>> count = discovery.discover_and_register(provider_type, registry)
            >>> print(f"Registered {count} providers")
        """
        plugins = self.discover_plugins(plugin_type)
        registered = 0

        for metadata in plugins:
            try:
                registry.register(metadata)
                registered += 1
            except Exception as e:
                logger.error(
                    f"Failed to register plugin {metadata.name} ({metadata.plugin_type}): {e}"
                )
                continue

        return registered

    def discover_all_and_register(
        self,
        plugin_types: list[PluginType],
        registry: "PluginRegistry",
    ) -> dict[str, int]:
        """Discover all plugins and register them in the registry.

        This is a convenience method that combines discovery and registration
        for multiple plugin types.

        Args:
            plugin_types: List of plugin types to discover
            registry: Plugin registry to register plugins in

        Returns:
            Dictionary mapping plugin type name to number of plugins registered

        Example:
            >>> all_types = type_registry.get_all_types()
            >>> counts = discovery.discover_all_and_register(all_types, registry)
            >>> for type_name, count in counts.items():
            ...     print(f"{type_name}: {count} plugins registered")
        """
        counts = {}

        for plugin_type in plugin_types:
            count = self.discover_and_register(plugin_type, registry)
            counts[plugin_type.type_name] = count

        return counts
