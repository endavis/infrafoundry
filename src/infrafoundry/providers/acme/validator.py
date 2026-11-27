"""Offline validation for the ACME provider: resources, settings and secret references."""

from __future__ import annotations

from typing import Any

from infrafoundry.core.certs.models import PROVIDER_NAME
from infrafoundry.core.certs.schema import check_certificates, raw_settings_problems
from infrafoundry.core.config.models import EnvironmentConfig
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationReport
from infrafoundry.secrets.environment import SecretRefLookup
from infrafoundry.secrets.resolver import is_secret_uri


class AcmeValidator:
    """Validates ``certificate`` resources and ``provider_settings.acme`` without a network."""

    def __init__(self, env_config: EnvironmentConfig, report: ValidationReport) -> None:
        """Initialize the validator.

        Args:
            env_config: Environment configuration (holds the decrypted secrets).
            report: Report to add findings to.
        """
        self.env_config = env_config
        self.report = report

    def validate_offline(self, resources: list[ResourceConfig]) -> None:
        """Check the certificate resources, then the settings when any is declared."""
        certificates = [r for r in resources if r.type == "certificate"]
        for finding in check_certificates(resources):
            self.report.add_check(
                check_name=f"acme_schema_{finding.resource}",
                passed=False,
                message=finding.message,
                level=finding.level,
            )
        if certificates:
            self.validate_settings()

    def validate_settings(self) -> None:
        """Check the settings shape and that each ``secret://`` reference resolves."""
        raw: dict[str, Any] | None = self.env_config.provider_settings.get(PROVIDER_NAME)
        for index, problem in enumerate(raw_settings_problems(raw)):
            self.report.add_check(f"acme_settings_{index}", False, problem)
        cloudflare = (raw or {}).get("cloudflare")
        if not isinstance(cloudflare, dict):
            return
        with SecretRefLookup(self.env_config) as lookup:
            for key in ("api_token", "zone_id"):
                value = cloudflare.get(key)
                if isinstance(value, str) and is_secret_uri(value):
                    unresolved = lookup.problem(value)
                    if unresolved:
                        self.report.add_check(
                            f"acme_secret_{key}",
                            False,
                            f"provider_settings.acme.cloudflare.{key}: {unresolved}",
                        )
