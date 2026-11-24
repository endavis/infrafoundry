"""OpenWrt provider: manages one or several devices through generated playbooks.

The playbooks use the ``community.openwrt`` collection.

The provider writes an inventory, an ``ansible.cfg`` and ``openwrt.yml``. The playbook
stages UCI changes without committing; ``OpenWrtAnsibleRunner`` runs it in check mode
for ``plan`` and for the pre-apply check, and for real on ``apply`` and ``destroy``.
The real run commits through ``ubus call uci apply`` with rollback and confirms after
reconnecting (ADR-0028). Each device is a provider instance (ADR-0035).
Terraform has nothing to do here.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Self, override

import yaml

from infrafoundry.core.config.models import EnvironmentConfig
from infrafoundry.core.exceptions import SchemaValidationError
from infrafoundry.core.provider import ProviderBase, ResourceConfig
from infrafoundry.core.provider_instances import qualified_provider_id
from infrafoundry.core.provider_mixins import (
    ResourceGrouperMixin,
    TemplateRendererMixin,
    TerraformGeneratorMixin,
)
from infrafoundry.core.requirements.models import CollectionRequirement
from infrafoundry.core.validation import ValidationReport

from .components._managed import managed_index
from .components.playbook import PLAYBOOK_NAME, build_playbook, dump_playbook
from .components.results import (
    OpenWrtRunResult,
    RunSpec,
    interpret,
    parse_output,
)
from .devices import device_label
from .schema import SPECS, Desired, check_resources, desired_from_resources
from .settings import PROVIDER_NAME, OpenWrtSettings, load_settings
from .validator import COLLECTION, OpenWrtValidator

INVENTORY_HOST = "openwrt"
ANSIBLE_CFG = (
    "[defaults]\n"
    "host_key_checking = True\n"
    "retry_files_enabled = False\n"
    "\n"
    "[ssh_connection]\n"
    "pipelining = True\n"
    "transfer_method = smart\n"
)

Mode = Literal["apply", "destroy"]


@dataclass
class RenderedRun:
    """The files written for one run and what they ask the device to do."""

    ansible_dir: Path
    settings: OpenWrtSettings
    spec: RunSpec
    tags: list[str] = field(default_factory=list)

    @property
    def playbook(self) -> str:
        """The playbook file name inside ``ansible_dir``."""
        return PLAYBOOK_NAME


class OpenWrtProvider(
    ProviderBase,
    TemplateRendererMixin,
    ResourceGrouperMixin,
    TerraformGeneratorMixin,
):
    """Provider for one OpenWrt device, managed over SSH with Ansible.

    With ``provider_settings.openwrt.devices`` declared, each extra device is another
    instance named ``openwrt@<device>``.
    """

    renders_terraform_backend = False

    def __init__(self, config_dir: Path, output_dir: Path, device: str | None = None) -> None:
        """Initialize the OpenWrt provider.

        Args:
            config_dir: Configuration directory.
            output_dir: Base output directory.
            device: Device name for a non-primary instance (``openwrt@<device>``).
        """
        super().__init__(qualified_provider_id(PROVIDER_NAME, device), config_dir, output_dir)
        self._setup_template_environment()
        self._label_cache: dict[str, str | None] = {}

    def spawn_instance(self, name: str) -> Self:
        """Return a provider for the named device instance (#1656).

        Args:
            name: Device name from ``provider_settings.openwrt.devices``.

        Returns:
            A new provider named ``openwrt@<name>`` sharing this provider's directories.
        """
        instance = type(self)(self.config_dir, self.base_output_dir, device=name)
        current = getattr(self, "_current_environment", None)
        if current:
            instance.set_environment(current)
        return instance

    def device_label(self, env_name: str) -> str | None:
        """Return the device name for output labels, or ``None`` for a flat config (#1656).

        Duck-typed hook read by ``OpenWrtAnsibleRunner``. The result is cached per environment.

        Args:
            env_name: Environment whose settings declare the devices.
        """
        if env_name not in self._label_cache:
            from infrafoundry.core.config import ConfigManager

            try:
                env_config = ConfigManager(self.config_dir).load_environment(env_name)
            except (FileNotFoundError, OSError):
                label = None
            else:
                label = device_label(env_config, self.name)
            self._label_cache[env_name] = label
        return self._label_cache[env_name]

    def _run_labelled(
        self,
        env_config: EnvironmentConfig,
        report: ValidationReport,
        checks: Callable[[OpenWrtValidator], None],
    ) -> None:
        """Run ``checks`` for this device, prefixing its new results with ``[<device>] ``."""
        validator = OpenWrtValidator(env_config, report, self.config_dir, provider_name=self.name)
        start = len(report.results)
        checks(validator)
        label = device_label(env_config, self.name)
        if label is None:
            return
        for result in report.results[start:]:
            result.message = f"[{label}] {result.message}"

    @override
    def validate_config(self, config: dict[str, Any]) -> bool:
        """Validate an OpenWrt resource configuration (the schema checks do the work)."""
        return isinstance(config, dict)

    @override
    def get_resource_types(self) -> list[str]:
        """Get supported resource types."""
        return list(SPECS)

    @override
    def get_dependencies(self) -> dict[str, list[str]]:
        """Get resource dependencies; UCI stages and commits every type together."""
        return {name: [] for name in SPECS}

    @override
    def get_terraform_resource_types(self) -> dict[str, list[str]]:
        """Map each type to the pseudo prefix of the runner's outcome addresses."""
        return {name: [f"openwrt_{spec.slug}"] for name, spec in SPECS.items()}

    @override
    def ansible_collection_requirements(self) -> tuple[CollectionRequirement, ...]:
        """Return the collection the generated playbooks use."""
        return (COLLECTION,)

    @override
    def validate_connectivity(
        self, env_config: EnvironmentConfig, report: ValidationReport
    ) -> None:
        """Check the controller tools and probe the device read-only."""
        self._run_labelled(env_config, report, lambda v: v.validate_connectivity())

    @override
    def validate_references(
        self,
        resources: list[ResourceConfig],
        env_config: EnvironmentConfig,
        report: ValidationReport,
    ) -> None:
        """Run schema and settings checks."""
        self._run_labelled(env_config, report, lambda v: v.validate_references(resources))

    def validate_offline(
        self,
        resources: list[ResourceConfig],
        reference_resources: list[ResourceConfig],
        env_config: EnvironmentConfig,
        report: ValidationReport,
    ) -> None:
        """Run schema and settings checks without touching the network."""
        self._run_labelled(env_config, report, lambda v: v.validate_offline(resources))

    @override
    def generate_terraform(self, resources: list[ResourceConfig]) -> None:
        """Write an empty ``terraform {}`` block; the Ansible runner does the work."""
        self.prepare_terraform_generation(resources)
        self.render_and_write_terraform("openwrt/main.tf.j2", output_name="main.tf")

    @override
    def generate_ansible(self, resources: list[ResourceConfig]) -> None:
        """Create the output directories; ``render_run`` writes the files per run."""
        self.ensure_directories()

    def generate_openwrt_ansible(self, resources: list[ResourceConfig]) -> None:
        """Dispatch hook for ``OpenWrtAnsibleRunner``; the runner renders each run itself."""

    def render_run(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        mode: Mode = "apply",
        add_only: bool = False,
        managed_resources: Mapping[str, list[ResourceConfig]] | None = None,
        target_resources: list[str] | None = None,
    ) -> RenderedRun:
        """Write the inventory, ``ansible.cfg`` and ``openwrt.yml`` for one run.

        Args:
            env_name: Environment name.
            resources: This provider's resources.
            mode: ``apply`` stages the declared objects; ``destroy`` deletes them.
            add_only: Suppress deletes of managed rows that are no longer declared.
            managed_resources: Managed rows by type (ADR-0018).
            target_resources: Restrict to these resource names; implies add-only.

        Returns:
            The run's directory, settings, interpretation spec and ``--tags``.

        Raises:
            SchemaValidationError: If a resource is invalid.
            OpenWrtSettingsError: If the settings are missing or invalid.
        """
        settings = load_settings(self.config_dir, env_name, self.name)
        errors = [f.message for f in check_resources(resources, settings)]
        if errors:
            raise SchemaValidationError("OpenWrt configuration is invalid:\n" + "\n".join(errors))
        declared = desired_from_resources([r for r in resources if r.type in SPECS])
        targets = set(target_resources or ())
        selected = [d for d in declared if not targets or d.name in targets]
        index = managed_index(managed_resources, declared)
        spec = self._run_spec(mode, selected, index, add_only or bool(targets))
        self.ensure_directories()
        self._write_ansible_file("ansible.cfg", ANSIBLE_CFG)
        self._write_ansible_file("inventory.yml", self._render_inventory(settings))
        play = build_playbook(settings, spec.items)
        self._write_ansible_file(PLAYBOOK_NAME, dump_playbook(play))
        tags = sorted({d.name for d in spec.items}) if targets else []
        spec.tags = tags
        return RenderedRun(self.ansible_dir, settings, spec, tags)

    @staticmethod
    def _run_spec(mode: Mode, selected: list[Desired], index: Any, add_only: bool) -> RunSpec:
        if mode == "destroy":
            items = [
                Desired(d.spec, d.name, d.key, {}, absent=True)
                for d in selected
                if d.spec.deletable
            ]
            return RunSpec(
                mode=mode,
                items=items,
                managed_names=index.names,
                forgotten_items=[d for d in selected if not d.spec.deletable],
            )
        items = list(selected)
        removal_names: set[str] = set()
        forgotten = []
        if not add_only:
            items.extend(index.removals)
            removal_names = {r.name for r in index.removals}
            forgotten = list(index.forgotten)
        return RunSpec(
            mode=mode,
            items=items,
            managed_names=index.names,
            removal_names=removal_names,
            forgotten=forgotten,
        )

    @staticmethod
    def _render_inventory(settings: OpenWrtSettings) -> str:
        """Render the inventory; it holds the address, port, user and key path only.

        Every connection checks the device's host key under the settings address
        (``HostKeyAlias``), so the reconnect after a management-address change is
        checked against the same known key instead of failing on an unknown host.
        """
        entry: dict[str, Any] = {
            "ansible_host": settings.address,
            "ansible_port": settings.ssh_port,
            "ansible_user": settings.ssh_user,
            "ansible_ssh_common_args": f"-o HostKeyAlias={settings.address}",
        }
        if settings.ssh_private_key_file:
            entry["ansible_ssh_private_key_file"] = settings.ssh_private_key_file
        return yaml.safe_dump({"all": {"hosts": {INVENTORY_HOST: entry}}}, sort_keys=False)

    @staticmethod
    def parse_run(
        raw: str, run: RenderedRun, *, check: bool, resolve: Any = None
    ) -> OpenWrtRunResult:
        """Interpret the JSON output of a run.

        Args:
            raw: Captured stdout of ``ansible-playbook`` with the JSON callback.
            run: The result of :meth:`render_run` for the run.
            check: True for a check-mode pass.
            resolve: Resolver for the settings address, replaced in tests.

        Raises:
            ResultsError: If the output is not the JSON document.
        """
        return interpret(
            parse_output(raw), run.spec, address=run.settings.address, check=check, resolve=resolve
        )

    @staticmethod
    def deletable_types() -> set[str]:
        """Return the resource types the provider can delete."""
        return {name for name, spec in SPECS.items() if spec.deletable}
