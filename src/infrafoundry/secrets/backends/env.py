"""Environment variable secret backend.

This module provides a secret backend that reads secrets from environment variables.
It's the simplest backend and useful for development and CI/CD environments.

Example:
    >>> import os
    >>> os.environ['INFRAFOUNDRY_PROXMOX_TOKEN'] = 'my-secret'
    >>> backend = EnvSecretBackend({'prefix': 'INFRAFOUNDRY_'})
    >>> token = backend.get_secret('proxmox/token')
    >>> print(token)
    'my-secret'
"""

import logging
import os
from typing import TYPE_CHECKING, Any

from infrafoundry.secrets.protocol import SecretBackendError, SecretNotFoundError

if TYPE_CHECKING:
    from infrafoundry.secrets.plugin_type import SecretBackendMetadata

logger = logging.getLogger(__name__)


class EnvSecretBackend:
    """Secret backend that reads from environment variables.

    This backend transforms secret keys into environment variable names by:
    1. Adding a configurable prefix
    2. Converting to uppercase
    3. Replacing '/' with '_'

    Example:
        >>> backend = EnvSecretBackend({'prefix': 'INFRAFOUNDRY_'})
        >>> # Looks for INFRAFOUNDRY_PROXMOX_TOKEN
        >>> token = backend.get_secret('proxmox/token')

    Args:
        config: Backend configuration with optional 'prefix' key

    Note:
        This is a read-only backend. Calling set_secret() or delete_secret()
        will raise NotImplementedError.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize environment variable backend.

        Args:
            config: Configuration dictionary with optional keys:
                - prefix: Prefix for environment variables (default: "")

        Example:
            >>> backend = EnvSecretBackend({'prefix': 'INFRAFOUNDRY_'})
        """
        self.prefix: str = config.get("prefix", "")
        logger.debug(f"Initialized EnvSecretBackend with prefix: {self.prefix}")

    def _key_to_env(self, key: str) -> str:
        """Convert secret key to environment variable name.

        Args:
            key: Secret key (e.g., "proxmox/token")

        Returns:
            Environment variable name (e.g., "INFRAFOUNDRY_PROXMOX_TOKEN")

        Example:
            >>> backend = EnvSecretBackend({'prefix': 'APP_'})
            >>> backend._key_to_env('db/password')
            'APP_DB_PASSWORD'
        """
        # Replace slashes with underscores and convert to uppercase
        env_key = key.replace("/", "_").upper()
        return self.prefix + env_key

    def get_secret(self, key: str) -> str:
        """Retrieve a secret from environment variables.

        Args:
            key: Secret key (e.g., "proxmox/token")

        Returns:
            Secret value from environment variable

        Raises:
            SecretNotFoundError: If environment variable doesn't exist
            SecretBackendError: If retrieval fails for other reasons

        Example:
            >>> import os
            >>> os.environ['APP_DB_PASSWORD'] = 'secret123'
            >>> backend = EnvSecretBackend({'prefix': 'APP_'})
            >>> password = backend.get_secret('db/password')
            >>> print(password)
            'secret123'
        """
        try:
            env_var = self._key_to_env(key)

            if env_var not in os.environ:
                logger.debug(f"Secret not found: {key} (env var: {env_var})")
                raise SecretNotFoundError(
                    f"Secret '{key}' not found in environment (expected env var: {env_var})"
                )

            value = os.environ[env_var]
            logger.debug(f"Retrieved secret: {key} from {env_var}")
            return value

        except SecretNotFoundError:
            raise
        except Exception as e:
            raise SecretBackendError(f"Failed to retrieve secret '{key}': {e}") from e

    def list_secrets(self, prefix: str = "") -> list[str]:
        """List all secrets available in environment variables.

        This scans environment variables that start with the configured prefix
        and optionally match an additional filter prefix.

        Args:
            prefix: Optional prefix to filter secrets (e.g., "proxmox/")

        Returns:
            List of secret keys (converted back from env var names)

        Raises:
            SecretBackendError: If listing fails

        Example:
            >>> import os
            >>> os.environ['APP_DB_HOST'] = 'localhost'
            >>> os.environ['APP_DB_PASSWORD'] = 'secret'
            >>> os.environ['APP_API_TOKEN'] = 'token123'
            >>> backend = EnvSecretBackend({'prefix': 'APP_'})
            >>> secrets = backend.list_secrets('db/')
            >>> print(sorted(secrets))
            ['db/host', 'db/password']
        """
        try:
            secrets = []

            # Convert filter prefix to env var format
            env_prefix = self.prefix
            if prefix:
                env_prefix = self._key_to_env(prefix)

            # Scan environment variables
            for env_var in os.environ:
                if not env_var.startswith(self.prefix):
                    continue

                # Check if it matches the filter prefix
                if prefix and not env_var.startswith(env_prefix):
                    continue

                # Convert env var back to secret key format
                # Remove prefix and convert to lowercase with slashes
                key = env_var[len(self.prefix) :]
                key = key.lower().replace("_", "/")
                secrets.append(key)

            logger.debug(
                f"Listed {len(secrets)} secrets with prefix '{prefix}' (env prefix: {env_prefix})"
            )
            return sorted(secrets)

        except Exception as e:
            raise SecretBackendError(f"Failed to list secrets: {e}") from e

    def health_check(self) -> bool:
        """Check if backend is accessible.

        For the environment backend, this always returns True since
        environment variables are always accessible.

        Returns:
            True (always)

        Example:
            >>> backend = EnvSecretBackend({})
            >>> backend.health_check()
            True
        """
        return True


def register() -> "SecretBackendMetadata":
    """Register the environment variable secret backend.

    Returns:
        SecretBackendMetadata for the env backend

    Example:
        >>> metadata = register()
        >>> print(metadata.name)
        'env'
    """
    from infrafoundry.secrets.plugin_type import SecretBackendMetadata

    return SecretBackendMetadata(
        name="env",
        version="1.0.0",
        description="Read secrets from environment variables",
        backend_class=EnvSecretBackend,
        read_only=True,
        author="InfraFoundry Team",
        url="https://github.com/infrascloudy/infrafoundry",
    )
