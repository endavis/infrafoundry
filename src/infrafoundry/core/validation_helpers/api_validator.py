"""Shared helper for API-driven provider validators."""

from __future__ import annotations

from typing import Any, cast

import requests
from requests import Response

from infrafoundry.core.types import EnvironmentData
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.core.validation_helpers.base_validator import BaseProviderValidator


class APIConnectivityError(Exception):
    """Raised when API connectivity validation fails."""


class BaseAPIValidator:
    """Convenience wrapper around BaseProviderValidator for API providers."""

    def __init__(
        self,
        provider_name: str,
        env_config: EnvironmentData,
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

    def api_request(
        self,
        *,
        url: str,
        check_name: str,
        method: str = "GET",
        auth: tuple[str, str] | None = None,
        headers: dict[str, str] | None = None,
        verify_ssl: bool = True,
        timeout: int = 10,
        success_message: str | None = None,
        error_message: str | None = None,
        error_level: ValidationLevel = ValidationLevel.ERROR,
        expect_ok: bool = True,
        optional: bool = False,
        **request_kwargs: Any,
    ) -> Response | None:
        """Execute an HTTP request with standardized error handling.

        Args:
            url: API endpoint to call.
            check_name: Validation check name for success/error reporting.
            method: HTTP method to use.
            auth: Optional HTTP basic auth tuple.
            headers: Optional HTTP headers.
            verify_ssl: Whether to verify SSL certificates.
            timeout: Request timeout in seconds.
            success_message: Optional message to emit when the request succeeds.
            error_message: Custom error message. Supports `{status}` and `{error}` placeholders.
            error_level: Validation level for failures.
            expect_ok: Whether non-2xx responses should be treated as failures.
            optional: If True, suppress error reporting on failures.
            **request_kwargs: Additional keyword args forwarded to `requests.request`.

        Returns:
            `requests.Response` on success, otherwise None.
        """
        try:
            response = requests.request(
                method=method,
                url=url,
                auth=auth,
                headers=headers,
                verify=verify_ssl,
                timeout=timeout,
                **request_kwargs,
            )
        except requests.exceptions.RequestException as exc:  # pragma: no cover - network errors
            if not optional:
                if error_message:
                    message = error_message.format(status="unknown", error=str(exc))
                else:
                    message = f"Error calling {url}: {exc}"
                self.add_error(
                    check_name=check_name,
                    message=message,
                    level=error_level,
                )
            return None

        if expect_ok and response.status_code >= 400:
            if not optional:
                if error_message:
                    message = error_message.format(status=response.status_code, error="")
                else:
                    message = f"{url} returned status {response.status_code}"
                self.add_error(
                    check_name=check_name,
                    message=message,
                    level=error_level,
                )
            return None

        if success_message:
            self.add_success(check_name, success_message)

        return response

    def fetch_json(
        self,
        *,
        url: str,
        check_name: str,
        method: str = "GET",
        auth: tuple[str, str] | None = None,
        headers: dict[str, str] | None = None,
        verify_ssl: bool = True,
        timeout: int = 10,
        success_message: str | None = None,
        error_message: str | None = None,
        json_error_message: str | None = None,
        error_level: ValidationLevel = ValidationLevel.ERROR,
        expect_ok: bool = True,
        optional: bool = False,
        **request_kwargs: Any,
    ) -> dict[str, Any] | None:
        """Execute an HTTP request and parse the JSON response."""
        response = self.api_request(
            url=url,
            check_name=check_name,
            method=method,
            auth=auth,
            headers=headers,
            verify_ssl=verify_ssl,
            timeout=timeout,
            success_message=success_message,
            error_message=error_message,
            error_level=error_level,
            expect_ok=expect_ok,
            optional=optional,
            **request_kwargs,
        )

        if not response:
            return None

        try:
            return cast(dict[str, Any], response.json())
        except ValueError as exc:  # pragma: no cover - JSON errors rare
            if not optional:
                if json_error_message:
                    message = json_error_message.format(status="unknown", error=str(exc))
                else:
                    message = f"Invalid JSON response from {url}: {exc}"
                self.add_error(
                    check_name=check_name,
                    message=message,
                    level=error_level,
                )
            return None
