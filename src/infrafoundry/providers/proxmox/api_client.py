"""Proxmox VE API client with PVE token authentication."""

from __future__ import annotations

import json
import logging
from typing import Any

import requests
import urllib3

from infrafoundry.core.exceptions import APIError, AuthenticationError
from infrafoundry.core.types import ProxmoxProviderSettings

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)


class ProxmoxClient:
    """Thin wrapper around requests with Proxmox PVE token authentication.

    Handles URL construction, authentication headers, and error conversion
    following the same pattern as OPNsenseClient.
    """

    def __init__(
        self,
        api_url: str,
        api_token: str,
        verify_ssl: bool = False,
        timeout: int = 10,
    ) -> None:
        """Initialize Proxmox API client.

        Args:
            api_url: Proxmox API base URL (e.g. https://pve.example.com:8006/api2/json)
            api_token: Full PVE API token (USER@REALM!TOKENID=SECRET)
            verify_ssl: Whether to verify SSL certificates
            timeout: Request timeout in seconds
        """
        self.api_url = api_url
        self.headers = {"Authorization": f"PVEAPIToken={api_token}"}
        self.verify_ssl = verify_ssl
        self.timeout = timeout

    @classmethod
    def from_provider_settings(cls, settings: ProxmoxProviderSettings) -> ProxmoxClient | None:
        """Create a client from provider settings.

        Supports two token formats:
        - api_token: Full token string
        - api_token_id + api_token_secret: Terraform provider format

        Args:
            settings: Proxmox provider settings dictionary

        Returns:
            ProxmoxClient instance, or None if credentials are insufficient
        """
        api_url = settings.get("api_url")
        if not api_url:
            return None

        api_token = settings.get("api_token")
        if not api_token:
            token_id = settings.get("api_token_id")
            token_secret = settings.get("api_token_secret")
            if token_id and token_secret:
                api_token = f"{token_id}={token_secret}"

        if not api_token:
            return None

        return cls(api_url=api_url, api_token=api_token)

    def get_json(self, endpoint: str, **kwargs: Any) -> dict[str, Any]:
        """Make an authenticated GET request and return parsed JSON.

        Args:
            endpoint: API endpoint path (appended to base URL)
            **kwargs: Additional arguments passed to requests.get

        Returns:
            Parsed JSON response as a dictionary

        Raises:
            AuthenticationError: On 401/403 responses
            APIError: On other HTTP errors, connection errors, or JSON parse failures
        """
        url = f"{self.api_url}/{endpoint}"
        try:
            response = requests.get(
                url,
                headers=self.headers,
                verify=self.verify_ssl,
                timeout=self.timeout,
                **kwargs,
            )
        except requests.exceptions.ConnectionError as e:
            raise APIError(
                f"Proxmox API connection failed: {e}",
                provider="proxmox",
            ) from e
        except requests.exceptions.Timeout as e:
            raise APIError(
                f"Proxmox API request timed out: {e}",
                provider="proxmox",
            ) from e
        except requests.exceptions.RequestException as e:
            raise APIError(
                f"Proxmox API request failed: {e}",
                provider="proxmox",
            ) from e

        if response.status_code in (401, 403):
            raise AuthenticationError(
                "Proxmox authentication failed",
                status_code=response.status_code,
                response=response.text,
                provider="proxmox",
            )

        if not response.ok:
            raise APIError(
                f"Proxmox API request failed: {response.status_code}",
                status_code=response.status_code,
                response=response.text,
                provider="proxmox",
            )

        try:
            return dict(response.json())
        except (json.JSONDecodeError, ValueError) as e:
            raise APIError(
                "Invalid JSON response from Proxmox",
                response=str(e),
                provider="proxmox",
            ) from e

    @property
    def base_url(self) -> str:
        """Return the API base URL."""
        return self.api_url
