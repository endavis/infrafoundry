"""Validation logic for OCI provider."""

from __future__ import annotations

import logging
from typing import Any, cast

from infrafoundry.core.exceptions import APIError, ConfigurationError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.tailscale import TailscaleSchemaError, process_tailscale_config
from infrafoundry.core.types import EnvironmentData, OCIProviderSettings
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.core.validation_helpers import (
    BaseAPIValidator,
    validate_terraform_secrets_references,
)
from infrafoundry.providers.oci.api_client import OCIClient

from .validators import CompartmentValidator, ImageValidator, NetworkValidator

logger = logging.getLogger(__name__)


class OCIValidator:
    """Validates OCI configurations against live API state.

    Performs pre-flight validation including:
    - API connectivity and authentication
    - VCN/subnet reference validation between resources
    - Compartment existence validation via OCI API
    - VCN/subnet name collision detection via OCI API
    - Image OCID validation via OCI API
    """

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

        # Initialize specialized validators
        self.compartment_validator = CompartmentValidator(report)
        self.network_validator = NetworkValidator(report)
        self.image_validator = ImageValidator(report)

    def _create_client(self) -> OCIClient | None:
        """Create an OCIClient from provider settings.

        Returns:
            OCIClient instance, or None if client creation fails
        """
        try:
            return OCIClient.from_provider_settings(self.provider_settings)
        except ConfigurationError as exc:
            self.api_validator.add_error(
                check_name="oci_client",
                message=str(exc),
                level=ValidationLevel.WARNING,
            )
            return None

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

        client = self._create_client()
        if not client:
            return

        tenancy_ocid = self.provider_settings.get("tenancy_ocid", "")

        # Test API connectivity using availability domains endpoint
        try:
            client.list_resources(
                base_url=client.identity_url(),
                path=f"/20160918/availabilityDomains?compartmentId={tenancy_ocid}",
            )
            self.api_validator.add_success(
                check_name="oci_connectivity",
                message="OCI API connectivity validated successfully",
            )
        except APIError as exc:
            self.api_validator.add_error(
                check_name="oci_connectivity",
                message=f"OCI API connectivity failed: {exc.message}",
            )

    def validate_references(self, resources: list[ResourceConfig]) -> None:
        """Validate that referenced OCI resources exist within config and live API.

        Performs local cross-reference checks (always) and API-based validation
        (when client creation succeeds and compartment_ocid is configured).

        Args:
            resources: List of resources to validate
        """
        self._validate_local_references(resources)
        self._validate_api_references(resources)

    def _validate_local_references(self, resources: list[ResourceConfig]) -> None:
        """Validate cross-references between resources in the configuration.

        Checks:
        - Subnets reference valid VCNs
        - Instances reference valid subnets
        - ``tailscale:`` schema is well-formed and mutually exclusive with
          ``cloud_init_snippets`` (issue #212)
        - ``terraform_secrets`` references resolve in env secrets

        Args:
            resources: List of resources to validate
        """
        # Tailscale schema must run before terraform_secrets validation
        # because process_tailscale_config auto-populates terraform_secrets
        # from the tailscale.auth.* secret references.
        for resource in resources:
            if resource.type != "instance":
                continue
            if (resource.config or {}).get("tailscale") is None:
                continue
            try:
                # base64_encode flag is irrelevant for validation; just need
                # the schema check + terraform_secrets auto-population.
                process_tailscale_config(resource, base64_encode=True)
            except TailscaleSchemaError as exc:
                self.report.add_check(
                    check_name=f"oci_tailscale_schema_{resource.name}",
                    passed=False,
                    message=str(exc),
                    level=ValidationLevel.ERROR,
                )

        validate_terraform_secrets_references("oci", resources, self.env_config, self.report)
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

    def _validate_api_references(self, resources: list[ResourceConfig]) -> None:
        """Validate resources against live OCI API state.

        Attempts to create an OCIClient. If client creation fails or
        compartment_ocid is not configured, API checks are skipped gracefully.

        Args:
            resources: List of resources to validate
        """
        compartment_ocid = self.provider_settings.get("compartment_ocid", "")
        tenancy_ocid = self.provider_settings.get("tenancy_ocid", "")

        if not compartment_ocid or not self.provider_settings.get("region", ""):
            return

        client = self._create_client()
        if not client:
            return

        try:
            # Fetch compartments (uses tenancy_ocid as parent)
            compartments = None
            if tenancy_ocid:
                compartments = self._safe_list(
                    client,
                    client.identity_url(),
                    f"/20160918/compartments?compartmentId={tenancy_ocid}",
                )
                self.compartment_validator.validate(compartment_ocid, compartments)

            # Fetch VCNs and subnets
            vcns = self._safe_list(
                client,
                client.iaas_url(),
                f"/20160918/vcns?compartmentId={compartment_ocid}",
            )
            subnets = self._safe_list(
                client,
                client.iaas_url(),
                f"/20160918/subnets?compartmentId={compartment_ocid}",
            )
            self.network_validator.validate(resources, vcns, subnets)

            # Fetch images
            images = self._safe_list(
                client,
                client.iaas_url(),
                f"/20160918/images?compartmentId={compartment_ocid}",
            )
            self.image_validator.validate(resources, images)

        except Exception as exc:
            self.api_validator.handle_validation_exception(
                check_name="oci_api_validation",
                error=exc,
                warning_level=ValidationLevel.WARNING,
            )

    def _safe_list(
        self,
        client: OCIClient,
        base_url: str,
        path: str,
    ) -> list[dict[str, Any]] | None:
        """Safely fetch a list resource, returning None on failure.

        Args:
            client: OCI API client
            base_url: API base URL
            path: API path including query parameters

        Returns:
            List of resource dicts, or None if the request fails
        """
        try:
            return client.list_resources(base_url, path)
        except APIError:
            return None
