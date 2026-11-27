"""ACME provider: declares per-device Let's Encrypt certificates (ADR-0040).

The provider owns the resource type ``certificate``. It gives the declaration offline schema
checks, ``--provider acme`` filtering and a place in the state database. ``infra apply``
never issues a certificate: only ``foundry certs`` does, because issuing talks to a CA and
writes encrypted files into the config repo. Terraform has nothing to do here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, override

from infrafoundry.core.certs.models import CERTIFICATE_TYPE
from infrafoundry.core.config.models import EnvironmentConfig
from infrafoundry.core.provider import ProviderBase, ResourceConfig
from infrafoundry.core.provider_mixins import (
    ResourceGrouperMixin,
    TemplateRendererMixin,
    TerraformGeneratorMixin,
)
from infrafoundry.core.validation import ValidationReport

from .validator import AcmeValidator


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
        """Nothing to probe in PR 1: the settings are checked offline."""
        AcmeValidator(env_config, report).validate_settings()

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
