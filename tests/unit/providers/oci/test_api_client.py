"""Unit tests for OCI API client."""

from unittest.mock import MagicMock, patch

import pytest
import requests

from infrafoundry.core.exceptions import APIError, ConfigurationError
from infrafoundry.providers.oci.api_client import OCIClient


@pytest.fixture
def rsa_key_path(tmp_path):
    """Create a temporary RSA private key file."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    key_path = tmp_path / "test_key.pem"
    key_path.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    return str(key_path)


@pytest.fixture
def client(rsa_key_path):
    """Create an OCIClient instance with a valid test key."""
    return OCIClient(
        tenancy_ocid="ocid1.tenancy.oc1..example",
        user_ocid="ocid1.user.oc1..example",
        private_key_path=rsa_key_path,
        fingerprint="aa:bb:cc:dd:ee:ff:00:11",
        region="us-ashburn-1",
    )


class TestInit:
    """Tests for OCIClient initialization."""

    def test_loads_rsa_key(self, rsa_key_path):
        """Successfully loads a valid RSA key."""
        client = OCIClient(
            tenancy_ocid="t",
            user_ocid="u",
            private_key_path=rsa_key_path,
            fingerprint="f",
            region="us-ashburn-1",
        )
        assert client._private_key is not None

    def test_missing_key_file_raises(self):
        """Raises ConfigurationError when key file doesn't exist."""
        with pytest.raises(ConfigurationError, match="not found"):
            OCIClient(
                tenancy_ocid="t",
                user_ocid="u",
                private_key_path="/nonexistent/key.pem",
                fingerprint="f",
                region="us-ashburn-1",
            )

    def test_non_rsa_key_raises(self, tmp_path):
        """Raises ConfigurationError for non-RSA key."""
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ec

        # Generate an EC key (not RSA)
        ec_key = ec.generate_private_key(ec.SECP256R1())
        key_path = tmp_path / "ec_key.pem"
        key_path.write_bytes(
            ec_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )

        with pytest.raises(ConfigurationError, match="RSA"):
            OCIClient(
                tenancy_ocid="t",
                user_ocid="u",
                private_key_path=str(key_path),
                fingerprint="f",
                region="us-ashburn-1",
            )

    def test_invalid_key_data_raises(self, tmp_path):
        """Raises ConfigurationError for invalid key data."""
        key_path = tmp_path / "bad_key.pem"
        key_path.write_text("not a real key")

        with pytest.raises(ConfigurationError, match="Failed to load"):
            OCIClient(
                tenancy_ocid="t",
                user_ocid="u",
                private_key_path=str(key_path),
                fingerprint="f",
                region="us-ashburn-1",
            )


class TestBuildSignedHeaders:
    """Tests for _build_signed_headers."""

    def test_produces_valid_authorization_header(self, client):
        """Signed headers contain valid Authorization format."""
        headers = client._build_signed_headers(
            "get",
            "https://identity.us-ashburn-1.oraclecloud.com/20160918/availabilityDomains",
        )

        assert "Authorization" in headers
        assert "date" in headers
        assert "host" in headers
        assert 'Signature version="1"' in headers["Authorization"]
        assert 'algorithm="rsa-sha256"' in headers["Authorization"]
        assert "ocid1.tenancy.oc1..example" in headers["Authorization"]

    def test_includes_body_headers_for_post(self, client):
        """POST requests include content headers in signature."""
        headers = client._build_signed_headers(
            "post",
            "https://iaas.us-ashburn-1.oraclecloud.com/20160918/vcns",
            body='{"displayName": "test"}',
        )

        assert "x-content-sha256" in headers["Authorization"]
        assert "content-type" in headers["Authorization"]


class TestListResources:
    """Tests for list_resources."""

    @patch("infrafoundry.providers.oci.api_client.requests.get")
    def test_success(self, mock_get, client):
        """Successful list returns parsed JSON array."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = [
            {"id": "ocid1.vcn.oc1..aaa", "displayName": "my-vcn"},
        ]
        mock_get.return_value = mock_response

        result = client.list_resources(
            "https://iaas.us-ashburn-1.oraclecloud.com",
            "/20160918/vcns?compartmentId=test",
        )

        assert result == [{"id": "ocid1.vcn.oc1..aaa", "displayName": "my-vcn"}]

    @patch("infrafoundry.providers.oci.api_client.requests.get")
    def test_http_error_raises_api_error(self, mock_get, client):
        """HTTP error raises APIError."""
        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_get.return_value = mock_response

        with pytest.raises(APIError) as exc_info:
            client.list_resources(
                "https://iaas.us-ashburn-1.oraclecloud.com",
                "/20160918/vcns?compartmentId=test",
            )

        assert exc_info.value.status_code == 500

    @patch("infrafoundry.providers.oci.api_client.requests.get")
    def test_connection_error_raises_api_error(self, mock_get, client):
        """Connection error raises APIError."""
        mock_get.side_effect = requests.exceptions.ConnectionError("refused")

        with pytest.raises(APIError):
            client.list_resources(
                "https://iaas.us-ashburn-1.oraclecloud.com",
                "/20160918/vcns?compartmentId=test",
            )

    @patch("infrafoundry.providers.oci.api_client.requests.get")
    def test_non_list_response_raises_api_error(self, mock_get, client):
        """Non-list JSON response raises APIError."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = {"error": "unexpected"}
        mock_get.return_value = mock_response

        with pytest.raises(APIError, match="unexpected format"):
            client.list_resources(
                "https://iaas.us-ashburn-1.oraclecloud.com",
                "/20160918/vcns?compartmentId=test",
            )

    @patch("infrafoundry.providers.oci.api_client.requests.get")
    def test_invalid_json_raises_api_error(self, mock_get, client):
        """Invalid JSON raises APIError."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.side_effect = ValueError("bad json")
        mock_get.return_value = mock_response

        with pytest.raises(APIError, match="Invalid JSON"):
            client.list_resources(
                "https://iaas.us-ashburn-1.oraclecloud.com",
                "/20160918/vcns?compartmentId=test",
            )


class TestFromProviderSettings:
    """Tests for from_provider_settings."""

    def test_extracts_fields(self, rsa_key_path):
        """Creates client with correct fields from settings."""
        settings = {
            "tenancy_ocid": "ocid1.tenancy.oc1..test",
            "user_ocid": "ocid1.user.oc1..test",
            "private_key_path": rsa_key_path,
            "fingerprint": "aa:bb:cc",
            "region": "us-phoenix-1",
        }

        client = OCIClient.from_provider_settings(settings)

        assert client.tenancy_ocid == "ocid1.tenancy.oc1..test"
        assert client.region == "us-phoenix-1"

    def test_missing_key_raises(self):
        """Raises ConfigurationError when key path is invalid."""
        settings = {
            "tenancy_ocid": "t",
            "user_ocid": "u",
            "private_key_path": "/nonexistent",
            "fingerprint": "f",
            "region": "r",
        }

        with pytest.raises(ConfigurationError):
            OCIClient.from_provider_settings(settings)


class TestUrlHelpers:
    """Tests for URL helper methods."""

    def test_identity_url(self, client):
        """identity_url returns correct URL."""
        assert client.identity_url() == "https://identity.us-ashburn-1.oraclecloud.com"

    def test_iaas_url(self, client):
        """iaas_url returns correct URL."""
        assert client.iaas_url() == "https://iaas.us-ashburn-1.oraclecloud.com"
