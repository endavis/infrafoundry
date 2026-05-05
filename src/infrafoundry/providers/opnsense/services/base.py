"""Base service class for OPNsense operations."""

from abc import ABC
from pathlib import Path
from typing import Self

from ..api_client import OPNsenseClient
from ._credentials import resolve_credentials


class BaseService(ABC):  # noqa: B024
    """Base class for OPNsense service operations.

    Services provide low-level API operations for specific OPNsense components.
    They handle direct API communication and data transformation.
    """

    def __init__(self, client: OPNsenseClient) -> None:
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
    ) -> Self:
        """Create service instance from environment configuration.

        Resolves credentials via ``resolve_credentials`` so that, when
        ``INFRAFOUNDRY_ALLOW_ENV_OVERRIDE=1`` is set, ``OPNSENSE_API_URL``
        / ``OPNSENSE_API_KEY`` / ``OPNSENSE_API_SECRET`` /
        ``OPNSENSE_VERIFY_SSL`` env vars take precedence over
        ``settings.yaml``. See
        ``infrafoundry.providers.opnsense.services._credentials`` and
        ADR-0014 §"Secrets handling" → "Runtime credential resolution".

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

        api_url, api_key, api_secret, verify_ssl = resolve_credentials(provider_settings)
        client = OPNsenseClient(
            api_key=api_key,
            api_secret=api_secret,
            base_url=api_url,
            verify_ssl=verify_ssl,
        )

        return cls(client)
