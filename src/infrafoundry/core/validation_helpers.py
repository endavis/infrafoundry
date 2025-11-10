"""Base validation helper for providers.

This module provides reusable validation utilities for provider implementations,
reducing code duplication and standardizing validation patterns across providers.
"""

import logging
from typing import Any

from infrafoundry.core.validation import ValidationLevel, ValidationReport

logger = logging.getLogger(__name__)


class BaseProviderValidator:
    """Base class for provider validation with common helper methods.

    Provides reusable patterns for:
    - Credential validation
    - API connectivity checks
    - HTTP response validation
    - Resource reference checks

    Example:
        class ProxmoxProvider(ProviderBase):
            def validate_connectivity(self, env_config, report):
                validator = BaseProviderValidator(
                    provider_name="proxmox",
                    env_config=env_config,
                    report=report
                )

                credentials = validator.validate_credentials(
                    required_fields=["api_url", "api_token", "node"]
                )
                if not credentials:
                    return

                validator.check_api_connectivity(
                    url=f"{credentials['api_url']}/api2/json/version",
                    headers={"Authorization": f"PVEAPIToken={credentials['api_token']}"},
                    verify_ssl=False
                )
    """

    def __init__(
        self,
        provider_name: str,
        env_config: dict[str, Any],
        report: ValidationReport,
    ):
        """Initialize validator.

        Args:
            provider_name: Name of the provider (e.g., "proxmox", "opnsense")
            env_config: Environment configuration with provider_settings
            report: ValidationReport to add results to
        """
        self.provider_name = provider_name
        self.env_config = env_config
        self.report = report
        self.provider_settings = env_config.get("provider_settings", {}).get(provider_name, {})

    def validate_credentials(
        self,
        required_fields: list[str],
        env_vars: dict[str, str] | None = None,
    ) -> dict[str, Any] | None:
        """Validate that required credentials are configured.

        Checks provider_settings first, then falls back to environment variables.

        Args:
            required_fields: List of required credential field names
            env_vars: Optional dict mapping field names to env var names

        Returns:
            Dict of credentials if valid, None otherwise

        Example:
            credentials = validator.validate_credentials(
                required_fields=["api_url", "api_key", "api_secret"],
                env_vars={
                    "api_url": "OPNSENSE_API_URL",
                    "api_key": "OPNSENSE_API_KEY",
                    "api_secret": "OPNSENSE_API_SECRET"
                }
            )
        """
        import os

        credentials = {}
        missing_fields = []

        for field in required_fields:
            # Try provider_settings first
            value = self.provider_settings.get(field)

            # Fall back to environment variable if provided
            if not value and env_vars and field in env_vars:
                value = os.getenv(env_vars[field])

            if value:
                credentials[field] = value
            else:
                missing_fields.append(field)

        if missing_fields:
            self.report.add_check(
                check_name=f"{self.provider_name}_credentials",
                passed=False,
                message=(
                    f"{self.provider_name.title()} credentials not configured "
                    f"({', '.join(required_fields)} required)"
                ),
                level=ValidationLevel.ERROR,
                details={"missing_fields": missing_fields},
            )
            return None

        return credentials

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

        Args:
            url: API endpoint URL
            method: HTTP method (GET, POST, etc.)
            auth: Optional (username, password) tuple for basic auth
            headers: Optional HTTP headers
            verify_ssl: Whether to verify SSL certificates
            timeout: Request timeout in seconds
            success_message: Custom success message (defaults to standard message)

        Returns:
            True if API is reachable and returns 200, False otherwise
        """
        try:
            import requests
        except ImportError:
            self.report.add_check(
                check_name=f"{self.provider_name}_connectivity",
                passed=False,
                message="requests library not installed (required for API validation)",
                level=ValidationLevel.ERROR,
            )
            return False

        try:
            response = requests.request(
                method=method,
                url=url,
                auth=auth,
                headers=headers,
                verify=verify_ssl,
                timeout=timeout,
            )

            if response.status_code == 200:
                msg = (
                    success_message
                    or f"Successfully connected to {self.provider_name} API at {url}"
                )
                self.report.add_check(
                    check_name=f"{self.provider_name}_connectivity",
                    passed=True,
                    message=msg,
                    level=ValidationLevel.INFO,
                )
                return True

            elif response.status_code == 401:
                self.report.add_check(
                    check_name=f"{self.provider_name}_connectivity",
                    passed=False,
                    message=(
                        f"{self.provider_name.title()} API credentials invalid (401 Unauthorized)"
                    ),
                    level=ValidationLevel.ERROR,
                )
                return False

            elif response.status_code == 403:
                self.report.add_check(
                    check_name=f"{self.provider_name}_connectivity",
                    passed=False,
                    message=f"{self.provider_name.title()} API access forbidden (403 Forbidden)",
                    level=ValidationLevel.ERROR,
                )
                return False

            else:
                self.report.add_check(
                    check_name=f"{self.provider_name}_connectivity",
                    passed=False,
                    message=f"Failed to connect: HTTP {response.status_code}",
                    level=ValidationLevel.ERROR,
                    details={"status_code": response.status_code, "url": url},
                )
                return False

        except requests.exceptions.Timeout:
            self.report.add_check(
                check_name=f"{self.provider_name}_connectivity",
                passed=False,
                message=f"Connection timeout after {timeout}s",
                level=ValidationLevel.ERROR,
                details={"url": url, "timeout": timeout},
            )
            return False

        except requests.exceptions.ConnectionError as e:
            self.report.add_check(
                check_name=f"{self.provider_name}_connectivity",
                passed=False,
                message=f"Connection failed: {e}",
                level=ValidationLevel.ERROR,
                details={"url": url},
            )
            return False

        except Exception as e:
            self.report.add_check(
                check_name=f"{self.provider_name}_connectivity",
                passed=False,
                message=f"Unexpected error testing connectivity: {e}",
                level=ValidationLevel.ERROR,
                details={"url": url, "error_type": type(e).__name__},
            )
            return False

    def add_success_check(
        self,
        check_name: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Add a success validation check.

        Helper method for consistent success reporting.

        Args:
            check_name: Name of the validation check
            message: Success message
            details: Optional additional details
        """
        self.report.add_check(
            check_name=check_name,
            passed=True,
            message=message,
            level=ValidationLevel.INFO,
            details=details,
        )

    def add_error_check(
        self,
        check_name: str,
        message: str,
        level: ValidationLevel = ValidationLevel.ERROR,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Add an error validation check.

        Helper method for consistent error reporting.

        Args:
            check_name: Name of the validation check
            message: Error message
            level: Validation level (ERROR or WARNING)
            details: Optional additional details
        """
        self.report.add_check(
            check_name=check_name,
            passed=False,
            message=message,
            level=level,
            details=details,
        )

    def validate_resource_exists(
        self,
        resource_type: str,
        resource_name: str,
        existing_resources: set[str],
        parent_resource: str | None = None,
    ) -> bool:
        """Validate that a referenced resource exists.

        Args:
            resource_type: Type of resource (e.g., "template", "vlan", "alias")
            resource_name: Name of the resource being checked
            existing_resources: Set of existing resource names
            parent_resource: Optional parent resource name for context

        Returns:
            True if resource exists, False otherwise
        """
        check_name = f"{self.provider_name}_{resource_type}_{resource_name}"

        if resource_name in existing_resources:
            msg = f"{resource_type.title()} '{resource_name}' exists"
            if parent_resource:
                msg += f" (referenced by {parent_resource})"

            self.add_success_check(
                check_name=check_name,
                message=msg,
            )
            return True
        else:
            msg = f"{resource_type.title()} '{resource_name}' not found"
            if parent_resource:
                msg += f" (referenced by {parent_resource})"

            self.add_error_check(
                check_name=check_name,
                message=msg,
                details={
                    "resource_type": resource_type,
                    "resource_name": resource_name,
                    "existing_resources": list(existing_resources),
                },
            )
            return False
