"""Provider-specific registry operations.

This module provides convenience functions for working with provider
plugins through the generic plugin registry.

Example:
    >>> from infrafoundry.providers.registry import ProviderRegistry
    >>> registry = ProviderRegistry()
    >>> providers = registry.list_providers()
    >>> proxmox = registry.create_provider("proxmox", {"api_url": "..."})
"""

from typing import Any

from infrafoundry.core.plugin_system import get_registry
from infrafoundry.core.plugin_system.plugin_type import PluginMetadata


class ProviderRegistry:
    """Provider-specific registry operations.

    This class wraps the generic plugin registry with provider-specific
    convenience methods.

    Example:
        >>> registry = ProviderRegistry()
        >>> providers = registry.list_providers()
        >>> for name in providers:
        ...     print(f"Provider: {name}")
    """

    def __init__(self) -> None:
        """Initialize provider registry."""
        self._core_registry = get_registry()

    def get_provider_metadata(self, name: str) -> PluginMetadata:
        """Get provider metadata.

        Args:
            name: Provider name (e.g., "proxmox", "aws")

        Returns:
            Plugin metadata for the provider

        Raises:
            PluginNotFoundError: If provider not found

        Example:
            >>> metadata = registry.get_provider_metadata("proxmox")
            >>> print(metadata.version)
            '1.0.0'
        """
        return self._core_registry.get("provider", name)

    def get_provider_class(self, name: str) -> Any:
        """Get provider class.

        Args:
            name: Provider name (e.g., "proxmox", "aws")

        Returns:
            Provider class that implements BaseProvider

        Raises:
            PluginNotFoundError: If provider not found

        Example:
            >>> provider_class = registry.get_provider_class("proxmox")
            >>> print(provider_class.__name__)
            'ProxmoxProvider'
        """
        metadata = self.get_provider_metadata(name)
        return metadata.implementation

    def create_provider(self, name: str, config: dict[str, Any]) -> Any:
        """Instantiate a provider.

        Args:
            name: Provider name (e.g., "proxmox", "aws")
            config: Provider configuration dictionary

        Returns:
            Instantiated provider

        Raises:
            PluginNotFoundError: If provider not found

        Example:
            >>> provider = registry.create_provider("proxmox", {
            ...     "api_url": "https://proxmox.example.com:8006",
            ...     "api_token": "secret://vault/proxmox/token"
            ... })
        """
        provider_class = self.get_provider_class(name)
        return provider_class(config)

    def list_providers(self) -> list[str]:
        """List all registered provider names.

        Returns:
            List of provider names

        Example:
            >>> providers = registry.list_providers()
            >>> print(providers)
            ['proxmox', 'aws', 'lxd']
        """
        providers = self._core_registry.list_by_type("provider")
        return [p.name for p in providers]

    def get_resource_types(self, name: str) -> list[str]:
        """Get resource types supported by a provider.

        Args:
            name: Provider name (e.g., "proxmox", "aws")

        Returns:
            List of supported resource types

        Raises:
            PluginNotFoundError: If provider not found

        Example:
            >>> types = registry.get_resource_types("proxmox")
            >>> print(types)
            ['vm', 'container', 'storage']
        """
        metadata = self.get_provider_metadata(name)
        resource_types = metadata.metadata.get("resource_types", [])
        if not isinstance(resource_types, list):
            return []
        return resource_types

    def has_provider(self, name: str) -> bool:
        """Check if a provider is registered.

        Args:
            name: Provider name to check

        Returns:
            True if provider is registered, False otherwise

        Example:
            >>> if registry.has_provider("proxmox"):
            ...     provider = registry.create_provider("proxmox", config)
        """
        return self._core_registry.has_plugin("provider", name)


def get_provider_registry() -> ProviderRegistry:
    """Get the provider registry.

    Returns:
        Provider registry instance

    Example:
        >>> from infrafoundry.providers.registry import get_provider_registry
        >>> registry = get_provider_registry()
        >>> providers = registry.list_providers()
    """
    return ProviderRegistry()
