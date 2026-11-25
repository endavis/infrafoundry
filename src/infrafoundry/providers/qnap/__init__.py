"""QNAP provider: manages a QNAP QSW-M series switch over its web API.

One switch per environment. ``vlan``, ``lacp.group`` and ``port`` resources are diffed against
the switch and written by ``QnapRestRunner`` through :class:`QnapConfigManager` (ADR-0039).
The ``firmware.update`` resource is never applied: it only drives the plan's update report
and ``foundry provider qnap upgrade`` (ADR-0038). Terraform has nothing to do here.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, override

from infrafoundry.core.config.models import EnvironmentConfig
from infrafoundry.core.exceptions import InfraFoundryError
from infrafoundry.core.provider import ProviderBase, ResourceConfig
from infrafoundry.core.provider_mixins import (
    ResourceGrouperMixin,
    TemplateRendererMixin,
    TerraformGeneratorMixin,
)
from infrafoundry.core.validation import ValidationReport

from .client import QnapClient
from .components.firmware import (
    FIRMWARE_ADDRESS_PREFIX,
    FIRMWARE_TYPE,
    check_firmware,
    plan_line,
)
from .components.manager import QnapApplyResult, QnapConfigManager, QnapPlan
from .schema import (
    DELETABLE_TYPES,
    LACP_ADDRESS_PREFIX,
    LACP_TYPE,
    PORT_ADDRESS_PREFIX,
    PORT_TYPE,
    VLAN_ADDRESS_PREFIX,
    VLAN_TYPE,
)
from .settings import load_settings
from .validator import QnapValidator


class QnapProvider(
    ProviderBase,
    TemplateRendererMixin,
    ResourceGrouperMixin,
    TerraformGeneratorMixin,
):
    """Provider for a QNAP switch, managed over its web JSON API."""

    renders_terraform_backend = False

    def __init__(self, config_dir: Path, output_dir: Path) -> None:
        """Initialize the QNAP provider."""
        super().__init__("qnap", config_dir, output_dir)
        self._setup_template_environment()

    @override
    def validate_config(self, config: dict[str, Any]) -> bool:
        """Validate a QNAP resource configuration (the schema checks do the work)."""
        return isinstance(config, dict)

    @override
    def get_resource_types(self) -> list[str]:
        """Get supported resource types."""
        return [VLAN_TYPE, LACP_TYPE, PORT_TYPE, FIRMWARE_TYPE]

    @override
    def get_dependencies(self) -> dict[str, list[str]]:
        """Get resource dependencies (a VLAN may list a LAG, so groups come first).

        Port settings are written last, after the VLANs and LACP groups.
        """
        return {
            LACP_TYPE: [],
            VLAN_TYPE: [LACP_TYPE],
            PORT_TYPE: [VLAN_TYPE, LACP_TYPE],
            FIRMWARE_TYPE: [],
        }

    @override
    def get_terraform_resource_types(self) -> dict[str, list[str]]:
        """Map each type to the pseudo prefix of the runner's outcome addresses."""
        return {
            VLAN_TYPE: [VLAN_ADDRESS_PREFIX],
            LACP_TYPE: [LACP_ADDRESS_PREFIX],
            PORT_TYPE: [PORT_ADDRESS_PREFIX],
            FIRMWARE_TYPE: [FIRMWARE_ADDRESS_PREFIX],
        }

    @override
    def validate_connectivity(
        self, env_config: EnvironmentConfig, report: ValidationReport
    ) -> None:
        """Check the switch answers and a login works."""
        QnapValidator(env_config, report, self.config_dir).validate_connectivity()

    @override
    def validate_references(
        self,
        resources: list[ResourceConfig],
        env_config: EnvironmentConfig,
        report: ValidationReport,
    ) -> None:
        """Run resource and settings checks."""
        QnapValidator(env_config, report, self.config_dir).validate_references(resources)

    def validate_references_in_context(
        self,
        resources: list[ResourceConfig],
        reference_resources: list[ResourceConfig],
        env_config: EnvironmentConfig,
        report: ValidationReport,
    ) -> None:
        """Validate *resources*; there are no cross-resource references."""
        QnapValidator(env_config, report, self.config_dir).validate_references(resources)

    def validate_offline(
        self,
        resources: list[ResourceConfig],
        reference_resources: list[ResourceConfig],
        env_config: EnvironmentConfig,
        report: ValidationReport,
    ) -> None:
        """Run resource and settings checks without touching the network."""
        QnapValidator(env_config, report, self.config_dir).validate_offline(resources)

    @override
    def generate_terraform(self, resources: list[ResourceConfig]) -> None:
        """Write an empty ``terraform {}`` block; the REST runner does the work."""
        self.prepare_terraform_generation(resources)
        self.render_and_write_terraform("qnap/main.tf.j2", output_name="main.tf")

    @override
    def generate_ansible(self, resources: list[ResourceConfig]) -> None:
        """Create the output directories; there is no Ansible content."""
        self.ensure_directories()

    def generate_qnap_rest(self, resources: list[ResourceConfig]) -> None:
        """Dispatch hook for ``QnapRestRunner``; the runner reads the switch itself."""

    def rest_plan(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        add_only: bool = False,
        managed_resources: Mapping[str, list[ResourceConfig]] | None = None,
        target_resources: list[str] | None = None,
    ) -> QnapPlan:
        """Plan the VLAN, LACP and port changes for the switch; called by ``QnapRestRunner``.

        Args:
            env_name: Environment name.
            resources: This provider's resources.
            add_only: Suppress deletes.
            managed_resources: Managed rows by type (ADR-0018).
            target_resources: Restrict to these resource names.
        """
        return QnapConfigManager(self.config_dir).plan(
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
    ) -> QnapApplyResult:
        """Plan against the switch, then apply the plan; called by ``QnapRestRunner``.

        Args:
            env_name: Environment name.
            resources: This provider's resources.
            add_only: Suppress deletes.
            managed_resources: Managed rows by type (ADR-0018).
            target_resources: Restrict to these resource names.
        """
        manager = QnapConfigManager(self.config_dir)
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
    ) -> QnapApplyResult:
        """Delete the declared VLANs and LACP groups that exist on the switch.

        Args:
            env_name: Environment name.
            resources: This provider's resources.
            target_resources: Restrict to these resource names.
        """
        return QnapConfigManager(self.config_dir).destroy(
            env_name, resources, target_resources=target_resources
        )

    def rest_resource_ids(self, env_name: str, resources: list[ResourceConfig]) -> dict[str, str]:
        """Return ``{resource_name: id}`` for the declared objects that exist on the switch.

        Args:
            env_name: Environment name.
            resources: This provider's resources.
        """
        return QnapConfigManager(self.config_dir).resource_ids(env_name, resources)

    @staticmethod
    def deletable_types() -> set[str]:
        """Return the resource types the provider can delete."""
        return set(DELETABLE_TYPES)

    def firmware_plan_lines(
        self, env_name: str, resources: list[ResourceConfig]
    ) -> list[tuple[str, bool]]:
        """Check the switch's firmware offer and return plan lines (ADR-0038).

        Duck-typed hook read by ``QnapRestRunner.plan``. It only reads: a failure becomes a
        warning line so an unreachable switch or update server cannot block planning.

        Args:
            env_name: Environment name.
            resources: This provider's resources.

        Returns:
            ``(line, is_warning)`` pairs; empty when no ``firmware.update`` exists.
        """
        updates = [r for r in resources if r.type == FIRMWARE_TYPE]
        if not updates:
            return []
        name = updates[0].name
        try:
            settings = load_settings(self.config_dir, env_name)
            client = QnapClient(settings)
            with client.session():
                state = check_firmware(client, settings.check_timeout)
        except (InfraFoundryError, OSError) as exc:
            return [(f"{FIRMWARE_TYPE} '{name}': update check failed: {exc}", True)]
        return [plan_line(name, state, env_name)]


def register_cli(provider_group: Any) -> None:
    """Attach the QNAP subcommands to the ``foundry provider qnap`` group.

    Args:
        provider_group: The Click group created for this provider.
    """
    # Imported here so that importing the provider does not pull in the CLI code.
    from .cli import qnap as qnap_cli_group

    for name, command in qnap_cli_group.commands.items():
        provider_group.add_command(command, name=name)


def register() -> Any:
    """Return provider metadata for plugin discovery (the ``infrafoundry.providers`` entry point).

    Returns:
        A ``ProviderMetadata`` describing the QNAP provider.
    """
    from infrafoundry.providers.plugin_type import ProviderMetadata

    return ProviderMetadata(
        name="qnap",
        version="0.1.0",
        description="QNAP QSW-M switch provider",
        provider_class=QnapProvider,
        resource_types=[VLAN_TYPE, LACP_TYPE, PORT_TYPE, FIRMWARE_TYPE],
        cli_registration=register_cli,
    )
