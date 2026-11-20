"""Validation logic for OCI provider."""

from __future__ import annotations

import ipaddress
import logging
from dataclasses import replace
from typing import Any, cast

from infrafoundry.core.config.models import EnvironmentConfig
from infrafoundry.core.exceptions import APIError, ConfigurationError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.tailscale import TailscaleSchemaError, process_tailscale_config
from infrafoundry.core.types import OCIProviderSettings
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.core.validation_helpers import (
    BaseAPIValidator,
    validate_terraform_secrets_references,
)
from infrafoundry.providers.oci.api_client import OCIClient

from .compartments import find_parent_cycles, is_ocid
from .validators import (
    CompartmentValidator,
    ImageValidator,
    NetworkValidator,
    StorageIamValidator,
)
from .validators.context import OCIApiContext, OCIStorageIamContext

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

    def __init__(self, env_config: EnvironmentConfig, report: ValidationReport) -> None:
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
        self.storage_iam_validator = StorageIamValidator(report)

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
        self._validate_compartments(resources, None)
        self.storage_iam_validator.validate(OCIStorageIamContext(resources=resources))
        self._validate_api_references(resources)

    def validate_offline(
        self,
        resources: list[ResourceConfig],
        reference_resources: list[ResourceConfig] | None = None,
    ) -> None:
        """Run the local cross-reference checks, which need no OCI API (#1433).

        Args:
            resources: List of resources to validate
            reference_resources: Every OCI resource in the environment, used to resolve
                compartment names when ``resources`` is a filtered subset
        """
        self._validate_local_references(resources)
        self._validate_compartments(resources, reference_resources)
        self.storage_iam_validator.validate(
            OCIStorageIamContext(
                resources=resources, reference_resources=list(reference_resources or [])
            )
        )

    def _validate_compartments(
        self,
        resources: list[ResourceConfig],
        reference_resources: list[ResourceConfig] | None,
    ) -> None:
        """Validate compartment resources and the ``compartment`` references to them.

        Checks that each compartment has a description, a known parent and no parent
        cycle, that each ``compartment`` reference is an OCID or a defined compartment,
        and that a resource without one has a ``compartment_ocid`` to fall back on.
        """
        pool = [*(reference_resources or []), *resources]
        names = {r.name for r in pool if r.type == "compartment"}
        fallback = self.provider_settings.get("compartment_ocid", "")

        def fail(check: str, message: str) -> None:
            self.report.add_check(
                check_name=check, passed=False, message=message, level=ValidationLevel.ERROR
            )

        compartments = [r for r in resources if r.type == "compartment"]
        for comp in compartments:
            if not comp.config.get("description"):
                fail(
                    f"oci_compartment_{comp.name}_description",
                    f"Compartment '{comp.name}' requires a description",
                )
            parent = comp.config.get("parent")
            if parent and not is_ocid(str(parent)) and parent not in names:
                fail(
                    f"oci_compartment_{comp.name}_parent",
                    f"Compartment '{comp.name}' has parent '{parent}' which is neither "
                    f"an OCID nor a defined compartment",
                )
        cyclic = find_parent_cycles(r for r in pool if r.type == "compartment")
        for comp in compartments:
            if comp.name in cyclic:
                fail(
                    f"oci_compartment_{comp.name}_cycle",
                    f"Compartment '{comp.name}' is part of a parent cycle",
                )

        for resource in resources:
            if resource.type not in ("vcn", "subnet", "instance", "bucket"):
                continue
            ref = resource.config.get("compartment")
            check = f"oci_compartment_ref_{resource.type}_{resource.name}"
            if ref:
                if not is_ocid(str(ref)) and ref not in names:
                    fail(
                        check,
                        f"{resource.type.capitalize()} '{resource.name}' references "
                        f"compartment '{ref}' which is neither an OCID nor a defined compartment",
                    )
            elif not fallback:
                fail(
                    check,
                    f"{resource.type.capitalize()} '{resource.name}' sets no compartment "
                    f"and the provider settings have no compartment_ocid",
                )

    def _validate_local_references(self, resources: list[ResourceConfig]) -> None:
        """Validate cross-references between resources in the configuration.

        Checks:
        - Subnets reference valid VCNs
        - Instances reference valid subnets
        - Subnet CIDRs lie inside their VCN's CIDR and do not overlap (#1521)
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

        self._validate_subnet_cidrs(resources)

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

    @staticmethod
    def _parse_network(value: object) -> ipaddress.IPv4Network | ipaddress.IPv6Network | None:
        """Parse a CIDR string, returning None when it is missing or unparsable."""
        if not isinstance(value, str):
            return None
        try:
            return ipaddress.ip_network(value, strict=False)
        except ValueError:
            return None

    def _validate_subnet_cidrs(self, resources: list[ResourceConfig]) -> None:
        """Check subnet CIDRs against their VCN and each other, offline (#1521).

        Reports an ERROR when a subnet's ``cidr_block`` is not inside the
        ``cidr_block`` of the VCN it references, or when two subnets of one VCN
        overlap. A subnet whose VCN is not defined, or whose CIDR (or the VCN's)
        is missing or unparsable, is skipped; the reference check reports the
        former. Only failures are reported.

        Args:
            resources: List of resources to validate
        """
        vcn_nets: dict[str, ipaddress.IPv4Network | ipaddress.IPv6Network] = {}
        for resource in resources:
            if resource.type == "vcn":
                net = self._parse_network(resource.config.get("cidr_block"))
                if net is not None:
                    vcn_nets[resource.name] = net

        by_vcn: dict[str, list[tuple[str, ipaddress.IPv4Network | ipaddress.IPv6Network]]] = {}
        for resource in resources:
            if resource.type != "subnet":
                continue
            vcn_ref = resource.config.get("vcn")
            subnet_net = self._parse_network(resource.config.get("cidr_block"))
            if not isinstance(vcn_ref, str) or vcn_ref not in vcn_nets or subnet_net is None:
                continue
            vcn_net = vcn_nets[vcn_ref]
            if subnet_net.version != vcn_net.version or not subnet_net.subnet_of(vcn_net):  # type: ignore[arg-type]
                self.report.add_check(
                    check_name=f"oci_subnet_{resource.name}_cidr_outside_vcn",
                    passed=False,
                    message=(
                        f"Subnet '{resource.name}' cidr_block {subnet_net} is not inside "
                        f"VCN '{vcn_ref}' cidr_block {vcn_net}"
                    ),
                    level=ValidationLevel.ERROR,
                )
                continue
            by_vcn.setdefault(vcn_ref, []).append((resource.name, subnet_net))

        for vcn_ref, subnets in by_vcn.items():
            for i, (name_a, net_a) in enumerate(subnets):
                for name_b, net_b in subnets[i + 1 :]:
                    if net_a.version == net_b.version and net_a.overlaps(net_b):
                        self.report.add_check(
                            check_name=f"oci_subnet_{name_a}_{name_b}_cidr_overlap",
                            passed=False,
                            message=(
                                f"Subnets '{name_a}' ({net_a}) and '{name_b}' ({net_b}) "
                                f"in VCN '{vcn_ref}' have overlapping cidr_block ranges"
                            ),
                            level=ValidationLevel.ERROR,
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

        region = self.provider_settings.get("region", "")
        has_compartments = any(r.type == "compartment" for r in resources)

        if not region or not (compartment_ocid or has_compartments):
            return

        client = self._create_client()
        if not client:
            return

        context = OCIApiContext(
            resources=resources, compartment_ocid=compartment_ocid, region=region
        )

        try:
            if has_compartments and tenancy_ocid:
                subscriptions = self._safe_list(
                    client,
                    client.identity_url(),
                    f"/20160918/tenancies/{tenancy_ocid}/regionSubscriptions",
                )
                context = replace(context, region_subscriptions=subscriptions)
                self.compartment_validator.check_home_region(context)

            if not compartment_ocid:
                return

            # Fetch compartments (uses tenancy_ocid as parent)
            compartments = None
            if tenancy_ocid:
                compartments = self._safe_list(
                    client,
                    client.identity_url(),
                    f"/20160918/compartments?compartmentId={tenancy_ocid}",
                )
                context = replace(context, compartments=compartments)
                self.compartment_validator.validate(context)

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
            context = replace(context, existing_vcns=vcns, existing_subnets=subnets)
            self.network_validator.validate(context)

            # Fetch images
            images = self._safe_list(
                client,
                client.iaas_url(),
                f"/20160918/images?compartmentId={compartment_ocid}",
            )
            context = replace(context, existing_images=images)
            self.image_validator.validate(context)

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
