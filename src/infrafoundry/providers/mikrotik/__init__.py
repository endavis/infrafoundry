"""MikroTik RouterOS provider: manages a device natively over its REST API.

InfraFoundry reads the device through ``/rest``, diffs the declared objects against
it and applies them in a lock-out-safe order, stopping at the first error. Terraform has
nothing to do here; ``MikroTikRestRunner`` plans, applies and destroys (ADR-0026).
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, override

from infrafoundry.core.config.models import EnvironmentConfig
from infrafoundry.core.provider import ProviderBase, ResourceConfig
from infrafoundry.core.provider_mixins import (
    ResourceGrouperMixin,
    TemplateRendererMixin,
    TerraformGeneratorMixin,
)
from infrafoundry.core.validation import ValidationReport

from .components.manager import MikroTikApplyResult, MikroTikManager, MikroTikPlan
from .schema import SPECS
from .validator import MikroTikValidator


class MikroTikProvider(
    ProviderBase,
    TemplateRendererMixin,
    ResourceGrouperMixin,
    TerraformGeneratorMixin,
):
    """Provider for a MikroTik RouterOS device, managed over the REST API."""

    renders_terraform_backend = False

    def __init__(self, config_dir: Path, output_dir: Path) -> None:
        """Initialize the MikroTik provider."""
        super().__init__("mikrotik", config_dir, output_dir)
        self._setup_template_environment()

    @override
    def validate_config(self, config: dict[str, Any]) -> bool:
        """Validate a MikroTik resource configuration (the schema checks do the work)."""
        return isinstance(config, dict)

    @override
    def get_resource_types(self) -> list[str]:
        """Get supported resource types."""
        return list(SPECS)

    @override
    def get_dependencies(self) -> dict[str, list[str]]:
        """Get resource dependencies."""
        return {
            "interface.bridge": [],
            "interface.bridge.port": ["interface.bridge"],
            "interface.bridge.vlan": ["interface.bridge"],
            "interface.vlan": ["interface.bridge"],
            "ip.address": ["interface.vlan"],
            "ip.dhcp-client": ["interface.vlan"],
            "ip.service": [],
        }

    @override
    def get_terraform_resource_types(self) -> dict[str, list[str]]:
        """Map each type to the pseudo prefix of the runner's outcome addresses."""
        return {name: [f"mikrotik_{spec.slug}"] for name, spec in SPECS.items()}

    @override
    def validate_connectivity(
        self, env_config: EnvironmentConfig, report: ValidationReport
    ) -> None:
        """Check the device answers over REST and runs RouterOS 7 or later."""
        MikroTikValidator(env_config, report, self.config_dir).validate_connectivity()

    @override
    def validate_references(
        self,
        resources: list[ResourceConfig],
        env_config: EnvironmentConfig,
        report: ValidationReport,
    ) -> None:
        """Run schema, settings and interface-reference checks."""
        MikroTikValidator(env_config, report, self.config_dir).validate_references(resources)

    def validate_references_in_context(
        self,
        resources: list[ResourceConfig],
        reference_resources: list[ResourceConfig],
        env_config: EnvironmentConfig,
        report: ValidationReport,
    ) -> None:
        """Validate *resources*, resolving names against *reference_resources* (#1568)."""
        MikroTikValidator(env_config, report, self.config_dir).validate_references(
            resources, reference_resources
        )

    def validate_offline(
        self,
        resources: list[ResourceConfig],
        reference_resources: list[ResourceConfig],
        env_config: EnvironmentConfig,
        report: ValidationReport,
    ) -> None:
        """Run schema and settings checks without touching the network."""
        MikroTikValidator(env_config, report, self.config_dir).validate_offline(resources)

    @override
    def generate_terraform(self, resources: list[ResourceConfig]) -> None:
        """Write an empty ``terraform {}`` block; the REST runner does the work."""
        self.prepare_terraform_generation(resources)
        self.render_and_write_terraform("mikrotik/main.tf.j2", output_name="main.tf")

    @override
    def generate_ansible(self, resources: list[ResourceConfig]) -> None:
        """Create the output directories; there is no Ansible content."""
        self.ensure_directories()

    def generate_mikrotik_rest(self, resources: list[ResourceConfig]) -> None:
        """Dispatch hook for ``MikroTikRestRunner``; the runner reads the device itself."""

    def rest_plan(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        add_only: bool = False,
        managed_resources: Mapping[str, list[ResourceConfig]] | None = None,
        target_resources: list[str] | None = None,
    ) -> MikroTikPlan:
        """Plan the changes for the device; called by ``MikroTikRestRunner``.

        Args:
            env_name: Environment name.
            resources: This provider's resources.
            add_only: Suppress deletes.
            managed_resources: Managed rows by type (ADR-0018).
            target_resources: Restrict to these resource names.
        """
        return MikroTikManager(self.config_dir).plan(
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
    ) -> MikroTikApplyResult:
        """Plan against the device, then apply the plan; called by ``MikroTikRestRunner``.

        Args:
            env_name: Environment name.
            resources: This provider's resources.
            add_only: Suppress deletes.
            managed_resources: Managed rows by type (ADR-0018).
            target_resources: Restrict to these resource names.
        """
        manager = MikroTikManager(self.config_dir)
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
    ) -> MikroTikApplyResult:
        """Delete the declared objects that exist on the device.

        Args:
            env_name: Environment name.
            resources: This provider's resources.
            target_resources: Restrict to these resource names.
        """
        return MikroTikManager(self.config_dir).destroy(
            env_name, resources, target_resources=target_resources
        )

    def rest_resource_ids(self, env_name: str, resources: list[ResourceConfig]) -> dict[str, str]:
        """Return ``{resource_name: .id}`` for the declared objects that exist live.

        Args:
            env_name: Environment name.
            resources: This provider's resources.
        """
        return MikroTikManager(self.config_dir).resource_ids(env_name, resources)

    @staticmethod
    def deletable_types() -> set[str]:
        """Return the resource types the provider can delete."""
        return {name for name, spec in SPECS.items() if spec.deletable}
