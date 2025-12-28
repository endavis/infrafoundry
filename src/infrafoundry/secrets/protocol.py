"""Secret backend protocol.

This module defines the protocol that all secret backend plugins must implement.
Secret backends provide secure storage and retrieval of sensitive configuration values.

Example:
    >>> class MySecretBackend:
    ...     def __init__(self, config: dict[str, Any]) -> None:
    ...         self.config = config
    ...
    ...     def get_secret(self, key: str) -> str:
    ...         # Implementation
    ...         pass
"""

from abc import abstractmethod
from typing import Any, Protocol


class SecretNotFoundError(Exception):
    """Secret not found in backend."""

    pass


class SecretBackendError(Exception):
    """Secret backend operation failed."""

    pass


class SecretBackend(Protocol):
    """Protocol that all secret backends must implement.

    Secret backends provide secure storage and retrieval of sensitive
    configuration values like API tokens, passwords, and certificates.

    Example:
        >>> class EnvSecretBackend:
        ...     def __init__(self, config: dict[str, Any]) -> None:
        ...         self.prefix = config.get("prefix", "")
        ...
        ...     def get_secret(self, key: str) -> str:
        ...         import os
        ...         env_key = self.prefix + key.upper().replace("/", "_")
        ...         value = os.environ.get(env_key)
        ...         if value is None:
        ...             raise SecretNotFoundError(f"Secret not found: {key}")
        ...         return value
    """

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize secret backend with configuration.

        Args:
            config: Backend-specific configuration

        Example:
            >>> config = {"prefix": "INFRAFOUNDRY_"}
            >>> backend = EnvSecretBackend(config)
        """

    @abstractmethod
    def get_secret(self, key: str) -> str:
        """Retrieve a secret value by key.

        Args:
            key: Secret key/path (e.g., "proxmox/token", "aws/access_key")

        Returns:
            Secret value as string

        Raises:
            SecretNotFoundError: If secret doesn't exist
            SecretBackendError: If retrieval fails

        Example:
            >>> value = backend.get_secret("proxmox/token")
            >>> print(value)
            'super-secret-token'
        """

    @abstractmethod
    def list_secrets(self, prefix: str = "") -> list[str]:
        """List available secret keys.

        Args:
            prefix: Optional prefix to filter secrets (e.g., "proxmox/")

        Returns:
            List of secret keys

        Raises:
            SecretBackendError: If listing fails

        Example:
            >>> keys = backend.list_secrets("proxmox/")
            >>> print(keys)
            ['proxmox/token', 'proxmox/url']
        """

    def set_secret(self, key: str, value: str) -> None:
        """Store a secret value (optional).

        Not all backends support writing secrets. Read-only backends
        should raise NotImplementedError.

        Args:
            key: Secret key/path
            value: Secret value to store

        Raises:
            NotImplementedError: If backend is read-only
            SecretBackendError: If storage fails

        Example:
            >>> backend.set_secret("proxmox/token", "new-token-value")
        """
        raise NotImplementedError("This backend does not support writing secrets")

    def delete_secret(self, key: str) -> None:
        """Delete a secret (optional).

        Not all backends support deleting secrets. Read-only backends
        should raise NotImplementedError.

        Args:
            key: Secret key/path to delete

        Raises:
            NotImplementedError: If backend is read-only
            SecretNotFoundError: If secret doesn't exist
            SecretBackendError: If deletion fails

        Example:
            >>> backend.delete_secret("proxmox/old_token")
        """
        raise NotImplementedError("This backend does not support deleting secrets")

    def health_check(self) -> bool:
        """Check if backend is accessible.

        Returns:
            True if backend is healthy, False otherwise

        Example:
            >>> if backend.health_check():
            ...     print("Backend is healthy")
        """
        try:
            # Default implementation: try listing secrets
            self.list_secrets()
            return True
        except Exception:
            return False

    def close(self) -> None:
        """Clean up resources (connections, sessions, etc.).

        Called when backend is no longer needed.

        Example:
            >>> backend.close()
        """
        pass
