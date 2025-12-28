"""File-based secret backend.

This module provides a secret backend that reads secrets from files.
It's useful for Docker secrets, Kubernetes secrets, and local development.

Example:
    >>> backend = FileSecretBackend({'base_path': '/run/secrets'})
    >>> # Reads from /run/secrets/proxmox/token
    >>> token = backend.get_secret('proxmox/token')
"""

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from infrafoundry.secrets.protocol import SecretBackendError, SecretNotFoundError

if TYPE_CHECKING:
    from infrafoundry.secrets.plugin_type import SecretBackendMetadata

logger = logging.getLogger(__name__)


class FileSecretBackend:
    """Secret backend that reads from files.

    This backend reads secrets from files in a directory structure.
    Secret keys map directly to file paths relative to the base path.

    Example:
        >>> backend = FileSecretBackend({'base_path': '/run/secrets'})
        >>> # Reads from /run/secrets/db/password
        >>> password = backend.get_secret('db/password')

    Args:
        config: Backend configuration with required 'base_path' key

    Note:
        This is a read-only backend. Calling set_secret() or delete_secret()
        will raise NotImplementedError.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize file-based secret backend.

        Args:
            config: Configuration dictionary with required keys:
                - base_path: Base directory for secret files

        Raises:
            SecretBackendError: If base_path is not provided or invalid

        Example:
            >>> backend = FileSecretBackend({'base_path': '/run/secrets'})
        """
        base_path = config.get("base_path")
        if not base_path:
            raise SecretBackendError("FileSecretBackend requires 'base_path' in config")

        self.base_path: Path = Path(base_path)

        if not self.base_path.exists():
            logger.warning(
                f"Base path does not exist: {self.base_path} "
                "(will be created when secrets are written)"
            )
        elif not self.base_path.is_dir():
            raise SecretBackendError(f"Base path is not a directory: {self.base_path}")

        logger.debug(f"Initialized FileSecretBackend with base_path: {self.base_path}")

    def _get_secret_path(self, key: str) -> Path:
        """Get the file path for a secret key.

        Args:
            key: Secret key (e.g., "proxmox/token")

        Returns:
            Path object for the secret file

        Raises:
            SecretBackendError: If key attempts path traversal

        Example:
            >>> backend = FileSecretBackend({'base_path': '/secrets'})
            >>> backend._get_secret_path('db/password')
            PosixPath('/secrets/db/password')
        """
        # Prevent path traversal attacks
        if ".." in key or key.startswith("/"):
            raise SecretBackendError(f"Invalid secret key (path traversal detected): {key}")

        secret_path = self.base_path / key

        # Ensure the resolved path is still under base_path
        try:
            secret_path.resolve().relative_to(self.base_path.resolve())
        except ValueError:
            raise SecretBackendError(f"Invalid secret key (path outside base): {key}") from None

        return secret_path

    def get_secret(self, key: str) -> str:
        """Retrieve a secret from a file.

        Args:
            key: Secret key (e.g., "proxmox/token")

        Returns:
            Secret value from file (trailing whitespace stripped)

        Raises:
            SecretNotFoundError: If file doesn't exist
            SecretBackendError: If file cannot be read

        Example:
            >>> backend = FileSecretBackend({'base_path': '/run/secrets'})
            >>> password = backend.get_secret('db/password')
            >>> print(password)
            'super-secret'
        """
        try:
            secret_path = self._get_secret_path(key)

            if not secret_path.exists():
                logger.debug(f"Secret not found: {key} (path: {secret_path})")
                raise SecretNotFoundError(
                    f"Secret '{key}' not found (expected file: {secret_path})"
                )

            if not secret_path.is_file():
                raise SecretBackendError(f"Secret '{key}' is not a file (path: {secret_path})")

            # Read file and strip trailing whitespace (common for secret files)
            value = secret_path.read_text(encoding="utf-8").rstrip()
            logger.debug(f"Retrieved secret: {key} from {secret_path}")
            return value

        except (SecretNotFoundError, SecretBackendError):
            raise
        except Exception as e:
            raise SecretBackendError(f"Failed to read secret '{key}': {e}") from e

    def list_secrets(self, prefix: str = "") -> list[str]:
        """List all secrets in the file backend.

        This recursively scans the base directory and returns all file paths
        as secret keys, optionally filtered by prefix.

        Args:
            prefix: Optional prefix to filter secrets (e.g., "proxmox/")

        Returns:
            List of secret keys (file paths relative to base_path)

        Raises:
            SecretBackendError: If listing fails

        Example:
            >>> backend = FileSecretBackend({'base_path': '/run/secrets'})
            >>> secrets = backend.list_secrets('db/')
            >>> print(sorted(secrets))
            ['db/host', 'db/password', 'db/username']
        """
        try:
            if not self.base_path.exists():
                logger.debug(f"Base path does not exist, returning empty list: {self.base_path}")
                return []

            secrets = []
            search_path = self.base_path

            # If prefix is provided, search from that subdirectory
            if prefix:
                search_path = self.base_path / prefix

            if not search_path.exists():
                logger.debug(f"Prefix path does not exist: {search_path}")
                return []

            # Recursively find all files
            for file_path in search_path.rglob("*"):
                if not file_path.is_file():
                    continue

                # Get relative path from base_path
                try:
                    rel_path = file_path.relative_to(self.base_path)
                except ValueError:
                    continue

                # Convert to secret key format (use forward slashes)
                key = str(rel_path).replace("\\", "/")
                secrets.append(key)

            logger.debug(
                f"Listed {len(secrets)} secrets with prefix '{prefix}' (search path: {search_path})"
            )
            return sorted(secrets)

        except Exception as e:
            raise SecretBackendError(f"Failed to list secrets: {e}") from e

    def health_check(self) -> bool:
        """Check if backend is accessible.

        Returns:
            True if base_path exists and is readable, False otherwise

        Example:
            >>> backend = FileSecretBackend({'base_path': '/run/secrets'})
            >>> if backend.health_check():
            ...     print("Backend is healthy")
        """
        try:
            # Check if base path exists and is accessible
            if not self.base_path.exists():
                return False

            # Try to list directory to verify read access
            list(self.base_path.iterdir())
            return True

        except Exception:
            return False


def register() -> "SecretBackendMetadata":
    """Register the file-based secret backend.

    Returns:
        SecretBackendMetadata for the file backend

    Example:
        >>> metadata = register()
        >>> print(metadata.name)
        'file'
    """
    from infrafoundry.secrets.plugin_type import SecretBackendMetadata

    return SecretBackendMetadata(
        name="file",
        version="1.0.0",
        description="Read secrets from files in a directory structure",
        backend_class=FileSecretBackend,
        read_only=True,
        author="InfraFoundry Team",
        url="https://github.com/infrascloudy/infrafoundry",
    )
