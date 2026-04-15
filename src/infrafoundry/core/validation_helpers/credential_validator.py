"""Credential validation utilities for infrastructure providers.

This module handles validation of provider credentials from various sources
(configuration files, environment variables, etc.).
"""

import logging
import os
from typing import Any

from infrafoundry.core.config.models import EnvironmentConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport

logger = logging.getLogger(__name__)


class CredentialValidator:
    """Validates provider credentials from configuration and environment variables.

    Checks multiple sources in order:
    1. Provider settings in configuration
    2. Environment variables (if mapping provided)

    Example:
        validator = CredentialValidator("proxmox", env_config, report)
        credentials = validator.validate_credentials(
            required_fields=["api_url", "api_token", "node"],
            env_vars={
                "api_url": "PROXMOX_API_URL",
                "api_token": "PROXMOX_API_TOKEN",
                "node": "PROXMOX_NODE"
            }
        )
    """

    def __init__(
        self,
        provider_name: str,
        env_config: EnvironmentConfig,
        report: ValidationReport,
    ) -> None:
        """Initialize credential validator.

        Args:
            provider_name: Provider name (e.g., "proxmox", "opnsense")
            env_config: Environment configuration with provider_settings
            report: ValidationReport to add results to
        """
        self.provider_name = provider_name
        self.env_config = env_config
        self.report = report
        self.provider_settings = env_config.provider_settings.get(provider_name, {})

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
            self._add_missing_credentials_error(required_fields, missing_fields)
            return None

        return credentials

    def _add_missing_credentials_error(
        self,
        required_fields: list[str],
        missing_fields: list[str],
    ) -> None:
        """Add validation error for missing credentials.

        Args:
            required_fields: All required field names
            missing_fields: Fields that are missing
        """
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
