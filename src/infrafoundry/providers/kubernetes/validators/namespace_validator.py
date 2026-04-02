"""Namespace validation for Kubernetes provider."""

from __future__ import annotations

from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.core.validation_helpers import BaseAPIValidator


class NamespaceValidator:
    """Validates that referenced namespaces exist in the cluster.

    Queries the Kubernetes API for existing namespaces and checks
    that all namespace references in resources are either present
    in the cluster or being created by the configuration.
    """

    def __init__(self, api_validator: BaseAPIValidator, report: ValidationReport) -> None:
        """Initialize namespace validator.

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
        referenced_namespaces: set[str],
        config_namespaces: set[str],
    ) -> None:
        """Validate that referenced namespaces exist or will be created.

        Args:
            server_url: Kubernetes API server URL
            headers: HTTP headers with authorization
            verify_ssl: Whether to verify SSL certificates
            referenced_namespaces: Namespaces referenced by resources
            config_namespaces: Namespaces defined in the configuration
        """
        if not referenced_namespaces:
            return

        # Fetch existing namespaces from API
        existing = self._fetch_namespaces(server_url, headers, verify_ssl)
        if existing is None:
            return  # API error already reported

        for ns in sorted(referenced_namespaces):
            if ns in existing:
                self.report.add_check(
                    check_name=f"kubernetes_namespace_{ns}",
                    passed=True,
                    message=f"Namespace '{ns}' exists in cluster",
                    level=ValidationLevel.INFO,
                )
            elif ns in config_namespaces:
                self.report.add_check(
                    check_name=f"kubernetes_namespace_{ns}",
                    passed=True,
                    message=f"Namespace '{ns}' will be created by configuration",
                    level=ValidationLevel.INFO,
                )
            else:
                self.report.add_check(
                    check_name=f"kubernetes_namespace_{ns}",
                    passed=True,
                    message=(
                        f"Namespace '{ns}' not found in cluster or configuration "
                        "(assuming it exists)"
                    ),
                    level=ValidationLevel.WARNING,
                )

    def _fetch_namespaces(
        self,
        server_url: str,
        headers: dict[str, str],
        verify_ssl: bool,
    ) -> set[str] | None:
        """Fetch the list of existing namespaces from the cluster.

        Returns:
            Set of namespace names, or None if the API call failed.
        """
        data = self.api_validator.fetch_json(
            url=f"{server_url}/api/v1/namespaces",
            headers=headers,
            verify_ssl=verify_ssl,
            timeout=10,
            check_name="kubernetes_namespaces_list",
            error_message="Failed to list namespaces (status {status})",
            error_level=ValidationLevel.WARNING,
        )
        if data is None:
            return None

        items = data.get("items", [])
        return {item.get("metadata", {}).get("name", "") for item in items} - {""}
