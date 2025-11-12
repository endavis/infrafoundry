"""Base service class for OPNsense operations."""

from abc import ABC
from pathlib import Path

from ..api_client import OPNsenseClient


class BaseService(ABC):
    """Base class for OPNsense service operations.

    Services provide low-level API operations for specific OPNsense components.
    They handle direct API communication and data transformation.
    """

    def __init__(self, client: OPNsenseClient):
        """Initialize service with API client.

        Args:
            client: Configured OPNsense API client
        """
        self.client = client

    @classmethod
    def from_environment(
        cls,
        env_name: str,
        provider_name: str,
        config_dir: Path,
    ) -> "BaseService":
        """Create service instance from environment configuration.

        Args:
            env_name: Environment name (e.g., 'prod', 'dev')
            provider_name: Provider name (e.g., 'opnsense')
            config_dir: Path to configuration directory

        Returns:
            Configured service instance

        Raises:
            ValueError: If provider settings not found
        """
        from infrafoundry.core.config import ConfigManager

        config_manager = ConfigManager(config_dir)
        env_config = config_manager.load_environment(env_name)
        provider_settings = env_config.get_provider_settings(provider_name)

        if not provider_settings:
            raise ValueError(
                f"No {provider_name} provider settings found for environment {env_name}"
            )

        client = OPNsenseClient(
            api_key=provider_settings.get("api_key", ""),
            api_secret=provider_settings.get("api_secret", ""),
            base_url=provider_settings.get("api_url", ""),
            verify_ssl=provider_settings.get("verify_ssl", True),
        )

        return cls(client)
