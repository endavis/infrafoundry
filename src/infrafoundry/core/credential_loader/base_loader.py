"""Base credential loader for provider-specific implementations."""

import logging
import traceback
from abc import ABC, abstractmethod
from pathlib import Path

from infrafoundry.core.exceptions import (
    CredentialError,
    SecretError,
    SecretNotFoundError,
)
from infrafoundry.core.secrets.provider import SecretProvider
from infrafoundry.core.secrets.providers.sops import SopsSecretProvider

logger = logging.getLogger(__name__)


class CredentialLoaderError(CredentialError):
    """Raised when provider credentials cannot be loaded."""


class BaseCredentialLoader(ABC):
    """Abstract base class for provider-specific credential loaders."""

    def __init__(
        self,
        secrets_dir: Path,
        debug_mode: bool = False,
        secret_provider: SecretProvider | None = None,
    ) -> None:
        """Initialize credential loader.

        Args:
            secrets_dir: Directory containing encrypted credential files
            debug_mode: Enable debug logging
            secret_provider: Secret provider implementation (defaults to SopsSecretProvider)
        """
        self.secrets_dir = secrets_dir
        self.debug_mode = debug_mode
        self.secret_provider = secret_provider or SopsSecretProvider()

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the provider name (e.g., 'proxmox', 'opnsense')."""
        pass

    @property
    @abstractmethod
    def credential_file(self) -> str:
        """Return the credential filename (e.g., 'proxmox.yaml')."""
        pass

    @property
    @abstractmethod
    def field_mapping(self) -> dict[str, str]:
        """Return mapping of secret keys to environment variable names.

        Example:
            {
                "proxmox_api_url": "PROXMOX_API_URL",
                "proxmox_token_id": "PROXMOX_API_TOKEN_ID",
            }
        """
        pass

    def load_credentials(self) -> dict[str, str]:
        """Load and map credentials for this provider.

        Returns:
            Dictionary of environment variables (e.g., {'PROXMOX_API_URL': '...'})
        """
        file_path = self.secrets_dir / self.credential_file

        # Check if file exists using Path.exists() first to avoid overhead if missing
        # But provider.load_secret should also handle it.
        # However, existing logic checks existence first.
        if not file_path.exists():
            if self.debug_mode:
                logger.debug(f"Credential file not found: {file_path}")
            return {}

        try:
            decrypted_data = self.secret_provider.load_secret(file_path)
        except SecretNotFoundError:
            if self.debug_mode:
                logger.debug(f"Credential file not found (via provider): {file_path}")
            return {}
        except SecretError as exc:
            if self.debug_mode:
                logger.debug(f"Secret loading failed for {file_path}: {exc}")
            # We re-raise as CredentialLoaderError to maintain contract
            raise CredentialLoaderError(f"Failed to load secret from {file_path}: {exc}") from exc
        except Exception as exc:  # pragma: no cover - defensive
            logger.error(f"Unexpected error reading {file_path}: {exc}")
            logger.debug(traceback.format_exc())
            raise CredentialLoaderError(f"Unexpected error reading {file_path}: {exc}") from exc

        if not decrypted_data:
            return {}

        env_vars = {}
        for secret_key, env_var_name in self.field_mapping.items():
            if value := decrypted_data.get(secret_key):
                env_vars[env_var_name] = value

        if self.debug_mode and env_vars:
            logger.debug(f"Loaded {len(env_vars)} credentials for {self.provider_name}")

        return env_vars
