"""Credential-shape validation for the Tailscale provider (config only, no network)."""

from __future__ import annotations

from typing import override

from infrafoundry.core.protocols import SpecializedValidator
from infrafoundry.core.validation import ValidationLevel, ValidationReport

from ._common import fail
from .context import TailscaleCredentialsContext


class CredentialsValidator(SpecializedValidator[TailscaleCredentialsContext]):
    """Checks the credential settings are consistent. ``secret://`` URIs are not resolved."""

    def __init__(self, report: ValidationReport) -> None:
        """Initialize the validator.

        Args:
            report: ValidationReport to add results to
        """
        self.report = report

    @override
    def validate(self, context: TailscaleCredentialsContext) -> None:
        """Check the credential settings.

        Args:
            context: Settings and fallback environment-variable presence.
        """
        settings = context.provider_settings
        client_id = bool(settings.get("oauth_client_id"))
        client_secret = bool(settings.get("oauth_client_secret"))
        api_key = bool(settings.get("api_key"))
        oauth = client_id or client_secret or context.env_oauth
        if api_key and (client_id or client_secret):
            fail(
                self.report,
                "tailscale_credentials_conflict",
                "provider_settings.tailscale sets api_key together with oauth_client_*; "
                "the provider accepts one auth method",
            )
        if client_id != client_secret and not context.env_oauth:
            fail(
                self.report,
                "tailscale_credentials_oauth_pair",
                "provider_settings.tailscale needs both oauth_client_id and oauth_client_secret",
            )
        if settings.get("scopes") and not oauth:
            fail(
                self.report,
                "tailscale_credentials_scopes",
                "provider_settings.tailscale.scopes only applies to OAuth credentials",
            )
        if not (client_id or client_secret or api_key or context.env_oauth or context.env_api_key):
            fail(
                self.report,
                "tailscale_credentials_missing",
                "No Tailscale credentials in provider_settings.tailscale and no TAILSCALE_* "
                "fallback environment variables set",
                ValidationLevel.WARNING,
            )
            return
        self.report.add_check(
            check_name="tailscale_credentials",
            passed=True,
            message="Tailscale credential settings are consistent",
            level=ValidationLevel.INFO,
        )
