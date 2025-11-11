"""Base validation helper for infrastructure providers.

This module provides a unified interface for provider validation by composing
specialized validators for credentials, connectivity, resources, and reporting.
"""

import logging
from typing import Any

from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.core.validation_helpers.connectivity_validator import ConnectivityValidator
from infrafoundry.core.validation_helpers.credential_validator import CredentialValidator
from infrafoundry.core.validation_helpers.report_helper import ValidationReportHelper
from infrafoundry.core.validation_helpers.resource_validator import ResourceValidator

logger = logging.getLogger(__name__)


class BaseProviderValidator:
    """Unified validation interface for infrastructure providers.

    Composes specialized validators to provide a complete validation toolkit:
    - Credential validation (settings + environment variables)
    - API connectivity testing
    - Resource reference validation
    - Standardized report helpers

    Example:
        validator = BaseProviderValidator(
            provider_name="proxmox",
            env_config=env_config,
            report=report
        )

        # Validate credentials
        credentials = validator.validate_credentials(
            required_fields=["api_url", "api_token", "node"]
        )

        # Test connectivity
        if credentials:
            validator.check_api_connectivity(
                url=f"{credentials['api_url']}/api2/json/version",
                headers={"Authorization": f"PVEAPIToken={credentials['api_token']}"},
                verify_ssl=False
            )

        # Validate resource references
        validator.validate_resource_exists(
            resource_type="template",
            resource_name="ubuntu-22.04",
            existing_resources=template_names,
            parent_resource="web-server-01"
        )
    """

    def __init__(
        self,
        provider_name: str,
        env_config: dict[str, Any],
        report: ValidationReport,
    ):
        """Initialize provider validator with specialized validators.

        Args:
            provider_name: Provider name (e.g., "proxmox", "opnsense")
            env_config: Environment configuration with provider_settings
            report: ValidationReport to add results to
        """
        self.provider_name = provider_name
        self.env_config = env_config
        self.report = report

        # Initialize specialized validators
        self._credential_validator = CredentialValidator(provider_name, env_config, report)
        self._connectivity_validator = ConnectivityValidator(provider_name, report)
        self._resource_validator = ResourceValidator(provider_name, report)
        self._report_helper = ValidationReportHelper(report)

    @property
    def provider_settings(self) -> dict[str, Any]:
        """Get provider settings from credential validator."""
        return self._credential_validator.provider_settings

    @provider_settings.setter
    def provider_settings(self, value: dict[str, Any]) -> None:
        """Set provider settings on credential validator."""
        self._credential_validator.provider_settings = value

    # Delegate to CredentialValidator
    def validate_credentials(
        self,
        required_fields: list[str],
        env_vars: dict[str, str] | None = None,
    ) -> dict[str, Any] | None:
        """Validate that required credentials are configured.

        Delegates to CredentialValidator.

        Args:
            required_fields: List of required credential field names
            env_vars: Optional dict mapping field names to env var names

        Returns:
            Dict of credentials if valid, None otherwise
        """
        return self._credential_validator.validate_credentials(required_fields, env_vars)

    # Delegate to ConnectivityValidator
    def check_api_connectivity(
        self,
        url: str,
        method: str = "GET",
        auth: tuple[str, str] | None = None,
        headers: dict[str, str] | None = None,
        verify_ssl: bool = True,
        timeout: int = 10,
        success_message: str | None = None,
    ) -> bool:
        """Test API connectivity with standardized error handling.

        Delegates to ConnectivityValidator.

        Args:
            url: API endpoint URL
            method: HTTP method (GET, POST, etc.)
            auth: Optional (username, password) tuple for basic auth
            headers: Optional HTTP headers
            verify_ssl: Whether to verify SSL certificates
            timeout: Request timeout in seconds
            success_message: Custom success message

        Returns:
            True if API is reachable and returns 200, False otherwise
        """
        return self._connectivity_validator.check_api_connectivity(
            url=url,
            method=method,
            auth=auth,
            headers=headers,
            verify_ssl=verify_ssl,
            timeout=timeout,
            success_message=success_message,
        )

    # Delegate to ResourceValidator
    def validate_resource_exists(
        self,
        resource_type: str,
        resource_name: str,
        existing_resources: set[str],
        parent_resource: str | None = None,
    ) -> bool:
        """Validate that a referenced resource exists.

        Delegates to ResourceValidator.

        Args:
            resource_type: Type of resource (e.g., "template", "vlan", "alias")
            resource_name: Name of the resource being checked
            existing_resources: Set of existing resource names
            parent_resource: Optional parent resource name for context

        Returns:
            True if resource exists, False otherwise
        """
        return self._resource_validator.validate_resource_exists(
            resource_type=resource_type,
            resource_name=resource_name,
            existing_resources=existing_resources,
            parent_resource=parent_resource,
        )

    # Delegate to ValidationReportHelper
    def add_success_check(
        self,
        check_name: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Add a success validation check.

        Delegates to ValidationReportHelper.

        Args:
            check_name: Name of the validation check
            message: Success message
            details: Optional additional details
        """
        self._report_helper.add_success_check(check_name, message, details)

    def add_error_check(
        self,
        check_name: str,
        message: str,
        level: ValidationLevel = ValidationLevel.ERROR,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Add an error validation check.

        Delegates to ValidationReportHelper.

        Args:
            check_name: Name of the validation check
            message: Error message
            level: Validation level (ERROR or WARNING)
            details: Optional additional details
        """
        self._report_helper.add_error_check(check_name, message, level, details)
