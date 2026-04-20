"""Provider plugin type implementation.

This module implements the provider plugin type, which manages discovery,
loading, and validation of infrastructure provider plugins.

Example:
    >>> from infrafoundry.core.plugin_system import get_type_registry
    >>> from infrafoundry.providers.plugin_type import ProviderPluginType
    >>>
    >>> # Register the provider plugin type
    >>> type_registry = get_type_registry()
    >>> provider_type = ProviderPluginType()
    >>> type_registry.register_type(provider_type)
"""

import logging
from dataclasses import dataclass
from typing import Any

from infrafoundry.core.plugin_system.exceptions import PluginLoadError
from infrafoundry.core.plugin_system.plugin_type import (
    PluginMetadata,
    ValidationResult,
)

logger = logging.getLogger(__name__)


@dataclass
class ProviderMetadata:
    """Metadata returned by provider registration function.

    Args:
        name: Provider name (e.g., "proxmox", "aws")
        version: Provider version
        description: Human-readable description
        provider_class: Provider class that implements BaseProvider
        resource_types: List of supported resource types
        cli_registration: Optional CLI registration function
        author: Optional author name
        url: Optional homepage or repository URL
    """

    name: str
    version: str
    description: str
    provider_class: type
    resource_types: list[str]
    cli_registration: Any | None = None
    author: str | None = None
    url: str | None = None


class ProviderPluginType:
    """Provider plugin type implementation.

    This class implements the PluginType protocol for infrastructure
    provider plugins. It handles discovery, loading, and validation
    of providers.

    Example:
        >>> provider_type = ProviderPluginType()
        >>> print(provider_type.type_name)
        'provider'
        >>> print(provider_type.entry_point_group)
        'infrafoundry.providers'
    """

    @property
    def entry_point_group(self) -> str:
        """Return the entry point group for providers.

        Returns:
            Entry point group name

        Example:
            >>> provider_type.entry_point_group
            'infrafoundry.providers'
        """
        return "infrafoundry.providers"

    @property
    def type_name(self) -> str:
        """Return the plugin type name.

        Returns:
            Type name

        Example:
            >>> provider_type.type_name
            'provider'
        """
        return "provider"

    def load_plugin(self, entry_point: Any) -> PluginMetadata:
        """Load a provider plugin from an entry point.

        This method loads the provider's registration function and calls
        it to get provider metadata, which is then converted to generic
        PluginMetadata.

        Args:
            entry_point: Entry point object from importlib.metadata

        Returns:
            PluginMetadata for the provider

        Raises:
            PluginLoadError: If loading or registration fails

        Example:
            >>> from importlib.metadata import entry_points
            >>> eps = entry_points(group="infrafoundry.providers")
            >>> for ep in eps:
            ...     metadata = provider_type.load_plugin(ep)
            ...     print(f"Loaded: {metadata.name}")
        """
        try:
            # Load the registration function
            register_func = entry_point.load()

            if not callable(register_func):
                raise PluginLoadError(
                    f"Entry point '{entry_point.name}' is not callable",
                    plugin_type="provider",
                    plugin_name=entry_point.name,
                    entry_point=str(entry_point),
                )

            # Call it to get provider metadata
            try:
                provider_metadata = register_func()
            except Exception as e:
                raise PluginLoadError(
                    f"Registration function failed: {e}",
                    plugin_type="provider",
                    plugin_name=entry_point.name,
                    entry_point=str(entry_point),
                    cause=e,
                ) from e

            if not isinstance(provider_metadata, ProviderMetadata):
                raise PluginLoadError(
                    f"Registration function must return ProviderMetadata, "
                    f"got {type(provider_metadata).__name__}",
                    plugin_type="provider",
                    plugin_name=entry_point.name,
                    entry_point=str(entry_point),
                )

            # Convert to generic PluginMetadata
            return PluginMetadata(
                name=provider_metadata.name,
                version=provider_metadata.version,
                plugin_type="provider",
                description=provider_metadata.description,
                implementation=provider_metadata.provider_class,
                metadata={
                    "resource_types": provider_metadata.resource_types,
                    "cli_registration": provider_metadata.cli_registration,
                },
                author=provider_metadata.author,
                url=provider_metadata.url,
            )

        except PluginLoadError:
            raise
        except Exception as e:
            raise PluginLoadError(
                f"Failed to load provider plugin: {e}",
                plugin_type="provider",
                plugin_name=entry_point.name,
                entry_point=str(entry_point),
                cause=e,
            ) from e

    def validate_plugin(self, metadata: PluginMetadata) -> ValidationResult:
        """Validate that a provider implements the BaseProvider protocol.

        This method checks that the provider class implements all required
        methods and has declared resource types.

        Args:
            metadata: Plugin metadata to validate

        Returns:
            ValidationResult with validation status

        Example:
            >>> result = provider_type.validate_plugin(metadata)
            >>> if not result.valid:
            ...     print(f"Errors: {result.errors}")
        """
        errors = []
        warnings = []

        provider_class = metadata.implementation

        # Check required methods (must match ProviderBase's abstract surface).
        required_methods = [
            "validate_config",
            "generate_terraform",
            "generate_ansible",
            "get_resource_types",
        ]

        for method in required_methods:
            if not hasattr(provider_class, method):
                errors.append(f"Missing required method: {method}")
            elif not callable(getattr(provider_class, method, None)):
                errors.append(f"'{method}' is not callable")

        # Check resource types
        resource_types = metadata.metadata.get("resource_types", [])
        if not resource_types:
            warnings.append("No resource types declared")
        elif not isinstance(resource_types, list):
            errors.append("resource_types must be a list")

        # Check provider class is a type
        if not isinstance(provider_class, type):
            errors.append(f"implementation must be a class, got {type(provider_class).__name__}")

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

    def register_cli(self, app: Any, plugins: list[PluginMetadata]) -> None:
        """Register CLI commands for providers.

        This method creates CLI command groups for each provider and
        delegates to the provider's CLI registration function if provided.

        Args:
            app: Main CLI application (Click group)
            plugins: All loaded provider plugins

        Example:
            >>> import click
            >>> app = click.Group()
            >>> provider_type.register_cli(app, providers)
        """
        try:
            import click
        except ImportError:
            logger.warning("Click not available, skipping CLI registration")
            return

        for plugin in plugins:
            try:
                # Create provider group (e.g., "foundry proxmox")
                provider_group = click.Group(
                    name=plugin.name,
                    help=plugin.description,
                )
                app.add_command(provider_group)

                # Let provider register its commands if it provides a function
                cli_registration = plugin.metadata.get("cli_registration")
                if cli_registration and callable(cli_registration):
                    cli_registration(provider_group)
                    logger.info(f"Registered CLI commands for provider: {plugin.name}")
                else:
                    logger.debug(f"No CLI registration function for provider: {plugin.name}")

            except Exception as e:
                logger.error(f"Failed to register CLI for provider {plugin.name}: {e}")
                continue
