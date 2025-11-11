"""API connectivity validation for infrastructure providers.

This module handles testing HTTP/API connectivity with proper error handling
and standardized reporting.
"""

import logging
from typing import Any

from infrafoundry.core.validation import ValidationLevel, ValidationReport

logger = logging.getLogger(__name__)


class ConnectivityValidator:
    """Tests API connectivity and handles HTTP responses.

    Provides standardized connectivity testing with:
    - Multiple HTTP methods support
    - Authentication (basic auth, custom headers)
    - SSL verification control
    - Timeout handling
    - Detailed error reporting for common HTTP status codes

    Example:
        validator = ConnectivityValidator("proxmox", report)
        success = validator.check_api_connectivity(
            url="https://pve.example.com:8006/api2/json/version",
            headers={"Authorization": f"PVEAPIToken={token}"},
            verify_ssl=False
        )
    """

    def __init__(self, provider_name: str, report: ValidationReport):
        """Initialize connectivity validator.

        Args:
            provider_name: Provider name for error messages
            report: ValidationReport to add results to
        """
        self.provider_name = provider_name
        self.report = report

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
            success_message: Custom success message

        Returns:
            True if API is reachable and returns 200, False otherwise
        """
        # Check if requests library is available
        try:
            import requests
        except ImportError:
            self._add_requests_missing_error()
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

            return self._handle_response(response, url, success_message)

        except requests.exceptions.Timeout:
            self._add_timeout_error(url, timeout)
            return False

        except requests.exceptions.ConnectionError as e:
            self._add_connection_error(url, e)
            return False

        except Exception as e:
            self._add_unexpected_error(url, e)
            return False

    def _handle_response(
        self,
        response: Any,
        url: str,
        success_message: str | None,
    ) -> bool:
        """Handle HTTP response and add appropriate validation check.

        Args:
            response: HTTP response object
            url: URL that was requested
            success_message: Optional custom success message

        Returns:
            True if successful (200), False otherwise
        """
        if response.status_code == 200:
            msg = success_message or f"Successfully connected to {self.provider_name} API at {url}"
            self.report.add_check(
                check_name=f"{self.provider_name}_connectivity",
                passed=True,
                message=msg,
                level=ValidationLevel.INFO,
            )
            return True

        elif response.status_code == 401:
            self._add_unauthorized_error()
            return False

        elif response.status_code == 403:
            self._add_forbidden_error()
            return False

        else:
            self._add_http_error(response.status_code, url)
            return False

    def _add_requests_missing_error(self) -> None:
        """Add validation error for missing requests library."""
        self.report.add_check(
            check_name=f"{self.provider_name}_connectivity",
            passed=False,
            message="requests library not installed (required for API validation)",
            level=ValidationLevel.ERROR,
        )

    def _add_unauthorized_error(self) -> None:
        """Add validation error for 401 Unauthorized."""
        self.report.add_check(
            check_name=f"{self.provider_name}_connectivity",
            passed=False,
            message=f"{self.provider_name.title()} API credentials invalid (401 Unauthorized)",
            level=ValidationLevel.ERROR,
        )

    def _add_forbidden_error(self) -> None:
        """Add validation error for 403 Forbidden."""
        self.report.add_check(
            check_name=f"{self.provider_name}_connectivity",
            passed=False,
            message=f"{self.provider_name.title()} API access forbidden (403 Forbidden)",
            level=ValidationLevel.ERROR,
        )

    def _add_http_error(self, status_code: int, url: str) -> None:
        """Add validation error for unexpected HTTP status code."""
        self.report.add_check(
            check_name=f"{self.provider_name}_connectivity",
            passed=False,
            message=f"Failed to connect: HTTP {status_code}",
            level=ValidationLevel.ERROR,
            details={"status_code": status_code, "url": url},
        )

    def _add_timeout_error(self, url: str, timeout: int) -> None:
        """Add validation error for connection timeout."""
        self.report.add_check(
            check_name=f"{self.provider_name}_connectivity",
            passed=False,
            message=f"Connection timeout after {timeout}s",
            level=ValidationLevel.ERROR,
            details={"url": url, "timeout": timeout},
        )

    def _add_connection_error(self, url: str, error: Exception) -> None:
        """Add validation error for connection failure."""
        self.report.add_check(
            check_name=f"{self.provider_name}_connectivity",
            passed=False,
            message=f"Connection failed: {error}",
            level=ValidationLevel.ERROR,
            details={"url": url},
        )

    def _add_unexpected_error(self, url: str, error: Exception) -> None:
        """Add validation error for unexpected exception."""
        self.report.add_check(
            check_name=f"{self.provider_name}_connectivity",
            passed=False,
            message=f"Unexpected error testing connectivity: {error}",
            level=ValidationLevel.ERROR,
            details={"url": url, "error_type": type(error).__name__},
        )
