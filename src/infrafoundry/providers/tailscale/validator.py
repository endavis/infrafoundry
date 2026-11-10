"""Validation logic for the Tailscale provider (config checks only, no network calls)."""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any, cast

from infrafoundry.core.config.models import EnvironmentConfig
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.types import TailscaleProviderSettings
from infrafoundry.core.validation import ValidationReport, run_validators
from infrafoundry.core.validation_helpers import BaseAPIValidator

from .validators import (
    AclValidator,
    CredentialsValidator,
    DeviceReferenceValidator,
    DnsValidator,
    NamingValidator,
    TailnetKeyValidator,
)
from .validators.context import TailscaleConfigContext, TailscaleCredentialsContext


def detect_auth_mode(
    provider_settings: Mapping[str, Any], environ: Mapping[str, str] | None = None
) -> str:
    """Return the auth mode the provider block will run with.

    Args:
        provider_settings: ``provider_settings.tailscale`` (URIs unresolved).
        environ: Environment to consult for the provider's own fallbacks;
            defaults to ``os.environ``.

    Returns:
        ``"oauth"`` when ``oauth_client_id`` is set or ``TAILSCALE_OAUTH_CLIENT_ID``
        is, else ``"api_key"`` when ``api_key`` or ``TAILSCALE_API_KEY`` is set,
        else ``"unset"``.
    """
    env = os.environ if environ is None else environ
    if provider_settings.get("oauth_client_id") or env.get("TAILSCALE_OAUTH_CLIENT_ID"):
        return "oauth"
    if provider_settings.get("api_key") or env.get("TAILSCALE_API_KEY"):
        return "api_key"
    return "unset"


def acl_policy_of(resources: list[ResourceConfig]) -> dict[str, Any] | None:
    """Return the structured policy of the declared ``acl`` resource, if any."""
    for resource in resources:
        if resource.type == "acl" and isinstance(resource.config.get("policy"), dict):
            return cast(dict[str, Any], resource.config["policy"])
    return None


class TailscaleValidator:
    """Validates Tailscale configuration.

    Credential checks look at settings only; no token exchange or API call is made.
    """

    def __init__(self, env_config: EnvironmentConfig, report: ValidationReport) -> None:
        """Initialize the Tailscale validator.

        Args:
            env_config: Environment configuration including provider_settings
            report: ValidationReport to add results to
        """
        self.env_config = env_config
        self.report = report
        self.api_validator = BaseAPIValidator("tailscale", env_config, report)
        self.provider_settings = cast(
            TailscaleProviderSettings, self.api_validator.provider_settings
        )

    def validate_connectivity(self) -> None:
        """Check the credential settings are consistent (no network call)."""
        CredentialsValidator(self.report).validate(
            TailscaleCredentialsContext(
                provider_settings=cast(dict[str, Any], self.provider_settings),
                env_oauth=bool(os.environ.get("TAILSCALE_OAUTH_CLIENT_ID")),
                env_api_key=bool(os.environ.get("TAILSCALE_API_KEY")),
            )
        )

    def validate_references(self, resources: list[ResourceConfig]) -> None:
        """Run every resource-config validator.

        Args:
            resources: Resources to validate
        """
        context = TailscaleConfigContext(
            resources=resources,
            auth_mode=detect_auth_mode(cast(dict[str, Any], self.provider_settings)),
            acl_policy=acl_policy_of(resources),
        )
        report = self.report
        run_validators(
            (
                NamingValidator(report),
                AclValidator(report),
                TailnetKeyValidator(report),
                DeviceReferenceValidator(report),
                DnsValidator(report),
            ),
            context,
        )
