"""Secret backend plugin type implementation.

This module implements the secret backend plugin type, which manages discovery,
loading, and validation of secret backend plugins.
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
class SecretBackendMetadata:
    """Metadata returned by secret backend registration function.

    Args:
        name: Backend name (e.g., "env", "vault", "aws")
        version: Backend version
        description: Human-readable description
        backend_class: Backend class that implements SecretBackend
        read_only: Whether backend is read-only
        author: Optional author name
        url: Optional homepage or repository URL
    """

    name: str
    version: str
    description: str
    backend_class: type
    read_only: bool = True
    author: str | None = None
    url: str | None = None


class SecretBackendPluginType:
    """Secret backend plugin type implementation.

    This class implements the PluginType protocol for secret backend plugins.
    It handles discovery, loading, and validation of secret backends.
    """

    @property
    def entry_point_group(self) -> str:
        """Return the entry point group for secret backends.

        Returns:
            Entry point group name
        """
        return "infrafoundry.secrets"

    @property
    def type_name(self) -> str:
        """Return the plugin type name.

        Returns:
            Type name
        """
        return "secret_backend"

    def load_plugin(self, entry_point: Any) -> PluginMetadata:
        """Load a secret backend plugin from an entry point.

        Args:
            entry_point: Entry point object from importlib.metadata

        Returns:
            PluginMetadata for the secret backend

        Raises:
            PluginLoadError: If loading or registration fails
        """
        try:
            # Load the registration function
            register_func = entry_point.load()

            if not callable(register_func):
                raise PluginLoadError(
                    f"Entry point '{entry_point.name}' is not callable",
                    plugin_type="secret_backend",
                    plugin_name=entry_point.name,
                    entry_point=str(entry_point),
                )

            # Call it to get backend metadata
            try:
                backend_metadata = register_func()
            except Exception as e:
                raise PluginLoadError(
                    f"Registration function failed: {e}",
                    plugin_type="secret_backend",
                    plugin_name=entry_point.name,
                    entry_point=str(entry_point),
                    cause=e,
                ) from e

            if not isinstance(backend_metadata, SecretBackendMetadata):
                raise PluginLoadError(
                    f"Registration function must return SecretBackendMetadata, "
                    f"got {type(backend_metadata).__name__}",
                    plugin_type="secret_backend",
                    plugin_name=entry_point.name,
                    entry_point=str(entry_point),
                )

            # Convert to generic PluginMetadata
            return PluginMetadata(
                name=backend_metadata.name,
                version=backend_metadata.version,
                plugin_type="secret_backend",
                description=backend_metadata.description,
                implementation=backend_metadata.backend_class,
                metadata={
                    "read_only": backend_metadata.read_only,
                },
                author=backend_metadata.author,
                url=backend_metadata.url,
            )

        except PluginLoadError:
            raise
        except Exception as e:
            raise PluginLoadError(
                f"Failed to load secret backend plugin: {e}",
                plugin_type="secret_backend",
                plugin_name=entry_point.name,
                entry_point=str(entry_point),
                cause=e,
            ) from e

    def validate_plugin(self, metadata: PluginMetadata) -> ValidationResult:
        """Validate that a secret backend implements the SecretBackend protocol.

        Args:
            metadata: Plugin metadata to validate

        Returns:
            ValidationResult with validation status
        """
        errors: list[str] = []
        warnings: list[str] = []

        backend_class = metadata.implementation

        # Check required methods
        required_methods = ["get_secret", "list_secrets"]

        for method in required_methods:
            if not hasattr(backend_class, method):
                errors.append(f"Missing required method: {method}")
            elif not callable(getattr(backend_class, method, None)):
                errors.append(f"'{method}' is not callable")

        # Check optional methods
        optional_methods = ["set_secret", "delete_secret", "health_check", "close"]
        for method in optional_methods:
            if hasattr(backend_class, method) and not callable(
                getattr(backend_class, method, None)
            ):
                errors.append(f"'{method}' exists but is not callable")

        # Check backend class is a type
        if not isinstance(backend_class, type):
            errors.append(f"implementation must be a class, got {type(backend_class).__name__}")

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

    def register_cli(self, app: Any, plugins: list[PluginMetadata]) -> None:
        """Register CLI commands for secret backends.

        Secret backends typically don't need CLI commands, but we provide
        a hook for backends that want to register management commands.

        Args:
            app: Main CLI application (Click group)
            plugins: All loaded secret backend plugins
        """
        # Secret backends typically don't need CLI registration
        # But we log what's available
        logger.info(f"Registered {len(plugins)} secret backend(s)")
        for plugin in plugins:
            logger.debug(f"  - {plugin.name}: {plugin.description}")
