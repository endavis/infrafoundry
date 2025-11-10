"""Credential loading and management for InfraFoundry.

This module provides a CredentialLoader class for loading environment-specific
credentials from encrypted secret files and managing environment variables.
"""

import logging
import os
import subprocess
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


class CredentialLoader:
    """Load and manage environment-specific credentials.

    Handles loading credentials from SOPS-encrypted files in the secrets/
    directory and updating environment variables. Supports per-environment
    encryption keys and automatic fallback to existing environment variables.

    Example:
        >>> loader = CredentialLoader(config_dir=Path("/path/to/config"))
        >>> credentials = loader.load("dev")
        >>> loader.apply_to_environment(credentials)
        # Now PROXMOX_API_URL, etc. are set in os.environ

        >>> # Or use context manager
        >>> with loader.temporary_credentials("dev") as creds:
        ...     # Credentials are set
        ...     pass
        # Credentials are restored
    """

    # Provider credential mapping
    PROVIDER_CREDENTIALS = {
        "proxmox": {
            "file": "proxmox.yaml",
            "fields": {
                "proxmox_api_url": "PROXMOX_API_URL",
                "proxmox_token_id": "PROXMOX_API_TOKEN_ID",
                "proxmox_token_secret": "PROXMOX_API_TOKEN_SECRET",
            },
        },
        "opnsense": {
            "file": "opnsense.yaml",
            "fields": {
                "opnsense_api_url": "OPNSENSE_API_URL",
                "opnsense_api_key": "OPNSENSE_API_KEY",
                "opnsense_api_secret": "OPNSENSE_API_SECRET",
            },
        },
        "kubernetes": {
            "file": "kubernetes.yaml",
            "fields": {
                "kubeconfig": "KUBECONFIG",
            },
        },
    }

    def __init__(self, config_dir: Path | None = None):
        """Initialize credential loader.

        Args:
            config_dir: Configuration directory (defaults to INFRAFOUNDRY_CONFIG_REPO or cwd)
        """
        if config_dir is None:
            config_repo = os.getenv("INFRAFOUNDRY_CONFIG_REPO")
            self.config_dir = Path(config_repo) if config_repo else Path.cwd()
        else:
            self.config_dir = Path(config_dir)

        self._debug_mode = os.getenv("INFRAFOUNDRY_LOG_LEVEL") == "DEBUG"

    def get_secrets_dir(self, env_name: str) -> Path:
        """Get the secrets directory for an environment.

        Args:
            env_name: Environment name (e.g., 'dev', 'staging', 'prod')

        Returns:
            Path to secrets/{env_name} directory
        """
        return self.config_dir / "secrets" / env_name

    def load(self, env_name: str, providers: list[str] | None = None) -> dict[str, str]:
        """Load environment-specific credentials from encrypted secrets.

        Args:
            env_name: Environment name (e.g., 'dev', 'staging', 'prod')
            providers: List of providers to load credentials for (default: all)

        Returns:
            Dictionary of environment variables (e.g., {'PROXMOX_API_URL': '...', ...})

        Example:
            >>> loader = CredentialLoader()
            >>> creds = loader.load("dev")
            >>> creds = loader.load("dev", providers=["proxmox"])  # Only Proxmox
        """
        secrets_dir = self.get_secrets_dir(env_name)

        if not secrets_dir.exists():
            if self._debug_mode:
                logger.debug(f"No secrets directory for environment: {env_name}")
            return {}

        # Set per-environment SOPS age key if it exists
        self._set_age_key(secrets_dir)

        # Determine which providers to load
        providers_to_load = providers or list(self.PROVIDER_CREDENTIALS.keys())

        env_vars = {}
        for provider in providers_to_load:
            if provider not in self.PROVIDER_CREDENTIALS:
                logger.warning(f"Unknown provider for credentials: {provider}")
                continue

            provider_vars = self._load_provider_credentials(provider, secrets_dir)
            env_vars.update(provider_vars)

        if self._debug_mode and env_vars:
            logger.debug(f"Loaded {len(env_vars)} credentials for environment: {env_name}")

        return env_vars

    def _set_age_key(self, secrets_dir: Path) -> None:
        """Set per-environment SOPS age key if it exists.

        Args:
            secrets_dir: Directory containing age.key file
        """
        env_age_key = secrets_dir / "age.key"
        if env_age_key.exists():
            os.environ["SOPS_AGE_KEY_FILE"] = str(env_age_key)
            if self._debug_mode:
                logger.debug(f"Using environment-specific age key: {env_age_key}")

    def _load_provider_credentials(self, provider: str, secrets_dir: Path) -> dict[str, str]:
        """Load credentials for a specific provider.

        Args:
            provider: Provider name (proxmox, opnsense, kubernetes)
            secrets_dir: Directory containing encrypted credential files

        Returns:
            Dictionary of environment variables for this provider
        """
        provider_config = self.PROVIDER_CREDENTIALS[provider]
        file_path = secrets_dir / provider_config["file"]

        if not file_path.exists():
            return {}

        try:
            decrypted_data = self._decrypt_sops_file(file_path)
            if not decrypted_data:
                return {}

            # Map credential fields to environment variables
            env_vars = {}
            for secret_key, env_var_name in provider_config["fields"].items():
                if value := decrypted_data.get(secret_key):
                    env_vars[env_var_name] = value

            if self._debug_mode and env_vars:
                logger.debug(f"Loaded {len(env_vars)} credentials for {provider}")

            return env_vars

        except Exception as e:
            if self._debug_mode:
                logger.debug(f"Failed to load {provider} credentials: {e}")
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
            if self._debug_mode:
                logger.debug(f"SOPS decryption failed for {file_path}: {e}")
            return {}
        except FileNotFoundError:
            if self._debug_mode:
                logger.debug("SOPS command not found")
            return {}
        except yaml.YAMLError as e:
            if self._debug_mode:
                logger.debug(f"YAML parsing failed for {file_path}: {e}")
            return {}

    def apply_to_environment(self, credentials: dict[str, str]) -> None:
        """Apply credentials to the current process environment.

        Args:
            credentials: Dictionary of environment variables to set
        """
        if credentials:
            os.environ.update(credentials)
            if self._debug_mode:
                logger.debug(f"Applied {len(credentials)} credentials to environment")

    def load_and_apply(self, env_name: str, providers: list[str] | None = None) -> dict[str, str]:
        """Load credentials and immediately apply them to the environment.

        Convenience method that combines load() and apply_to_environment().

        Args:
            env_name: Environment name (e.g., 'dev', 'staging', 'prod')
            providers: List of providers to load credentials for (default: all)

        Returns:
            Dictionary of environment variables that were set
        """
        credentials = self.load(env_name, providers)
        self.apply_to_environment(credentials)
        return credentials

    def temporary_credentials(self, env_name: str, providers: list[str] | None = None):
        """Context manager for temporary credential loading.

        Loads credentials, applies them, and restores original values on exit.

        Args:
            env_name: Environment name
            providers: List of providers to load credentials for (default: all)

        Yields:
            Dictionary of loaded credentials

        Example:
            >>> loader = CredentialLoader()
            >>> with loader.temporary_credentials("dev") as creds:
            ...     # Credentials are active
            ...     run_commands()
            # Original environment is restored
        """
        return _TemporaryCredentials(self, env_name, providers)

    def register_provider(
        self, provider_name: str, filename: str, field_mapping: dict[str, str]
    ) -> None:
        """Register a custom provider credential mapping.

        Allows extending CredentialLoader with custom providers at runtime.

        Args:
            provider_name: Name of the provider
            filename: YAML filename in secrets/{env}/ directory
            field_mapping: Dict mapping secret keys to env var names

        Example:
            >>> loader = CredentialLoader()
            >>> loader.register_provider(
            ...     "aws",
            ...     "aws.yaml",
            ...     {"access_key": "AWS_ACCESS_KEY_ID", "secret_key": "AWS_SECRET_ACCESS_KEY"}
            ... )
        """
        self.PROVIDER_CREDENTIALS[provider_name] = {
            "file": filename,
            "fields": field_mapping,
        }
        if self._debug_mode:
            logger.debug(f"Registered custom provider: {provider_name}")


class _TemporaryCredentials:
    """Context manager for temporary credential application."""

    def __init__(self, loader: CredentialLoader, env_name: str, providers: list[str] | None):
        self.loader = loader
        self.env_name = env_name
        self.providers = providers
        self.credentials: dict[str, str] = {}
        self.original_values: dict[str, str | None] = {}

    def __enter__(self) -> dict[str, str]:
        """Load and apply credentials, saving original values."""
        self.credentials = self.loader.load(self.env_name, self.providers)

        # Save original values
        for key in self.credentials:
            self.original_values[key] = os.environ.get(key)

        # Apply new credentials
        self.loader.apply_to_environment(self.credentials)

        return self.credentials

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Restore original environment values."""
        for key, original_value in self.original_values.items():
            if original_value is None:
                # Key didn't exist before, remove it
                os.environ.pop(key, None)
            else:
                # Restore original value
                os.environ[key] = original_value
