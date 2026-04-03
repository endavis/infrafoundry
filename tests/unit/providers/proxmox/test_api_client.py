"""Unit tests for Proxmox API client."""

from unittest.mock import MagicMock, patch

import pytest
import requests

from infrafoundry.core.exceptions import APIError, AuthenticationError
from infrafoundry.providers.proxmox.api_client import ProxmoxClient


@pytest.fixture
def client():
    """Create a ProxmoxClient instance."""
    return ProxmoxClient(
        api_url="https://proxmox.example.com:8006/api2/json",
        api_token="user@pam!token=secret-value",
    )


class TestGetJson:
    """Tests for ProxmoxClient.get_json."""

    @patch("infrafoundry.providers.proxmox.api_client.requests.get")
    def test_success(self, mock_get, client):
        """Successful GET returns parsed JSON dict."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {"version": "8.1"}}
        mock_get.return_value = mock_response

        result = client.get_json("version")

        assert result == {"data": {"version": "8.1"}}
        mock_get.assert_called_once_with(
            "https://proxmox.example.com:8006/api2/json/version",
            headers={"Authorization": "PVEAPIToken=user@pam!token=secret-value"},
            verify=False,
            timeout=10,
        )

    @patch("infrafoundry.providers.proxmox.api_client.requests.get")
    def test_http_401_raises_authentication_error(self, mock_get, client):
        """HTTP 401 raises AuthenticationError."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.ok = False
        mock_response.text = "Unauthorized"
        mock_get.return_value = mock_response

        with pytest.raises(AuthenticationError) as exc_info:
            client.get_json("version")

        assert exc_info.value.status_code == 401
        assert exc_info.value.provider == "proxmox"

    @patch("infrafoundry.providers.proxmox.api_client.requests.get")
    def test_http_403_raises_authentication_error(self, mock_get, client):
        """HTTP 403 raises AuthenticationError."""
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.ok = False
        mock_response.text = "Forbidden"
        mock_get.return_value = mock_response

        with pytest.raises(AuthenticationError):
            client.get_json("version")

    @patch("infrafoundry.providers.proxmox.api_client.requests.get")
    def test_http_500_raises_api_error(self, mock_get, client):
        """HTTP 500 raises APIError with status code."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.ok = False
        mock_response.text = "Internal Server Error"
        mock_get.return_value = mock_response

        with pytest.raises(APIError) as exc_info:
            client.get_json("version")

        assert exc_info.value.status_code == 500
        assert exc_info.value.provider == "proxmox"

    @patch("infrafoundry.providers.proxmox.api_client.requests.get")
    def test_connection_error_raises_api_error(self, mock_get, client):
        """Connection error raises APIError."""
        mock_get.side_effect = requests.exceptions.ConnectionError("Connection refused")

        with pytest.raises(APIError) as exc_info:
            client.get_json("version")

        assert "connection failed" in exc_info.value.message.lower()

    @patch("infrafoundry.providers.proxmox.api_client.requests.get")
    def test_timeout_raises_api_error(self, mock_get, client):
        """Timeout raises APIError."""
        mock_get.side_effect = requests.exceptions.Timeout("Request timed out")

        with pytest.raises(APIError) as exc_info:
            client.get_json("version")

        assert "timed out" in exc_info.value.message.lower()

    @patch("infrafoundry.providers.proxmox.api_client.requests.get")
    def test_invalid_json_raises_api_error(self, mock_get, client):
        """Invalid JSON response raises APIError."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_get.return_value = mock_response

        with pytest.raises(APIError) as exc_info:
            client.get_json("version")

        assert "Invalid JSON" in exc_info.value.message

    @patch("infrafoundry.providers.proxmox.api_client.requests.get")
    def test_passes_extra_kwargs(self, mock_get, client):
        """Extra kwargs are passed through to requests.get."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": []}
        mock_get.return_value = mock_response

        client.get_json("cluster/resources", params={"type": "vm"})

        _, kwargs = mock_get.call_args
        assert kwargs["params"] == {"type": "vm"}


class TestFromProviderSettings:
    """Tests for ProxmoxClient.from_provider_settings."""

    def test_with_api_token(self):
        """Creates client from api_token setting."""
        settings = {
            "api_url": "https://pve.example.com:8006/api2/json",
            "api_token": "user@pam!token=secret",
            "node": "pve1",
        }

        client = ProxmoxClient.from_provider_settings(settings)

        assert client is not None
        assert client.base_url == "https://pve.example.com:8006/api2/json"
        assert client.headers["Authorization"] == "PVEAPIToken=user@pam!token=secret"

    def test_with_token_id_and_secret(self):
        """Creates client from api_token_id + api_token_secret."""
        settings = {
            "api_url": "https://pve.example.com:8006/api2/json",
            "api_token_id": "user@pam!mytoken",
            "api_token_secret": "12345-abcde",
            "node": "pve1",
        }

        client = ProxmoxClient.from_provider_settings(settings)

        assert client is not None
        assert client.headers["Authorization"] == "PVEAPIToken=user@pam!mytoken=12345-abcde"

    def test_no_token_returns_none(self):
        """Returns None when no token is available."""
        settings = {
            "api_url": "https://pve.example.com:8006/api2/json",
            "node": "pve1",
        }

        client = ProxmoxClient.from_provider_settings(settings)

        assert client is None

    def test_no_api_url_returns_none(self):
        """Returns None when api_url is missing."""
        settings = {
            "api_token": "user@pam!token=secret",
            "node": "pve1",
        }

        client = ProxmoxClient.from_provider_settings(settings)

        assert client is None


class TestBaseUrl:
    """Tests for the base_url property."""

    def test_returns_api_url(self, client):
        """base_url property returns the API URL."""
        assert client.base_url == "https://proxmox.example.com:8006/api2/json"
