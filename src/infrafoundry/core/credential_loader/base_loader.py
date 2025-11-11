"""Base credential loader for provider-specific implementations."""

import logging
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


class BaseCredentialLoader(ABC):
    """Abstract base class for provider-specific credential loaders."""

    def __init__(self, secrets_dir: Path, debug_mode: bool = False):
        """Initialize credential loader.

        Args:
            secrets_dir: Directory containing encrypted credential files
            debug_mode: Enable debug logging
        """
        self.secrets_dir = secrets_dir
        self.debug_mode = debug_mode

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

        if not file_path.exists():
            if self.debug_mode:
                logger.debug(f"Credential file not found: {file_path}")
            return {}

        try:
            decrypted_data = self._decrypt_sops_file(file_path)
            if not decrypted_data:
                return {}

            # Map credential fields to environment variables
            env_vars = {}
            for secret_key, env_var_name in self.field_mapping.items():
                if value := decrypted_data.get(secret_key):
                    env_vars[env_var_name] = value

            if self.debug_mode and env_vars:
                logger.debug(f"Loaded {len(env_vars)} credentials for {self.provider_name}")

            return env_vars

        except Exception as e:
            if self.debug_mode:
                logger.debug(f"Failed to load {self.provider_name} credentials: {e}")
            return {}

    def _decrypt_sops_file(self, file_path: Path) -> dict[str, Any]:
        """Decrypt a SOPS-encrypted YAML file.

        Args:
            file_path: Path to encrypted file

        Returns:
            Decrypted data as dictionary (empty dict if decryption fails)
        """
        try:
            result = subprocess.run(
                ["sops", "--decrypt", str(file_path)],
                capture_output=True,
                text=True,
                check=True,
            )
            return yaml.safe_load(result.stdout) or {}
        except subprocess.CalledProcessError as e:
            if self.debug_mode:
                logger.debug(f"SOPS decryption failed for {file_path}: {e}")
            return {}
        except FileNotFoundError:
            if self.debug_mode:
                logger.debug("SOPS command not found")
            return {}
        except yaml.YAMLError as e:
            if self.debug_mode:
                logger.debug(f"YAML parsing failed for {file_path}: {e}")
            return {}
