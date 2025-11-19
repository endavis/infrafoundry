"""Shared helper for API-driven provider validators."""

from __future__ import annotations

from typing import Any

from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.core.validation_helpers.base_validator import BaseProviderValidator


class BaseAPIValidator:
    """Convenience wrapper around BaseProviderValidator for API providers."""

    def __init__(
        self,
        provider_name: str,
        env_config: dict[str, Any],
        report: ValidationReport,
        env_prefix: str | None = None,
    ) -> None:
        self.provider_name = provider_name
        self.env_prefix = env_prefix
        self._validator = BaseProviderValidator(provider_name, env_config, report)

    @property
    def provider_settings(self) -> dict[str, Any]:
        """Expose provider settings for convenience."""
        return self._validator.provider_settings

    def get_credentials(
        self,
        required_fields: list[str],
        env_vars: dict[str, str] | None = None,
    ) -> dict[str, Any] | None:
        """Fetch credentials from provider settings or environment."""
        env_map = env_vars
        if env_map is None and self.env_prefix:
            env_map = {field: f"{self.env_prefix}_{field.upper()}" for field in required_fields}
        return self._validator.validate_credentials(required_fields, env_map)

    def check_api_connectivity(self, **kwargs: Any) -> bool:
        """Proxy API connectivity checks."""
        return self._validator.check_api_connectivity(**kwargs)

    def add_success(
        self, check_name: str, message: str, details: dict[str, Any] | None = None
    ) -> None:
        """Record a successful validation check."""
        self._validator.add_success_check(check_name, message, details)

    def add_error(
        self,
        check_name: str,
        message: str,
        level: ValidationLevel = ValidationLevel.ERROR,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Record an error/warning validation check."""
        self._validator.add_error_check(
            check_name=check_name,
            message=message,
            level=level,
            details=details,
        )
