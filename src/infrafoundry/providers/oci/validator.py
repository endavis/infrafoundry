"""Validation logic for OCI provider."""

from __future__ import annotations

import base64
import email.utils
import hashlib
from typing import cast

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.types import EnvironmentData, OCIProviderSettings
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.core.validation_helpers import BaseAPIValidator


class OCIValidator:
    """Validates OCI configurations against live API state.

    Performs pre-flight validation including:
    - API connectivity and authentication
    - VCN/subnet reference validation between resources
    """

    OCI_API_BASE = "https://iaas.{region}.oraclecloud.com"
    IDENTITY_API_BASE = "https://identity.{region}.oraclecloud.com"

    def __init__(self, env_config: EnvironmentData, report: ValidationReport) -> None:
        """Initialize OCI validator.

        Args:
            env_config: Environment configuration including provider_settings
            report: ValidationReport to add results to
        """
        self.env_config = env_config
        self.report = report
        self.api_validator = BaseAPIValidator("oci", env_config, report)
        self.provider_settings = cast(OCIProviderSettings, self.api_validator.provider_settings)

    def validate_connectivity(self) -> None:
        """Validate connectivity to OCI API.

        Checks:
        - Required credentials are present
        - API endpoint is reachable with signed request
        """
        credentials = self.api_validator.get_credentials(
            required_fields=[
                "tenancy_ocid",
                "user_ocid",
                "fingerprint",
                "private_key_path",
                "region",
            ]
        )
        if not credentials:
            return

        region = self.provider_settings.get("region", "")
        tenancy_ocid = self.provider_settings.get("tenancy_ocid", "")

        # Build the identity API URL for availability domains
        api_base = self.IDENTITY_API_BASE.format(region=region)
        url = f"{api_base}/20160918/availabilityDomains?compartmentId={tenancy_ocid}"

        # Build OCI API signature headers
        headers = self._build_signed_headers("get", url)
        if not headers:
            return

        # Test API connectivity
        response_ok = self.api_validator.check_api_connectivity(
            url=url,
            headers=headers,
        )

        if response_ok:
            self.api_validator.add_success(
                check_name="oci_connectivity",
                message="OCI API connectivity validated successfully",
            )

    def validate_references(self, resources: list[ResourceConfig]) -> None:
        """Validate that referenced OCI resources exist within config.

        Checks:
        - Subnets reference valid VCNs
        - Instances reference valid subnets

        Args:
            resources: List of resources to validate
        """
        # Collect resource names by type
        vcn_names: set[str] = set()
        subnet_names: set[str] = set()

        for resource in resources:
            if resource.type == "vcn":
                vcn_names.add(resource.name)
            elif resource.type == "subnet":
                subnet_names.add(resource.name)

        # Validate subnet -> VCN references
        for resource in resources:
            if resource.type == "subnet":
                vcn_ref = resource.config.get("vcn")
                if vcn_ref and vcn_ref not in vcn_names:
                    self.report.add_check(
                        check_name=f"oci_ref_subnet_{resource.name}_vcn",
                        passed=False,
                        message=(
                            f"Subnet '{resource.name}' references VCN '{vcn_ref}' "
                            f"which is not defined in the configuration"
                        ),
                        level=ValidationLevel.ERROR,
                    )
                else:
                    self.report.add_check(
                        check_name=f"oci_ref_subnet_{resource.name}_vcn",
                        passed=True,
                        message=f"Subnet '{resource.name}' VCN reference valid",
                    )

        # Validate instance -> subnet references
        for resource in resources:
            if resource.type == "instance":
                subnet_ref = resource.config.get("subnet")
                if subnet_ref and subnet_ref not in subnet_names:
                    self.report.add_check(
                        check_name=f"oci_ref_instance_{resource.name}_subnet",
                        passed=False,
                        message=(
                            f"Instance '{resource.name}' references subnet '{subnet_ref}' "
                            f"which is not defined in the configuration"
                        ),
                        level=ValidationLevel.ERROR,
                    )
                else:
                    self.report.add_check(
                        check_name=f"oci_ref_instance_{resource.name}_subnet",
                        passed=True,
                        message=f"Instance '{resource.name}' subnet reference valid",
                    )

    def _build_signed_headers(self, method: str, url: str, body: str = "") -> dict[str, str] | None:
        """Build OCI API signed request headers.

        Uses HTTP Signatures (RFC 7235) with RSA-SHA256 signing.

        Args:
            method: HTTP method (lowercase)
            url: Full request URL
            body: Request body (empty for GET)

        Returns:
            Headers dict with Authorization signature, or None on error
        """
        from pathlib import Path
        from urllib.parse import urlparse

        tenancy_ocid = self.provider_settings.get("tenancy_ocid", "")
        user_ocid = self.provider_settings.get("user_ocid", "")
        fingerprint = self.provider_settings.get("fingerprint", "")
        private_key_path = self.provider_settings.get("private_key_path", "")

        # Expand ~ in key path
        key_path = Path(private_key_path).expanduser()
        if not key_path.exists():
            self.api_validator.add_error(
                check_name="oci_private_key",
                message=f"OCI private key not found: {key_path}",
            )
            return None

        try:
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import padding
            from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
        except ImportError:
            self.api_validator.add_error(
                check_name="oci_dependencies",
                message="'cryptography' package required for OCI API signing",
                level=ValidationLevel.WARNING,
            )
            return None

        # Load private key (OCI requires RSA keys)
        try:
            with open(key_path, "rb") as f:
                loaded_key = serialization.load_pem_private_key(f.read(), password=None)
            if not isinstance(loaded_key, RSAPrivateKey):
                self.api_validator.add_error(
                    check_name="oci_private_key",
                    message="OCI API requires an RSA private key",
                )
                return None
            private_key = loaded_key
        except Exception as exc:
            self.api_validator.add_error(
                check_name="oci_private_key",
                message=f"Failed to load OCI private key: {exc}",
            )
            return None

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
        signature = private_key.sign(
            signing_string.encode(),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        b64_signature = base64.b64encode(signature).decode()

        # Build Authorization header
        key_id = f"{tenancy_ocid}/{user_ocid}/{fingerprint}"
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
