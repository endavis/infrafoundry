"""Proxmox provider for InfraFoundry."""

import os
from pathlib import Path
from typing import Any, ClassVar, override

from infrafoundry.core.config.models import EnvironmentConfig
from infrafoundry.core.exceptions import SchemaValidationError
from infrafoundry.core.provider import ProviderBase, ResourceConfig
from infrafoundry.core.provider_mixins import (
    CloudInitMixin,
    ResourceGrouperMixin,
    TemplateRendererMixin,
    TerraformGeneratorMixin,
    sanitize_secret_ref_to_tf_var,
)
from infrafoundry.core.validation import ValidationLevel, ValidationReport

from .validator import ProxmoxValidator
from .validators import (
    ContainerConfigValidator,
    StorageConfigValidator,
    VMConfigValidator,
)


class ProxmoxProvider(
    ProviderBase,
    TemplateRendererMixin,
    ResourceGrouperMixin,
    TerraformGeneratorMixin,
    CloudInitMixin,
):
    """Proxmox VE provider for managing VMs, containers, templates, and networks."""

    _PROXMOX_TFVARS_MAPPING: ClassVar[dict[str, str]] = {
        "api_url": "proxmox_api_url",
        "api_token": "proxmox_api_token",  # nosec B105
        "api_token_id": "proxmox_api_token_id",  # nosec B105
        "api_token_secret": "proxmox_api_token_secret",  # nosec B105
        "node": "proxmox_node",
        "storage": "proxmox_storage",
    }

    def __init__(self, config_dir: Path, output_dir: Path) -> None:
        """Initialize Proxmox provider."""
        super().__init__("proxmox", config_dir, output_dir)
        self.fail_on_missing_snippets = False
        # Serialize terraform operations to avoid CFS lock timeouts when
        # cloning VMs onto shared (NFS/CIFS) storage in a Proxmox cluster.
        self.terraform_parallelism = 1
        # Cache of resources from the most recent generate_terraform call.
        # Used by get_terraform_env_vars to resolve resource-level
        # ``terraform_secrets`` references into TF_VAR_* env vars.
        self._last_terraform_resources: list[ResourceConfig] = []
        # Use TemplateRendererMixin to set up Jinja2 environment
        self._setup_template_environment()

    @override
    def validate_config(self, config: dict[str, Any]) -> bool:
        """Validate Proxmox configuration."""
        required_fields = ["name"]
        return all(field in config for field in required_fields)

    @override
    def validate_connectivity(
        self, env_config: EnvironmentConfig, report: ValidationReport
    ) -> None:
        """Validate connectivity to Proxmox API."""
        validator = ProxmoxValidator(env_config, report)
        validator.validate_connectivity()

    @override
    def validate_references(
        self,
        resources: list[ResourceConfig],
        env_config: EnvironmentConfig,
        report: ValidationReport,
    ) -> None:
        """Validate that referenced Proxmox resources exist."""
        validator = ProxmoxValidator(env_config, report)
        validator.validate_references(resources)

    @override
    def get_terraform_env_vars(self) -> dict[str, str]:
        """Return TF_VAR_* env vars for Proxmox provider."""
        return self.build_terraform_env_vars(
            provider_name="proxmox",
            mapping=self._PROXMOX_TFVARS_MAPPING,
            include_ssh=True,
            ssh_prefix="proxmox",
            resources=self._last_terraform_resources,
        )

    @override
    def generate_terraform(self, resources: list[ResourceConfig]) -> None:
        """Generate Terraform configuration for Proxmox resources."""
        resources_by_type = self.prepare_terraform_generation(resources)

        # Field-level schema validation catches malformed configs (e.g., using
        # ``type:`` instead of ``backend:`` for storage) before template
        # rendering silently drops the resource. See issue #621.
        self._validate_resource_configs(resources_by_type)

        # Pre-process VMs FIRST so any ``tailscale:`` blocks auto-populate
        # ``terraform_secrets`` on the resource. This must happen before
        # ``collect_terraform_secret_refs`` runs so the variables.tf
        # template sees the dynamic sensitive vars.
        processed_vms = self._preprocess_vms_for_secrets(resources_by_type.get("vm", []))
        if processed_vms:
            resources_by_type["vm"] = processed_vms

        # Cache the post-processed resources so get_terraform_env_vars can
        # resolve all ``terraform_secrets`` references (including the ones
        # auto-populated by process_tailscale_config) at apply time.
        all_processed: list[ResourceConfig] = []
        for type_resources in resources_by_type.values():
            all_processed.extend(type_resources)
        self._last_terraform_resources = all_processed

        # Generate backend configuration if remote backend is configured
        self.render_backend()

        # Build the set of dynamic sensitive vars driven by resource-level
        # ``terraform_secrets`` references so the variables.tf template can
        # declare them.
        secret_refs = self.collect_terraform_secret_refs(all_processed)
        terraform_secret_vars = [
            {"name": sanitize_secret_ref_to_tf_var(ref), "source": ref} for ref in secret_refs
        ]

        # Generate provider configuration with environment context
        self.render_provider_and_variables(
            variables_context={
                "default_ssh_user": os.getenv("USER", "root"),
                "terraform_secret_vars": terraform_secret_vars,
            },
        )

        # Generate resources by type (storage before VMs/containers so they can reference it)
        if "storage" in resources_by_type:
            self._generate_storage_terraform(resources_by_type["storage"])

        if "vm" in resources_by_type:
            self._generate_vms_terraform(resources_by_type["vm"])

        if "container" in resources_by_type:
            self._generate_containers_terraform(resources_by_type["container"])

        if "template" in resources_by_type:
            self._generate_templates_terraform(resources_by_type["template"])

        if "trigger" in resources_by_type:
            self._generate_triggers_terraform(resources_by_type["trigger"])

        if "network" in resources_by_type:
            self._generate_networks_terraform(resources_by_type["network"])

        # Generate outputs
        self.render_outputs_terraform(resources_by_type)

    def _validate_resource_configs(
        self, resources_by_type: dict[str, list[ResourceConfig]]
    ) -> None:
        """Run field-level config validation on storage, VM, and container resources.

        Collects ERROR-level findings from the three ``*ConfigValidator`` classes and
        raises ``SchemaValidationError`` with a multi-line summary if any are present.
        WARNING-level findings (e.g., CIFS without ``username``) are collected but do
        not block generation.

        Args:
            resources_by_type: Resources grouped by type, as returned by
                ``prepare_terraform_generation``.

        Raises:
            SchemaValidationError: If one or more resources have ERROR-level
                validation findings. The message lists every failing check by
                name and description.
        """
        report = ValidationReport()
        StorageConfigValidator(report).validate(resources_by_type.get("storage", []))
        VMConfigValidator(report).validate(resources_by_type.get("vm", []))
        ContainerConfigValidator(report).validate(resources_by_type.get("container", []))

        if report.has_errors():
            error_lines = [
                f"  - [{r.check_name}] {r.message}"
                for r in report.results
                if not r.passed and r.level == ValidationLevel.ERROR
            ]
            message = "Proxmox resource configuration validation failed:\n" + "\n".join(error_lines)
            raise SchemaValidationError(message)

    def _preprocess_vms_for_secrets(self, vms: list[ResourceConfig]) -> list[ResourceConfig]:
        """Pre-process VMs so tailscale: blocks auto-populate terraform_secrets.

        Called from ``generate_terraform`` BEFORE ``collect_terraform_secret_refs``
        so that any auto-populated ``terraform_secrets`` entries are visible
        when the variables.tf template renders.

        Issue #212 phase 2: the result is the same list of resources, but
        each VM that has a ``tailscale:`` block has had its
        ``terraform_secrets`` extended with the referenced secret paths.
        ``_generate_vms_terraform`` will later run the full processing
        (snippet merge / tailscale module normalization) on the same
        objects. The tailscale helper is idempotent so the duplicate call
        is safe.
        """
        processed: list[ResourceConfig] = []
        for vm in vms:
            if "ova_source" in vm.config:
                # OVA VMs don't go through cloud-init / tailscale processing.
                processed.append(vm)
            else:
                processed.append(self._process_cloud_init_snippets(vm))
        return processed

    def _generate_vms_terraform(self, vms: list[ResourceConfig]) -> None:
        """Generate Terraform for Proxmox VMs.

        Partitions VMs into regular VMs (using bpg/proxmox provider) and OVA VMs
        (using terraform_data with SSH-based qm commands). Regular VMs get cloud-init
        processing; OVA VMs get network normalization only.

        Note: ``generate_terraform`` pre-processes VMs (via
        ``_preprocess_vms_for_secrets``) so the secrets→TF_VAR_* bridge can
        see auto-populated terraform_secrets before variables.tf is rendered.
        The cloud-init processing call here is idempotent and intentional —
        it normalizes VMs that didn't get pre-processed (e.g. when this
        method is called by code paths other than ``generate_terraform``).
        """
        regular_vms = []
        ova_vms = []
        for vm in vms:
            if "ova_source" in vm.config:
                ova_vms.append(self._normalize_vm_config(vm))
            else:
                processed = self._process_cloud_init_snippets(vm)
                processed = self._normalize_vm_config(processed)
                regular_vms.append(processed)

        if regular_vms:
            self.render_and_write_terraform(
                "proxmox/vms.tf.j2",
                context={"vms": regular_vms},
                output_name="vms.tf",
            )

        if ova_vms:
            self._generate_ova_vms_terraform(ova_vms)

    def _generate_ova_vms_terraform(self, ova_vms: list[ResourceConfig]) -> None:
        """Generate Terraform for OVA-based Proxmox VMs.

        Uses terraform_data resources with SSH-based local-exec provisioners to
        extract OVA files, import VMDK disks, and configure VMs via qm commands.
        Each VM's target_node is used as the SSH target since qm commands must
        run on the node where the VM will be created.

        Args:
            ova_vms: List of OVA VM resource configs (must have ova_source).
        """
        self.render_and_write_terraform(
            "proxmox/ova_vms.tf.j2",
            context={"ova_vms": ova_vms},
            output_name="ova_vms.tf",
        )

    def _generate_containers_terraform(self, containers: list[ResourceConfig]) -> None:
        """Generate Terraform for Proxmox LXC containers."""
        processed_containers = []
        for container in containers:
            processed_containers.append(self._normalize_container_config(container))

        self.render_and_write_terraform(
            "proxmox/containers.tf.j2",
            context={"containers": processed_containers},
            output_name="containers.tf",
        )

    def _normalize_container_config(self, container: ResourceConfig) -> ResourceConfig:
        """Normalize container config for template consumption.

        Ensures the network and mount_point fields are always lists of dicts,
        even when the user provides a single dict.

        Args:
            container: The container resource config to normalize.

        Returns:
            The container resource config with normalized fields.
        """
        import copy

        ct_copy = copy.deepcopy(container)
        config = ct_copy.config

        # Normalize network: wrap single dict in a list
        network = config.get("network")
        if isinstance(network, dict):
            config["network"] = [network]

        # Normalize mount_point: wrap single dict in a list
        mount_point = config.get("mount_point")
        if isinstance(mount_point, dict):
            config["mount_point"] = [mount_point]

        return ct_copy

    def _normalize_vm_config(self, vm: ResourceConfig) -> ResourceConfig:
        """Normalize VM config for template consumption.

        Ensures the network field is always a list of dicts, even when the user
        provides a single dict. This allows the Jinja2 template to use a simple
        ``{% for nic in vm.config.network %}`` loop without dual dict/list handling.

        Args:
            vm: The VM resource config to normalize.

        Returns:
            The VM resource config with normalized network field.
        """
        import copy

        vm_copy = copy.deepcopy(vm)
        config = vm_copy.config

        # Normalize network: wrap single dict in a list
        network = config.get("network")
        if isinstance(network, dict):
            config["network"] = [network]

        # Normalize clone: wrap scalar VMID in a dict for consistent template handling
        clone = config.get("clone")
        if clone is not None and not isinstance(clone, dict):
            config["clone"] = {"vm_id": clone}

        return vm_copy

    def _process_cloud_init_snippets(self, vm: ResourceConfig) -> ResourceConfig:
        """Process cloud-init snippets or tailscale module and merge into config.

        Two mutually exclusive paths (issue #212 phase 2):

        - If the VM config has a ``tailscale:`` block, it is validated and
          normalized into a ``tailscale_module_config`` dict. The resource's
          ``terraform_secrets`` list is auto-populated with the referenced
          secret paths so the framework's secrets→TF_VAR_* bridge (phase 1
          of #212) injects the values at apply time. The Tailscale module is
          rendered with ``base64_encode = false`` so the bpg/proxmox file
          resource can store the raw multipart MIME directly via
          ``source_raw.data``.
        - Otherwise, any ``cloud_init_snippets`` are loaded, merged, and
          stored as ``cloud_init_user_data`` (YAML string with Terraform
          ``${`` escaping) for the existing template path.

        Args:
            vm: VM resource config.

        Returns:
            Copy of the VM config with exactly one of
            ``cloud_init_user_data`` or ``tailscale_module_config`` set
            (or neither, if no cloud-init is configured).
        """
        import copy

        import yaml

        from infrafoundry.core.tailscale import process_tailscale_config

        vm_copy = copy.deepcopy(vm)
        # Proxmox stores cloud-init as a file via ``source_raw``; the
        # Tailscale module's ``rendered`` output is the raw multipart MIME
        # when base64_encode=False, which Proxmox can hand to cloud-init
        # at boot without further decoding.
        tailscale_module_config = process_tailscale_config(vm_copy, base64_encode=False)
        if tailscale_module_config is not None:
            vm_copy.config["tailscale_module_config"] = tailscale_module_config
            return vm_copy

        merged = self._merge_cloud_init_snippets(vm_copy.config)
        if merged:
            yaml_str = yaml.dump(merged, default_flow_style=False, sort_keys=False)
            vm_copy.config["cloud_init_user_data"] = yaml_str.replace("${", "$${")
        return vm_copy

    def _generate_templates_terraform(self, templates: list[ResourceConfig]) -> None:
        """Generate Terraform for Proxmox templates.

        Uses native bpg/proxmox provider resources for download_image templates
        (proxmox_virtual_environment_download_file + proxmox_virtual_environment_vm
        with template=true). Clone-based templates use proxmox_virtual_environment_vm
        with template=true directly.
        """
        self.render_and_write_terraform(
            "proxmox/templates.tf.j2",
            context={"templates": templates},
            output_name="templates.tf",
        )

    def _generate_networks_terraform(self, networks: list[ResourceConfig]) -> None:
        """Generate Terraform for Proxmox networks."""
        self.render_and_write_terraform(
            "proxmox/networks.tf.j2",
            context={"networks": networks},
            output_name="networks.tf",
        )

    def _generate_storage_terraform(self, storages: list[ResourceConfig]) -> None:
        """Generate Terraform for Proxmox storage backends."""
        self.render_and_write_terraform(
            "proxmox/storage.tf.j2",
            context={"storages": storages},
            output_name="storage.tf",
        )

    def _copy_tfvars_if_exists(self) -> None:
        """Copy environment-specific terraform.tfvars if it exists."""
        import shutil

        # Look for terraform.tfvars in the config directory
        # The config_dir points to envs/{env}, so we need to go up and check
        potential_tfvars = self.config_dir / "terraform.tfvars"

        if potential_tfvars.exists():
            dest = self.terraform_dir / "terraform.tfvars"
            shutil.copy2(potential_tfvars, dest)

    @override
    def generate_ansible(self, resources: list[ResourceConfig]) -> None:
        """Generate Ansible playbooks for Proxmox post-configuration."""
        self.ensure_directories()

        # Generate main playbook
        content = self.render_template("proxmox/playbook.yml.j2", {"resources": resources})
        self._write_ansible_file("playbook.yml", content)

        # Generate inventory
        content = self.render_template("proxmox/inventory.yml.j2", {"resources": resources})
        self._write_ansible_file("inventory.yml", content)

        # Create roles directory structure
        roles_dir = self.ansible_dir / "roles"
        roles_dir.mkdir(exist_ok=True)

        # Generate common role for post-configuration
        self._generate_common_role(roles_dir)

    def _generate_common_role(self, roles_dir: Path) -> None:
        """Generate common Ansible role for VM configuration."""
        common_role = roles_dir / "common"
        tasks_dir = common_role / "tasks"
        tasks_dir.mkdir(parents=True, exist_ok=True)

        # Generate main tasks
        content = self.render_template("proxmox/roles/common/main.yml.j2", {})
        (tasks_dir / "main.yml").write_text(content)

    @override
    def generate_pyinfra(self, resources: list[ResourceConfig]) -> None:
        """Generate pyinfra deploy scripts and inventory.

        Args:
            resources: List of resources to generate pyinfra for
        """
        self.ensure_directories()

        # Copy custom pyinfra code if it exists
        # Assuming 'pyinfra' directory at the root of the config repo
        # self.config_dir is envs/{env}, so we go up to the root
        custom_pyinfra_dir = self.config_dir.parent.parent / "pyinfra"
        if not custom_pyinfra_dir.exists():
            # Fallback: maybe config_dir is envs/ (if called from test or strict context)
            custom_pyinfra_dir = self.config_dir.parent / "pyinfra"

        if custom_pyinfra_dir.exists() and custom_pyinfra_dir.is_dir():
            import shutil

            # Copy contents to self.pyinfra_dir (so they are importable directly)
            for item in custom_pyinfra_dir.iterdir():
                dest = self.pyinfra_dir / item.name
                if item.is_dir():
                    if dest.exists():
                        shutil.rmtree(dest)
                    shutil.copytree(item, dest)
                else:
                    shutil.copy2(item, dest)

        # Generate inventory
        content = self.render_template("proxmox/inventory.py.j2", {"resources": resources})
        self._write_pyinfra_file("inventory.py", content)

        # Generate deploy script
        content = self.render_template("proxmox/deploy.py.j2", {"resources": resources})
        self._write_pyinfra_file("deploy.py", content)

    def _generate_triggers_terraform(self, triggers: list[ResourceConfig]) -> None:
        """Generate Terraform for trigger resources.

        Renders lightweight ``terraform_data`` resources that serve as state
        markers for packages without real infrastructure. Useful for triggering
        ``on_create`` lifecycle events in script-only packages.

        Args:
            triggers: List of trigger resource configs.
        """
        self.render_and_write_terraform(
            "proxmox/triggers.tf.j2",
            context={"triggers": triggers},
            output_name="triggers.tf",
        )

    @override
    def get_resource_types(self) -> list[str]:
        """Get supported resource types."""
        return ["vm", "container", "template", "network", "storage", "trigger"]

    @override
    def get_terraform_resource_types(self) -> dict[str, list[str]]:
        """Map InfraFoundry resource types to terraform resource types."""
        return {
            "vm": ["proxmox_virtual_environment_vm", "terraform_data"],
            "template": ["proxmox_virtual_environment_vm"],
            "container": ["proxmox_virtual_environment_container"],
            "storage": [
                "proxmox_virtual_environment_storage_nfs",
                "proxmox_virtual_environment_storage_cifs",
                "proxmox_virtual_environment_storage_dir",
            ],
            "trigger": ["terraform_data"],
        }

    @override
    def get_dependencies(self) -> dict[str, list[str]]:
        """Get resource dependencies."""
        return {
            "vm": ["template", "network", "storage"],
            "container": ["network", "storage"],
            "template": [],
            "network": [],
            "storage": [],
            "trigger": [],
        }
