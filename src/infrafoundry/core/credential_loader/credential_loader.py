"""Refactored credential loader - factory pattern for provider-specific loaders."""

import logging
import os
from pathlib import Path

from infrafoundry.core.credential_loader.base_loader import BaseCredentialLoader
from infrafoundry.core.credential_loader.kubernetes_loader import KubernetesCredentialLoader
from infrafoundry.core.credential_loader.opnsense_loader import OPNsenseCredentialLoader
from infrafoundry.core.credential_loader.proxmox_loader import ProxmoxCredentialLoader

logger = logging.getLogger(__name__)


class CredentialLoader:
    """Load and manage environment-specific credentials using provider-specific loaders.

    Uses factory pattern to instantiate appropriate credential loaders for each provider.
    Handles loading credentials from SOPS-encrypted files and managing environment variables.

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

    # Registry of available provider loaders
    PROVIDER_LOADERS = {
        "proxmox": ProxmoxCredentialLoader,
        "opnsense": OPNsenseCredentialLoader,
        "kubernetes": KubernetesCredentialLoader,
    }

    # Legacy attribute for backward compatibility with tests
    @property
    def provider_credentials(self) -> dict:
        """Return provider credentials in old format for backward compatibility."""
        result = {}
        for name, loader_class in self.PROVIDER_LOADERS.items():
            # Create a temporary instance to get properties
            temp_secrets_dir = Path("/tmp")
            loader = loader_class(temp_secrets_dir, False)
            result[name] = {
                "file": loader.credential_file,
                "fields": loader.field_mapping,
            }
        return result

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
        """Get the environment directory containing secrets.

        Args:
            env_name: Environment name (e.g., 'dev', 'staging', 'prod')

        Returns:
            Path to envs/{env_name} directory (where settings.yaml and age.key live)
        """
        return self.config_dir / "envs" / env_name

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
        providers_to_load = providers or list(self.PROVIDER_LOADERS.keys())

        env_vars = {}
        for provider in providers_to_load:
            if provider not in self.PROVIDER_LOADERS:
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
        """Load credentials for a specific provider using factory pattern.

        Args:
            provider: Provider name (proxmox, opnsense, kubernetes)
            secrets_dir: Directory containing encrypted credential files

        Returns:
            Dictionary of environment variables for this provider
        """
        loader_class = self.PROVIDER_LOADERS[provider]
        loader = loader_class(secrets_dir, self._debug_mode)
        return loader.load_credentials()

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
        self,
        provider_name: str,
        loader_class_or_filename: type[BaseCredentialLoader] | str,
        field_mapping: dict[str, str] | None = None,
    ) -> None:
        """Register a custom provider credential loader.

        Allows extending CredentialLoader with custom providers at runtime.
        Supports both new (loader class) and old (filename + mapping) APIs for
        backward compatibility.

        Args:
            provider_name: Name of the provider
            loader_class_or_filename: Either a BaseCredentialLoader subclass or filename (old API)
            field_mapping: Field mapping dict (only for old API with filename)

        Example (new API):
            >>> class AWSCredentialLoader(BaseCredentialLoader):
            ...     @property
            ...     def provider_name(self) -> str:
            ...         return "aws"
            ...     # ... implement other methods
            >>>
            >>> loader = CredentialLoader()
            >>> loader.register_provider("aws", AWSCredentialLoader)

        Example (old API - backward compatible):
            >>> loader.register_provider(
            ...     "aws",
            ...     "aws.yaml",
            ...     {"access_key": "AWS_ACCESS_KEY_ID"}
            ... )
        """
        # Handle old API (filename + field_mapping)
        if isinstance(loader_class_or_filename, str) and field_mapping is not None:
            # Create dynamic loader class for backward compatibility
            filename = loader_class_or_filename

            class DynamicLoader(BaseCredentialLoader):
                @property
                def provider_name(self) -> str:
                    return provider_name

                @property
                def credential_file(self) -> str:
                    return filename

                @property
                def field_mapping(self) -> dict[str, str]:
                    return field_mapping

            self.PROVIDER_LOADERS[provider_name] = DynamicLoader
        else:
            # New API (loader class)
            self.PROVIDER_LOADERS[provider_name] = loader_class_or_filename

        if self._debug_mode:
            logger.debug(f"Registered custom provider loader: {provider_name}")


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
