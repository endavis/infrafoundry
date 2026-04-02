"""CRD validation for Kubernetes provider."""

from __future__ import annotations

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.core.validation_helpers import BaseAPIValidator

# Standard Kubernetes API groups that don't require CRDs
_STANDARD_API_GROUPS: frozenset[str] = frozenset(
    {
        "",
        "apps",
        "batch",
        "networking.k8s.io",
        "rbac.authorization.k8s.io",
        "policy",
        "autoscaling",
        "storage.k8s.io",
        "admissionregistration.k8s.io",
        "apiextensions.k8s.io",
        "certificates.k8s.io",
        "coordination.k8s.io",
        "discovery.k8s.io",
        "events.k8s.io",
        "flowcontrol.apiserver.k8s.io",
        "node.k8s.io",
        "scheduling.k8s.io",
    }
)


class CRDValidator:
    """Validates that CRDs required by manifest resources exist.

    Queries the Kubernetes API for installed CRDs and checks that
    any custom resource references in manifest resources have their
    corresponding CRD installed.
    """

    def __init__(self, api_validator: BaseAPIValidator, report: ValidationReport) -> None:
        """Initialize CRD validator.

        Args:
            api_validator: Shared API validator helper
            report: ValidationReport to add results to
        """
        self.api_validator = api_validator
        self.report = report

    def validate(
        self,
        server_url: str,
        headers: dict[str, str],
        verify_ssl: bool,
        manifests: list[ResourceConfig],
    ) -> None:
        """Validate that CRDs required by manifests are installed.

        Args:
            server_url: Kubernetes API server URL
            headers: HTTP headers with authorization
            verify_ssl: Whether to verify SSL certificates
            manifests: Manifest resources to check for CRD requirements
        """
        if not manifests:
            return

        # Extract required CRD groups from manifests
        required_groups = self._extract_custom_api_groups(manifests)
        if not required_groups:
            return

        # Fetch installed CRDs
        installed_groups = self._fetch_crd_groups(server_url, headers, verify_ssl)
        if installed_groups is None:
            return  # API error already reported

        for group, resource_names in sorted(required_groups.items()):
            if group in installed_groups:
                self.report.add_check(
                    check_name=f"kubernetes_crd_{group}",
                    passed=True,
                    message=(
                        f"CRD group '{group}' is installed "
                        f"(used by: {', '.join(sorted(resource_names))})"
                    ),
                )
            else:
                self.report.add_check(
                    check_name=f"kubernetes_crd_{group}",
                    passed=False,
                    message=(
                        f"CRD group '{group}' not found in cluster "
                        f"(required by: {', '.join(sorted(resource_names))})"
                    ),
                    level=ValidationLevel.ERROR,
                )

    def _extract_custom_api_groups(self, manifests: list[ResourceConfig]) -> dict[str, list[str]]:
        """Extract non-standard API groups from manifest resources.

        Returns:
            Mapping of API group to list of resource names using it.
        """
        groups: dict[str, list[str]] = {}
        for manifest in manifests:
            config = manifest.config or {}
            api_version = config.get("apiVersion", "")
            group = self._parse_api_group(api_version)
            if group and group not in _STANDARD_API_GROUPS:
                groups.setdefault(group, []).append(manifest.name)
        return groups

    def _parse_api_group(self, api_version: str) -> str:
        """Parse the API group from an apiVersion string.

        Args:
            api_version: Kubernetes apiVersion (e.g., "apps/v1", "cert-manager.io/v1")

        Returns:
            The API group portion, or empty string for core API.
        """
        if "/" in api_version:
            return api_version.rsplit("/", 1)[0]
        return ""

    def _fetch_crd_groups(
        self,
        server_url: str,
        headers: dict[str, str],
        verify_ssl: bool,
    ) -> set[str] | None:
        """Fetch the set of API groups that have CRDs installed.

        Returns:
            Set of API group names, or None if the API call failed.
        """
        data = self.api_validator.fetch_json(
            url=f"{server_url}/apis/apiextensions.k8s.io/v1/customresourcedefinitions",
            headers=headers,
            verify_ssl=verify_ssl,
            timeout=10,
            check_name="kubernetes_crds_list",
            error_message="Failed to list CRDs (status {status})",
            error_level=ValidationLevel.WARNING,
        )
        if data is None:
            return None

        items = data.get("items", [])
        groups: set[str] = set()
        for item in items:
            group = item.get("spec", {}).get("group", "")
            if group:
                groups.add(group)
        return groups
