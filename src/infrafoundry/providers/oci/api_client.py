"""OCI API client with RSA-SHA256 HTTP Signature authentication."""

from __future__ import annotations

import base64
import email.utils
import hashlib
import json
import logging
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

from infrafoundry.core.exceptions import APIError, ConfigurationError
from infrafoundry.core.types import OCIProviderSettings

logger = logging.getLogger(__name__)


class OCIClient:
    """OCI API client with RSA-SHA256 HTTP Signature authentication.

    Loads the RSA private key once at construction time and generates
    per-request signatures. Follows the same pattern as OPNsenseClient
    for error handling (raises APIError/ConfigurationError).
    """

    IDENTITY_API_BASE = "https://identity.{region}.oraclecloud.com"
    OCI_API_BASE = "https://iaas.{region}.oraclecloud.com"

    def __init__(
        self,
        tenancy_ocid: str,
        user_ocid: str,
        private_key_path: str,
        fingerprint: str,
        region: str,
        timeout: int = 10,
    ) -> None:
        """Initialize OCI API client.

        Loads the RSA private key eagerly so signing never fails after construction.

        Args:
            tenancy_ocid: OCI tenancy OCID
            user_ocid: OCI user OCID
            private_key_path: Path to RSA private key PEM file
            fingerprint: RSA key fingerprint
            region: OCI region (e.g. us-ashburn-1)
            timeout: Request timeout in seconds

        Raises:
            ConfigurationError: If key file is missing, cryptography package
                unavailable, or key is not a valid RSA key
        """
        self.tenancy_ocid = tenancy_ocid
        self.user_ocid = user_ocid
        self.fingerprint = fingerprint
        self.region = region
        self.timeout = timeout

        # Load private key eagerly
        key_path = Path(private_key_path).expanduser()
        if not key_path.exists():
            raise ConfigurationError(f"OCI private key not found: {key_path}")

        try:
            from cryptography.hazmat.primitives import serialization
            from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
        except ImportError as exc:
            raise ConfigurationError("'cryptography' package required for OCI API signing") from exc

        try:
            with open(key_path, "rb") as f:
                loaded_key = serialization.load_pem_private_key(f.read(), password=None)
            if not isinstance(loaded_key, RSAPrivateKey):
                raise ConfigurationError("OCI API requires an RSA private key")
            self._private_key = loaded_key
        except ConfigurationError:
            raise
        except Exception as exc:
            raise ConfigurationError(f"Failed to load OCI private key: {exc}") from exc

    @classmethod
    def from_provider_settings(cls, settings: OCIProviderSettings) -> OCIClient:
        """Create a client from provider settings.

        Args:
            settings: OCI provider settings dictionary

        Returns:
            OCIClient instance

        Raises:
            ConfigurationError: If required settings are missing or key loading fails
        """
        return cls(
            tenancy_ocid=settings.get("tenancy_ocid", ""),
            user_ocid=settings.get("user_ocid", ""),
            private_key_path=settings.get("private_key_path", ""),
            fingerprint=settings.get("fingerprint", ""),
            region=settings.get("region", ""),
        )

    def identity_url(self) -> str:
        """Return the Identity API base URL for the configured region."""
        return self.IDENTITY_API_BASE.format(region=self.region)

    def iaas_url(self) -> str:
        """Return the IAAS API base URL for the configured region."""
        return self.OCI_API_BASE.format(region=self.region)

    def list_resources(self, base_url: str, path: str) -> list[dict[str, Any]]:
        """Fetch a list resource from the OCI API.

        OCI list endpoints return JSON arrays directly.

        Args:
            base_url: API base URL (e.g. identity or iaas endpoint)
            path: API path including query parameters

        Returns:
            List of resource dicts

        Raises:
            APIError: On HTTP errors, connection errors, or unexpected response format
        """
        url = f"{base_url}{path}"
        headers = self._build_signed_headers("get", url)

        try:
            response = requests.get(url, headers=headers, timeout=self.timeout)
        except requests.exceptions.RequestException as e:
            raise APIError(
                f"OCI API request failed: {e}",
                provider="oci",
            ) from e

        if not response.ok:
            raise APIError(
                f"OCI API request failed: {response.status_code}",
                status_code=response.status_code,
                response=response.text,
                provider="oci",
            )

        try:
            data = response.json()
        except (json.JSONDecodeError, ValueError) as e:
            raise APIError(
                "Invalid JSON response from OCI",
                response=str(e),
                provider="oci",
            ) from e

        if not isinstance(data, list):
            raise APIError(
                "OCI API returned unexpected format (expected JSON array)",
                provider="oci",
            )

        return data

    def _build_signed_headers(self, method: str, url: str, body: str = "") -> dict[str, str]:
        """Build OCI API signed request headers.

        Uses HTTP Signatures (RFC 7235) with RSA-SHA256 signing.

        Args:
            method: HTTP method (lowercase)
            url: Full request URL
            body: Request body (empty for GET)

        Returns:
            Headers dict with Authorization signature
        """
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding

        # Parse URL for host and path
        parsed = urlparse(url)
        host = parsed.netloc
        path = parsed.path
        if parsed.query:
            path = f"{path}?{parsed.query}"

        # Build signing headers
        date = email.utils.formatdate(usegmt=True)
        headers: dict[str, str] = {
            "date": date,
            "host": host,
            "(request-target)": f"{method} {path}",
        }

        signing_headers = ["date", "(request-target)", "host"]

        if body:
            body_hash = hashlib.sha256(body.encode()).digest()
            content_sha256 = base64.b64encode(body_hash).decode()
            headers["content-type"] = "application/json"
            headers["x-content-sha256"] = content_sha256
            headers["content-length"] = str(len(body))
            signing_headers.extend(["content-type", "x-content-sha256", "content-length"])

        # Build signing string
        signing_string = "\n".join(f"{h}: {headers[h]}" for h in signing_headers)

        # Sign with RSA-SHA256
        signature = self._private_key.sign(
            signing_string.encode(),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        b64_signature = base64.b64encode(signature).decode()

        # Build Authorization header
        key_id = f"{self.tenancy_ocid}/{self.user_ocid}/{self.fingerprint}"
        auth_header = (
            f'Signature version="1",'
            f'keyId="{key_id}",'
            f'algorithm="rsa-sha256",'
            f'headers="{" ".join(signing_headers)}",'
            f'signature="{b64_signature}"'
        )

        return {
            "date": date,
            "host": host,
            "Authorization": auth_header,
        }
