"""Unit tests for Proxmox API client."""

from unittest.mock import MagicMock, patch

import pytest
import requests

from infrafoundry.core.exceptions import APIError, AuthenticationError
from infrafoundry.core.types import ProxmoxProviderSettings
from infrafoundry.providers.proxmox.api_client import ProxmoxClient


@pytest.fixture
def client() -> ProxmoxClient:
    """Create a ProxmoxClient instance."""
    return ProxmoxClient(
        api_url="https://proxmox.example.com:8006/api2/json",
        api_token="user@pam!token=secret-value",
    )


class TestGetJson:
    """Tests for ProxmoxClient.get_json."""

    @patch("infrafoundry.providers.proxmox.api_client.requests.get")
    def test_success(self, mock_get: MagicMock, client: ProxmoxClient) -> None:
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
    def test_http_401_raises_authentication_error(
        self, mock_get: MagicMock, client: ProxmoxClient
    ) -> None:
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
    def test_http_403_raises_authentication_error(
        self, mock_get: MagicMock, client: ProxmoxClient
    ) -> None:
        """HTTP 403 raises AuthenticationError."""
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.ok = False
        mock_response.text = "Forbidden"
        mock_get.return_value = mock_response

        with pytest.raises(AuthenticationError):
            client.get_json("version")

    @patch("infrafoundry.providers.proxmox.api_client.requests.get")
    def test_http_500_raises_api_error(self, mock_get: MagicMock, client: ProxmoxClient) -> None:
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
    def test_connection_error_raises_api_error(
        self, mock_get: MagicMock, client: ProxmoxClient
    ) -> None:
        """Connection error raises APIError."""
        mock_get.side_effect = requests.exceptions.ConnectionError("Connection refused")

        with pytest.raises(APIError) as exc_info:
            client.get_json("version")

        assert "connection failed" in exc_info.value.message.lower()

    @patch("infrafoundry.providers.proxmox.api_client.requests.get")
    def test_timeout_raises_api_error(self, mock_get: MagicMock, client: ProxmoxClient) -> None:
        """Timeout raises APIError."""
        mock_get.side_effect = requests.exceptions.Timeout("Request timed out")

        with pytest.raises(APIError) as exc_info:
            client.get_json("version")

        assert "timed out" in exc_info.value.message.lower()

    @patch("infrafoundry.providers.proxmox.api_client.requests.get")
    def test_invalid_json_raises_api_error(
        self, mock_get: MagicMock, client: ProxmoxClient
    ) -> None:
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
    def test_passes_extra_kwargs(self, mock_get: MagicMock, client: ProxmoxClient) -> None:
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

    def test_with_api_token(self) -> None:
        """Creates client from api_token setting."""
        settings: ProxmoxProviderSettings = {
            "api_url": "https://pve.example.com:8006/api2/json",
            "api_token": "user@pam!token=secret",
            "node": "node1",
        }

        client = ProxmoxClient.from_provider_settings(settings)

        assert client is not None
        assert client.base_url == "https://pve.example.com:8006/api2/json"
        assert client.headers["Authorization"] == "PVEAPIToken=user@pam!token=secret"

    def test_with_token_id_and_secret(self) -> None:
        """Creates client from api_token_id + api_token_secret."""
        settings: ProxmoxProviderSettings = {
            "api_url": "https://pve.example.com:8006/api2/json",
            "api_token_id": "user@pam!mytoken",
            "api_token_secret": "12345-abcde",
            "node": "node1",
        }

        client = ProxmoxClient.from_provider_settings(settings)

        assert client is not None
        assert client.headers["Authorization"] == "PVEAPIToken=user@pam!mytoken=12345-abcde"

    def test_no_token_returns_none(self) -> None:
        """Returns None when no token is available."""
        settings: ProxmoxProviderSettings = {
            "api_url": "https://pve.example.com:8006/api2/json",
            "node": "node1",
        }

        client = ProxmoxClient.from_provider_settings(settings)

        assert client is None

    def test_no_api_url_returns_none(self) -> None:
        """Returns None when api_url is missing."""
        settings: ProxmoxProviderSettings = {
            "api_token": "user@pam!token=secret",
            "node": "node1",
        }

        client = ProxmoxClient.from_provider_settings(settings)

        assert client is None


class TestBaseUrl:
    """Tests for the base_url property."""

    def test_returns_api_url(self, client: ProxmoxClient) -> None:
        """base_url property returns the API URL."""
        assert client.base_url == "https://proxmox.example.com:8006/api2/json"


class TestPostJson:
    """Tests for ProxmoxClient.post_json."""

    @patch("infrafoundry.providers.proxmox.api_client.requests.post")
    def test_success_sends_a_form_body(self, mock_post: MagicMock, client: ProxmoxClient) -> None:
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": None}
        mock_post.return_value = mock_response

        result = client.post_json("nodes/pve1/certificates/custom", {"key": "k"})

        assert result == {"data": None}
        mock_post.assert_called_once_with(
            "https://proxmox.example.com:8006/api2/json/nodes/pve1/certificates/custom",
            headers={"Authorization": "PVEAPIToken=user@pam!token=secret-value"},
            data={"key": "k"},
            verify=False,
            timeout=10,
        )

    @pytest.mark.parametrize("status", [401, 403])
    @patch("infrafoundry.providers.proxmox.api_client.requests.post")
    def test_auth_failures(self, mock_post: MagicMock, client: ProxmoxClient, status: int) -> None:
        mock_post.return_value = MagicMock(ok=False, status_code=status, text="SECRET-BODY")
        with pytest.raises(AuthenticationError) as exc_info:
            client.post_json("x", {})
        assert exc_info.value.context["status_code"] == status
        assert "SECRET-BODY" not in str(exc_info.value)

    @patch("infrafoundry.providers.proxmox.api_client.requests.post")
    def test_http_error_does_not_leak_the_response(
        self, mock_post: MagicMock, client: ProxmoxClient
    ) -> None:
        mock_post.return_value = MagicMock(ok=False, status_code=500, text="SECRET-BODY")
        with pytest.raises(APIError) as exc_info:
            client.post_json("x", {})
        assert exc_info.value.context["status_code"] == 500
        assert "SECRET-BODY" not in str(exc_info.value)

    @patch("infrafoundry.providers.proxmox.api_client.requests.post")
    def test_connection_error(self, mock_post: MagicMock, client: ProxmoxClient) -> None:
        mock_post.side_effect = requests.exceptions.ConnectionError("SECRET-URL")
        with pytest.raises(APIError, match="request failed") as exc_info:
            client.post_json("x", {})
        assert "SECRET-URL" not in str(exc_info.value)

    @patch("infrafoundry.providers.proxmox.api_client.requests.post")
    def test_invalid_json(self, mock_post: MagicMock, client: ProxmoxClient) -> None:
        response = MagicMock(ok=True, status_code=200)
        response.json.side_effect = ValueError("bad")
        mock_post.return_value = response
        with pytest.raises(APIError, match="Invalid JSON"):
            client.post_json("x", {})
