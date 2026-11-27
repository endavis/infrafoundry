"""ACME provider: declares per-device Let's Encrypt certificates (ADR-0040).

The provider owns the resource type ``certificate``. It gives the declaration offline schema
checks, ``--provider acme`` filtering and a place in the state database. ``infra apply``
never issues a certificate: only ``foundry certs`` does, because issuing talks to a CA and
writes encrypted files into the config repo. Terraform has nothing to do here.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast, override

from infrafoundry.core.certs.dns_cloudflare import CloudflareDns, HttpSession
from infrafoundry.core.certs.models import (
    CERTIFICATE_TYPE,
    DEFAULT_RENEW_BEFORE_DAYS,
    PROVIDER_NAME,
    CertificateError,
)
from infrafoundry.core.certs.schema import raw_settings_problems, settings_from_mapping
from infrafoundry.core.certs.service import certificate_statuses
from infrafoundry.core.config.models import EnvironmentConfig
from infrafoundry.core.provider import ProviderBase, ResourceConfig
from infrafoundry.core.provider_mixins import (
    ResourceGrouperMixin,
    TemplateRendererMixin,
    TerraformGeneratorMixin,
)
from infrafoundry.core.validation import ValidationReport

from .validator import AcmeValidator

logger = logging.getLogger(__name__)

_NOTE_STATES = {
    "not issued": "has never been issued",
    "invalid": "has an unreadable stored certificate",
    "expired": "has expired",
    "due": "is due for renewal",
    "not installed": "is stored but not installed",
}


def _requests_session() -> HttpSession:
    import requests

    return cast(HttpSession, requests.Session())


class AcmeProvider(
    ProviderBase,
    TemplateRendererMixin,
    ResourceGrouperMixin,
    TerraformGeneratorMixin,
):
    """Provider for ``certificate`` resources; issued by ``foundry certs``, not by apply."""

    renders_terraform_backend = False

    def __init__(self, config_dir: Path, output_dir: Path) -> None:
        """Initialize the ACME provider."""
        super().__init__("acme", config_dir, output_dir)
        self._setup_template_environment()
        # The HTTP seam for the connectivity check; tests replace it.
        self.http_session: Callable[[], HttpSession] = _requests_session
        self.clock: Callable[[], datetime] = lambda: datetime.now(UTC)

    @override
    def get_plan_notes(self, resources: list[ResourceConfig]) -> list[str]:
        """Warn about certificates that are due, expired or never issued.

        Reads the encrypted store the package loader already decrypted; no network. It never
        raises: any problem yields fewer notes, never an exception.

        Args:
            resources: The provider's full resource list for this run

        Returns:
            One line per certificate that needs ``foundry certs renew``
        """
        try:
            window = self._renew_window()
            notes = [
                f"certificate '{s.name}' {_NOTE_STATES[s.state]}"
                + (f" ({s.days_left} days left)" if s.state == "due" else "")
                for s in certificate_statuses(resources, window, self.clock())
                if s.state in _NOTE_STATES
            ]
        except Exception as exc:
            logger.debug("acme plan notes skipped: %s", exc.__class__.__name__)
            return []
        if notes:
            notes.append("Run 'foundry certs renew' to issue or install them; apply does not.")
        return notes

    def _renew_window(self) -> int:
        """The environment's ``renew_before_days``, or the default when unreadable."""
        env_config = self._load_environment_config()
        raw = env_config.get_provider_settings(PROVIDER_NAME) if env_config else None
        value = raw.get("renew_before_days") if isinstance(raw, dict) else None
        return value if isinstance(value, int) and value > 0 else DEFAULT_RENEW_BEFORE_DAYS

    @override
    def validate_config(self, config: dict[str, Any]) -> bool:
        """Validate a certificate resource configuration (the schema checks do the work)."""
        return isinstance(config, dict)

    @override
    def get_resource_types(self) -> list[str]:
        """Get supported resource types."""
        return [CERTIFICATE_TYPE]

    @override
    def get_dependencies(self) -> dict[str, list[str]]:
        """Get resource dependencies (none)."""
        return {CERTIFICATE_TYPE: []}

    @override
    def get_terraform_resource_types(self) -> dict[str, list[str]]:
        """Map ``certificate`` to a pseudo prefix; no Terraform resource exists."""
        return {CERTIFICATE_TYPE: ["certificate"]}

    @override
    def validate_connectivity(
        self, env_config: EnvironmentConfig, report: ValidationReport
    ) -> None:
        """Check the settings, then that the Cloudflare token can reach the zone.

        The probe is one read-only DNS records call. Output names the failure, never the
        token or the zone id.
        """
        AcmeValidator(env_config, report).validate_settings()
        raw = env_config.provider_settings.get(PROVIDER_NAME)
        if raw is None or raw_settings_problems(raw):
            return
        try:
            from infrafoundry.secrets.environment import resolved_provider_settings

            settings = settings_from_mapping(
                resolved_provider_settings(env_config, PROVIDER_NAME) or {}
            )
        except CertificateError as exc:
            report.add_check("acme_cloudflare_token", False, str(exc))
            return
        except Exception as exc:
            report.add_check(
                "acme_cloudflare_token",
                False,
                f"Cannot resolve the acme secrets: {exc.__class__.__name__}",
            )
            return
        try:
            CloudflareDns(settings.api_token, settings.zone_id, self.http_session()).verify_access()
        except CertificateError as exc:
            report.add_check("acme_cloudflare_token", False, f"Cloudflare check failed: {exc}")
            return
        except Exception as exc:
            report.add_check(
                "acme_cloudflare_token",
                False,
                f"Cloudflare check failed: {exc.__class__.__name__}",
            )
            return
        report.add_check("acme_cloudflare_token", True, "Cloudflare token can read the DNS zone")

    @override
    def validate_references(
        self,
        resources: list[ResourceConfig],
        env_config: EnvironmentConfig,
        report: ValidationReport,
    ) -> None:
        """Run resource and settings checks."""
        AcmeValidator(env_config, report).validate_offline(resources)

    def validate_offline(
        self,
        resources: list[ResourceConfig],
        reference_resources: list[ResourceConfig],
        env_config: EnvironmentConfig,
        report: ValidationReport,
    ) -> None:
        """Run resource and settings checks without touching the network."""
        AcmeValidator(env_config, report).validate_offline(resources)

    @override
    def generate_terraform(self, resources: list[ResourceConfig]) -> None:
        """Write an empty ``terraform {}`` block; ``foundry certs`` does the work."""
        self.prepare_terraform_generation(resources)
        self.render_and_write_terraform("acme/main.tf.j2", output_name="main.tf")

    @override
    def generate_ansible(self, resources: list[ResourceConfig]) -> None:
        """Create the output directories; there is no Ansible content."""
        self.ensure_directories()


def register() -> Any:
    """Return provider metadata for plugin discovery.

    Returns:
        A ``ProviderMetadata`` describing the ACME provider.
    """
    from infrafoundry.providers.plugin_type import ProviderMetadata

    return ProviderMetadata(
        name="acme",
        version="0.1.0",
        description="Let's Encrypt certificates over ACME with Cloudflare DNS-01",
        provider_class=AcmeProvider,
        resource_types=[CERTIFICATE_TYPE],
    )
