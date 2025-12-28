"""Secret resolution system.

This module provides the secret resolution system that resolves "secret://" URIs
in configuration to actual secret values from backends.

Example:
    >>> from infrafoundry.secrets.resolver import SecretResolver
    >>> resolver = SecretResolver()
    >>> resolver.configure_backend('env', {'prefix': 'INFRAFOUNDRY_'})
    >>> value = resolver.resolve('secret://env/proxmox/token')
"""

import logging
import re
from typing import Any

from infrafoundry.secrets.protocol import SecretBackend, SecretBackendError

logger = logging.getLogger(__name__)

# Pattern for secret:// URIs
SECRET_URI_PATTERN = re.compile(r"^secret://([^/]+)/(.+)$")


class SecretResolutionError(Exception):
    """Failed to resolve a secret."""

    pass


class SecretResolver:
    """Resolves secret:// URIs to actual values using configured backends.

    This class manages secret backend instances and resolves secret references
    in configuration values.

    Example:
        >>> resolver = SecretResolver()
        >>> resolver.configure_backend('env', {'prefix': 'APP_'})
        >>> value = resolver.resolve('secret://env/db/password')
        >>> print(value)
        'super-secret'
    """

    def __init__(self) -> None:
        """Initialize the secret resolver.

        Example:
            >>> resolver = SecretResolver()
        """
        self._backends: dict[str, SecretBackend] = {}
        self._backend_configs: dict[str, dict[str, Any]] = {}
        logger.debug("Initialized SecretResolver")

    def configure_backend(self, backend_name: str, config: dict[str, Any]) -> None:
        """Configure a secret backend for use.

        The backend will be instantiated on first use.

        Args:
            backend_name: Backend name (e.g., "env", "file", "vault")
            config: Backend-specific configuration

        Example:
            >>> resolver = SecretResolver()
            >>> resolver.configure_backend('file', {'base_path': '/run/secrets'})
        """
        self._backend_configs[backend_name] = config
        # Clear any cached backend instance
        if backend_name in self._backends:
            self._close_backend(backend_name)
            del self._backends[backend_name]

        logger.debug(f"Configured backend: {backend_name}")

    def _close_backend(self, backend_name: str) -> None:
        """Close a backend if it has a close method.

        Args:
            backend_name: Backend name to close
        """
        backend = self._backends.get(backend_name)
        if backend and hasattr(backend, "close"):
            try:
                backend.close()
                logger.debug(f"Closed backend: {backend_name}")
            except Exception as e:
                logger.warning(f"Error closing backend {backend_name}: {e}")

    def _get_backend(self, backend_name: str) -> SecretBackend:
        """Get or create a backend instance.

        Args:
            backend_name: Backend name (e.g., "env", "file")

        Returns:
            Backend instance

        Raises:
            SecretResolutionError: If backend not configured or cannot be loaded
        """
        # Return cached backend if available
        if backend_name in self._backends:
            return self._backends[backend_name]

        # Check if backend is configured
        if backend_name not in self._backend_configs:
            raise SecretResolutionError(
                f"Backend '{backend_name}' not configured. "
                f"Available backends: {list(self._backend_configs.keys())}"
            )

        # Load backend class from registry
        try:
            from infrafoundry.core.plugin_system import get_registry

            registry = get_registry()
            metadata = registry.get("secret_backend", backend_name)
            backend_class = metadata.implementation

            # Instantiate backend
            config = self._backend_configs[backend_name]
            backend: SecretBackend = backend_class(config)

            # Cache it
            self._backends[backend_name] = backend
            logger.debug(f"Loaded backend: {backend_name}")

            return backend

        except Exception as e:
            raise SecretResolutionError(f"Failed to load backend '{backend_name}': {e}") from e

    def is_secret_uri(self, value: Any) -> bool:
        """Check if a value is a secret:// URI.

        Args:
            value: Value to check (can be any type)

        Returns:
            True if value is a secret URI, False otherwise

        Example:
            >>> resolver = SecretResolver()
            >>> resolver.is_secret_uri('secret://env/db/password')
            True
            >>> resolver.is_secret_uri('plain-value')
            False
            >>> resolver.is_secret_uri(123)
            False
        """
        if not isinstance(value, str):
            return False
        return SECRET_URI_PATTERN.match(value) is not None

    def parse_secret_uri(self, uri: str) -> tuple[str, str]:
        """Parse a secret:// URI into backend name and key.

        Args:
            uri: Secret URI (e.g., "secret://env/proxmox/token")

        Returns:
            Tuple of (backend_name, secret_key)

        Raises:
            SecretResolutionError: If URI format is invalid

        Example:
            >>> resolver = SecretResolver()
            >>> backend, key = resolver.parse_secret_uri('secret://env/db/password')
            >>> print(backend, key)
            'env' 'db/password'
        """
        match = SECRET_URI_PATTERN.match(uri)
        if not match:
            raise SecretResolutionError(
                f"Invalid secret URI format: {uri}. Expected: secret://<backend>/<key>"
            )

        backend_name = match.group(1)
        secret_key = match.group(2)

        return backend_name, secret_key

    def resolve(self, value: str) -> str:
        """Resolve a secret:// URI to its actual value.

        Args:
            value: Secret URI to resolve (e.g., "secret://env/proxmox/token")

        Returns:
            Resolved secret value

        Raises:
            SecretResolutionError: If URI is invalid or resolution fails

        Example:
            >>> import os
            >>> os.environ['APP_DB_PASSWORD'] = 'secret123'
            >>> resolver = SecretResolver()
            >>> resolver.configure_backend('env', {'prefix': 'APP_'})
            >>> value = resolver.resolve('secret://env/db/password')
            >>> print(value)
            'secret123'
        """
        # Parse URI
        backend_name, secret_key = self.parse_secret_uri(value)

        try:
            # Get backend
            backend = self._get_backend(backend_name)

            # Resolve secret
            secret_value = backend.get_secret(secret_key)

            logger.debug(f"Resolved secret: {value}")
            return secret_value

        except SecretBackendError as e:
            raise SecretResolutionError(f"Failed to resolve secret '{value}': {e}") from e

    def resolve_config(self, config: dict[str, Any]) -> dict[str, Any]:
        """Recursively resolve all secret:// URIs in a configuration dict.

        This walks through the configuration and replaces any string values
        that are secret:// URIs with their resolved values.

        Args:
            config: Configuration dictionary that may contain secret URIs

        Returns:
            New dictionary with all secrets resolved

        Raises:
            SecretResolutionError: If any secret resolution fails

        Example:
            >>> import os
            >>> os.environ['APP_TOKEN'] = 'secret-token'
            >>> resolver = SecretResolver()
            >>> resolver.configure_backend('env', {'prefix': 'APP_'})
            >>> config = {
            ...     'api_url': 'https://example.com',
            ...     'api_token': 'secret://env/token',
            ...     'database': {
            ...         'host': 'localhost',
            ...         'password': 'secret://env/db/password'
            ...     }
            ... }
            >>> resolved = resolver.resolve_config(config)
            >>> print(resolved['api_token'])
            'secret-token'
        """
        result: dict[str, Any] = {}

        for key, value in config.items():
            if isinstance(value, str) and self.is_secret_uri(value):
                # Resolve secret URI
                result[key] = self.resolve(value)
            elif isinstance(value, dict):
                # Recursively resolve nested dict
                result[key] = self.resolve_config(value)
            elif isinstance(value, list):
                # Recursively resolve list items
                result[key] = [
                    self.resolve(item)
                    if isinstance(item, str) and self.is_secret_uri(item)
                    else self.resolve_config(item)
                    if isinstance(item, dict)
                    else item
                    for item in value
                ]
            else:
                # Keep non-secret values as-is
                result[key] = value

        return result

    def close(self) -> None:
        """Close all backend connections.

        This should be called when the resolver is no longer needed to
        clean up any resources (file handles, network connections, etc.).

        Example:
            >>> resolver = SecretResolver()
            >>> resolver.configure_backend('vault', {...})
            >>> # Use resolver...
            >>> resolver.close()
        """
        for backend_name in list(self._backends.keys()):
            self._close_backend(backend_name)
        self._backends.clear()
        logger.debug("Closed all backends")

    def __enter__(self) -> "SecretResolver":
        """Context manager entry.

        Example:
            >>> with SecretResolver() as resolver:
            ...     resolver.configure_backend('env', {})
            ...     value = resolver.resolve('secret://env/key')
        """
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit."""
        self.close()


# Global resolver instance
_resolver: SecretResolver | None = None


def get_resolver() -> SecretResolver:
    """Get the global secret resolver instance.

    Returns:
        Global SecretResolver instance

    Example:
        >>> from infrafoundry.secrets.resolver import get_resolver
        >>> resolver = get_resolver()
        >>> resolver.configure_backend('env', {})
    """
    global _resolver
    if _resolver is None:
        _resolver = SecretResolver()
    return _resolver


def _reset_resolver() -> None:
    """Reset the global resolver (for testing).

    Example:
        >>> from infrafoundry.secrets.resolver import _reset_resolver
        >>> _reset_resolver()  # Clean state for tests
    """
    global _resolver
    if _resolver is not None:
        _resolver.close()
    _resolver = None
