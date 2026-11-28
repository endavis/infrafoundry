"""ONTAP provider: manages NetApp ONTAP data LIFs natively over the cluster's REST API.

InfraFoundry reads the cluster through pynetappfoundry (the optional
``infrafoundry[netapp]`` extra), diffs the declared ``network.ip.interface`` resources
against it and creates, updates or deletes LIFs, stopping at the first error. Terraform
has nothing to do here; ``OntapRestRunner`` plans, applies and destroys, as for MikroTik
(ADR-0026). Product siblings (``aiqum``, ``dii``, ``console``) share the service layer in
``providers/_netapp`` (ADR-0042).

Importing this package never imports pynetappfoundry: the provider always registers and a
core-only install fails clearly at plan time.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, override

from infrafoundry.core.certs.install import CertificateTarget
from infrafoundry.core.certs.models import CertificateInstallError
from infrafoundry.core.config.models import EnvironmentConfig
from infrafoundry.core.exceptions import InfraFoundryError
from infrafoundry.core.provider import ProviderBase, ResourceConfig
from infrafoundry.core.provider_mixins import (
    ResourceGrouperMixin,
    TemplateRendererMixin,
    TerraformGeneratorMixin,
)
from infrafoundry.core.validation import ValidationReport

from .components.certificate import OntapCertificateInstaller
from .components.manager import OntapApplyResult, OntapManager, OntapPlan
from .schema import SLUG, TYPE_NAME
from .settings import load_settings
from .validator import OntapValidator


class OntapProvider(
    ProviderBase,
    TemplateRendererMixin,
    ResourceGrouperMixin,
    TerraformGeneratorMixin,
):
    """Provider for a NetApp ONTAP cluster, managed over the REST API."""

    renders_terraform_backend = False

    def install_certificate(
        self, target: CertificateTarget, cert_pem: str, chain_pem: str, key_pem: str
    ) -> None:
        """Install an ACME certificate on the cluster or an SVM over REST and verify it (#1684).

        Args:
            target: The resolved install target; ``env`` names the environment whose
                ``provider_settings.ontap`` reach the cluster.
            cert_pem: The leaf certificate.
            chain_pem: The intermediate chain (may be empty).
            key_pem: The private key. Never logged.

        Raises:
            CertificateInstallError: If the install fails or the environment is unknown. The
                message holds no key material.
        """
        if not target.env:
            raise CertificateInstallError("the install target carries no environment name")
        try:
            settings = load_settings(self.config_dir, target.env)
        except InfraFoundryError as exc:
            raise CertificateInstallError(f"ontap settings are unusable: {exc}") from None
        OntapCertificateInstaller(settings).install(target, cert_pem, chain_pem, key_pem)

    def __init__(self, config_dir: Path, output_dir: Path) -> None:
        """Initialize the ONTAP provider."""
        super().__init__("ontap", config_dir, output_dir)
        self._setup_template_environment()

    @override
    def validate_config(self, config: dict[str, Any]) -> bool:
        """Validate an ONTAP resource configuration (the schema checks do the work)."""
        return isinstance(config, dict)

    @override
    def get_resource_types(self) -> list[str]:
        """Get supported resource types."""
        return [TYPE_NAME]

    @override
    def get_dependencies(self) -> dict[str, list[str]]:
        """Get resource dependencies."""
        return {TYPE_NAME: []}

    @override
    def get_terraform_resource_types(self) -> dict[str, list[str]]:
        """Map each type to the pseudo prefix of the runner's outcome addresses."""
        return {TYPE_NAME: [f"ontap_{SLUG}"]}

    @override
    def validate_connectivity(
        self, env_config: EnvironmentConfig, report: ValidationReport
    ) -> None:
        """Check the cluster answers over REST and report its ONTAP version."""
        OntapValidator(env_config, report, self.config_dir).validate_connectivity()

    @override
    def validate_references(
        self,
        resources: list[ResourceConfig],
        env_config: EnvironmentConfig,
        report: ValidationReport,
    ) -> None:
        """Run schema and settings checks, then check the SVMs, nodes and ports exist."""
        OntapValidator(env_config, report, self.config_dir).validate_references(resources)

    def validate_references_in_context(
        self,
        resources: list[ResourceConfig],
        reference_resources: list[ResourceConfig],
        env_config: EnvironmentConfig,
        report: ValidationReport,
    ) -> None:
        """Validate *resources*; LIFs reference cluster objects, so the context is unused."""
        OntapValidator(env_config, report, self.config_dir).validate_references(
            resources, reference_resources
        )

    def validate_offline(
        self,
        resources: list[ResourceConfig],
        reference_resources: list[ResourceConfig],
        env_config: EnvironmentConfig,
        report: ValidationReport,
    ) -> None:
        """Run schema, settings and spec checks without touching the network."""
        OntapValidator(env_config, report, self.config_dir).validate_offline(resources)

    @override
    def generate_terraform(self, resources: list[ResourceConfig]) -> None:
        """Write an empty ``terraform {}`` block; the REST runner does the work."""
        self.prepare_terraform_generation(resources)
        self.render_and_write_terraform("ontap/main.tf.j2", output_name="main.tf")

    @override
    def generate_ansible(self, resources: list[ResourceConfig]) -> None:
        """Create the output directories; there is no Ansible content."""
        self.ensure_directories()

    def generate_ontap_rest(self, resources: list[ResourceConfig]) -> None:
        """Dispatch hook for ``OntapRestRunner``; the runner reads the cluster itself."""

    def rest_plan(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        add_only: bool = False,
        managed_resources: Mapping[str, list[ResourceConfig]] | None = None,
        target_resources: list[str] | None = None,
    ) -> OntapPlan:
        """Plan the changes for the cluster; called by ``OntapRestRunner``.

        Args:
            env_name: Environment name.
            resources: This provider's resources.
            add_only: Suppress deletes.
            managed_resources: Managed rows by type (ADR-0018).
            target_resources: Restrict to these resource names.
        """
        return OntapManager(self.config_dir).plan(
            env_name,
            resources,
            add_only=add_only,
            managed_resources=managed_resources,
            target_resources=target_resources,
        )

    def rest_apply(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        add_only: bool = False,
        managed_resources: Mapping[str, list[ResourceConfig]] | None = None,
        target_resources: list[str] | None = None,
    ) -> OntapApplyResult:
        """Plan against the cluster, then apply the plan; called by ``OntapRestRunner``.

        Args:
            env_name: Environment name.
            resources: This provider's resources.
            add_only: Suppress deletes.
            managed_resources: Managed rows by type (ADR-0018).
            target_resources: Restrict to these resource names.
        """
        manager = OntapManager(self.config_dir)
        plan = manager.plan(
            env_name,
            resources,
            add_only=add_only,
            managed_resources=managed_resources,
            target_resources=target_resources,
        )
        return manager.apply(env_name, plan)

    def rest_destroy(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        target_resources: list[str] | None = None,
    ) -> OntapApplyResult:
        """Delete the declared LIFs that exist on the cluster.

        Args:
            env_name: Environment name.
            resources: This provider's resources.
            target_resources: Restrict to these resource names.
        """
        return OntapManager(self.config_dir).destroy(
            env_name, resources, target_resources=target_resources
        )

    def rest_resource_ids(self, env_name: str, resources: list[ResourceConfig]) -> dict[str, str]:
        """Return ``{resource_name: uuid}`` for the declared LIFs that exist live.

        Args:
            env_name: Environment name.
            resources: This provider's resources.
        """
        return OntapManager(self.config_dir).resource_ids(env_name, resources)

    @staticmethod
    def deletable_types() -> set[str]:
        """Return the resource types the provider can delete."""
        return {TYPE_NAME}


def register() -> Any:
    """Return provider metadata for plugin discovery (the ``infrafoundry.providers`` entry point).

    Returns:
        A ``ProviderMetadata`` describing the ONTAP provider.
    """
    from infrafoundry.providers.plugin_type import ProviderMetadata

    return ProviderMetadata(
        name="ontap",
        version="0.1.0",
        description="NetApp ONTAP provider",
        provider_class=OntapProvider,
        resource_types=[TYPE_NAME],
    )
