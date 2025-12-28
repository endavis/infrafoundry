"""Plugin type abstraction.

This module defines the protocol that all plugin types must implement.
Plugin types define how to discover, load, validate, and register plugins
of their category (providers, secret backends, reporters, etc.).

Example:
    >>> class ProviderPluginType:
    ...     @property
    ...     def type_name(self) -> str:
    ...         return "provider"
    ...
    ...     @property
    ...     def entry_point_group(self) -> str:
    ...         return "infrafoundry.providers"
    ...
    ...     def load_plugin(self, entry_point):
    ...         # Load provider from entry point
    ...         pass
"""

from abc import abstractmethod
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class PluginMetadata:
    """Generic plugin metadata.

    This class contains metadata about a discovered plugin, regardless
    of plugin type. The `metadata` field allows plugin types to store
    type-specific information.

    Args:
        name: Plugin name (e.g., "proxmox", "pdf-reporter")
        version: Plugin version (semantic versioning recommended)
        plugin_type: Type category (e.g., "provider", "reporter")
        description: Human-readable description
        implementation: Plugin implementation (class, function, etc.)
        metadata: Type-specific metadata dictionary
        author: Optional plugin author
        url: Optional plugin homepage or repository URL
        requires_core: Optional core version requirement (e.g., ">=0.1.0")
    """

    name: str
    version: str
    plugin_type: str
    description: str
    implementation: Any
    metadata: dict[str, Any] = field(default_factory=dict)
    author: str | None = None
    url: str | None = None
    requires_core: str | None = None

    def __str__(self) -> str:
        """Return formatted plugin metadata string."""
        return f"{self.name} v{self.version} ({self.plugin_type}): {self.description}"


@dataclass
class ValidationResult:
    """Result of plugin validation.

    Used to communicate validation results from plugin type validators
    back to the discovery engine.

    Args:
        valid: Whether the plugin passed validation
        errors: List of validation error messages
        warnings: List of validation warning messages
    """

    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        """Return formatted validation result string."""
        parts = ["VALID" if self.valid else "INVALID"]

        if self.errors:
            parts.append(f"Errors: {'; '.join(self.errors)}")

        if self.warnings:
            parts.append(f"Warnings: {'; '.join(self.warnings)}")

        return " | ".join(parts)


class PluginType(Protocol):
    """Protocol that all plugin types must implement.

    This is the contract between the generic plugin infrastructure
    and specific plugin type implementations. Each plugin type
    (provider, secret backend, reporter, etc.) must implement this
    protocol to integrate with the plugin system.

    Example:
        >>> class MyPluginType:
        ...     @property
        ...     def type_name(self) -> str:
        ...         return "my_type"
        ...
        ...     @property
        ...     def entry_point_group(self) -> str:
        ...         return "infrafoundry.my_types"
        ...
        ...     def load_plugin(self, entry_point):
        ...         # Implementation
        ...         pass
        ...
        ...     def validate_plugin(self, metadata):
        ...         # Implementation
        ...         pass
        ...
        ...     def register_cli(self, app, plugins):
        ...         # Implementation
        ...         pass
    """

    @property
    @abstractmethod
    def entry_point_group(self) -> str:
        """Entry point group to scan for plugins of this type.

        Returns:
            Entry point group name (e.g., "infrafoundry.providers")

        Example:
            >>> plugin_type.entry_point_group
            'infrafoundry.providers'
        """

    @property
    @abstractmethod
    def type_name(self) -> str:
        """Human-readable plugin type name.

        Returns:
            Type name (e.g., "provider", "reporter", "analyzer")

        Example:
            >>> plugin_type.type_name
            'provider'
        """

    @abstractmethod
    def load_plugin(self, entry_point: Any) -> PluginMetadata:
        """Load a plugin from an entry point.

        This method is called during plugin discovery for each entry point
        found in the plugin type's entry point group. The implementation
        should load the entry point, extract metadata, and return a
        PluginMetadata instance.

        Args:
            entry_point: Entry point object from importlib.metadata

        Returns:
            PluginMetadata for the loaded plugin

        Raises:
            PluginLoadError: If loading fails (import error, missing register function, etc.)

        Example:
            >>> metadata = plugin_type.load_plugin(entry_point)
            >>> print(metadata.name)
            'proxmox'
        """

    @abstractmethod
    def validate_plugin(self, metadata: PluginMetadata) -> ValidationResult:
        """Validate that a plugin implements the required interface.

        This method is called after loading to verify the plugin
        implements the protocol correctly. It should check for required
        methods, attributes, and any type-specific requirements.

        Args:
            metadata: Plugin metadata to validate

        Returns:
            ValidationResult with validation status, errors, and warnings

        Example:
            >>> result = plugin_type.validate_plugin(metadata)
            >>> if not result.valid:
            ...     print(f"Validation failed: {result.errors}")
        """

    @abstractmethod
    def register_cli(self, app: Any, plugins: list[PluginMetadata]) -> None:
        """Register CLI commands for this plugin type.

        This method is called during CLI initialization to allow plugin
        types to register commands. Plugin types can create command groups,
        delegate to individual plugins, or skip CLI registration entirely.

        This is optional - plugin types that don't need CLI integration
        can provide an empty implementation.

        Args:
            app: Main CLI application (Click group)
            plugins: All loaded plugins of this type

        Example:
            >>> # Create a command group for all providers
            >>> provider_group = click.Group(name="providers")
            >>> app.add_command(provider_group)
            >>> # Let each provider register its commands
            >>> for plugin in plugins:
            ...     plugin.metadata["cli_registration"](provider_group)
        """
