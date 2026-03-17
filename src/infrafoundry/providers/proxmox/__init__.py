"""Proxmox provider for InfraFoundry."""

import os
from pathlib import Path
from typing import Any, ClassVar, override

from infrafoundry.core.provider import ProviderBase, ResourceConfig
from infrafoundry.core.provider_mixins import (
    ResourceGrouperMixin,
    TemplateRendererMixin,
    TerraformGeneratorMixin,
)
from infrafoundry.core.types import EnvironmentData
from infrafoundry.core.validation import ValidationReport

from .validator import ProxmoxValidator


class ProxmoxProvider(
    ProviderBase,
    TemplateRendererMixin,
    ResourceGrouperMixin,
    TerraformGeneratorMixin,
):
    """Proxmox VE provider for managing VMs, containers, templates, and networks."""

    _PROXMOX_TFVARS_MAPPING: ClassVar[dict[str, str]] = {
        "api_url": "proxmox_api_url",
        "api_token": "proxmox_api_token",  # nosec B105
        "node": "proxmox_node",
        "storage": "proxmox_storage",
    }

    def __init__(self, config_dir: Path, output_dir: Path) -> None:
        """Initialize Proxmox provider."""
        super().__init__("proxmox", config_dir, output_dir)
        self.fail_on_missing_snippets = False
        # Use TemplateRendererMixin to set up Jinja2 environment
        self._setup_template_environment()

    @override
    def validate_config(self, config: dict[str, Any]) -> bool:
        """Validate Proxmox configuration."""
        required_fields = ["name"]
        return all(field in config for field in required_fields)

    @override
    def validate_connectivity(self, env_config: EnvironmentData, report: ValidationReport) -> None:
        """Validate connectivity to Proxmox API."""
        validator = ProxmoxValidator(env_config, report)
        validator.validate_connectivity()

    @override
    def validate_references(
        self, resources: list[ResourceConfig], env_config: EnvironmentData, report: ValidationReport
    ) -> None:
        """Validate that referenced Proxmox resources exist."""
        validator = ProxmoxValidator(env_config, report)
        validator.validate_references(resources)

    # Maps credential env vars (set by CredentialLoader) to TF_VAR_ names
    _CREDENTIAL_ENV_MAPPING: ClassVar[dict[str, str]] = {  # nosec B105
        "PROXMOX_API_URL": "proxmox_api_url",
        "PROXMOX_API_TOKEN_ID": "proxmox_api_token_id",
        "PROXMOX_API_TOKEN_SECRET": "proxmox_api_token_secret",
    }

    @override
    def get_terraform_env_vars(self) -> dict[str, str]:
        """Return TF_VAR_* env vars for Proxmox provider."""
        result = self.build_terraform_env_vars(
            provider_name="proxmox",
            mapping=self._PROXMOX_TFVARS_MAPPING,
            include_ssh=True,
            ssh_prefix="proxmox",
        )
        # Map credential env vars to TF_VAR_ equivalents
        for env_key, tf_var_name in self._CREDENTIAL_ENV_MAPPING.items():
            value = os.environ.get(env_key)
            if value:
                result[f"TF_VAR_{tf_var_name}"] = value
        return result

    @override
    def generate_terraform(self, resources: list[ResourceConfig]) -> None:
        """Generate Terraform configuration for Proxmox resources."""
        resources_by_type = self.prepare_terraform_generation(resources)

        # Generate backend configuration if remote backend is configured
        self.render_backend()

        # Generate provider configuration with environment context
        self.render_provider_and_variables(
            variables_context={"default_ssh_user": os.getenv("USER", "root")},
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

        if "network" in resources_by_type:
            self._generate_networks_terraform(resources_by_type["network"])

        # Generate outputs
        self.render_outputs_terraform(resources_by_type)

    def _generate_vms_terraform(self, vms: list[ResourceConfig]) -> None:
        """Generate Terraform for Proxmox VMs.

        Partitions VMs into regular VMs (using bpg/proxmox provider) and OVA VMs
        (using terraform_data with SSH-based qm commands). Regular VMs get cloud-init
        processing; OVA VMs get network normalization only.
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

        return vm_copy

    def _process_cloud_init_snippets(self, vm: ResourceConfig) -> ResourceConfig:
        """Process cloud-init snippets and merge them into VM config."""
        import copy

        import yaml

        # Work with a copy to avoid modifying the original
        vm_copy = copy.deepcopy(vm)
        config = vm_copy.config

        # Check if cloud_init_snippets is defined
        if "cloud_init_snippets" not in config:
            return vm_copy

        snippet_names = config.get("cloud_init_snippets", [])
        cloud_init_vars = config.get("cloud_init_vars", {})

        # Load and merge snippets
        merged_cloud_init: dict[Any, Any] = {}

        for snippet_name in snippet_names:
            # Build path to snippet file
            if self._current_environment:
                snippet_path = (
                    self.config_dir
                    / self._current_environment
                    / "files"
                    / "cloud-init-snippets"
                    / f"{snippet_name}.yaml"
                )
            else:
                snippet_path = (
                    self.config_dir / "files" / "cloud-init-snippets" / f"{snippet_name}.yaml"
                )

            if not snippet_path.exists():
                message = f"Cloud-init snippet not found: {snippet_path}"
                if self.fail_on_missing_snippets:
                    raise FileNotFoundError(message)
                print(f"Warning: {message}")
                continue

            # Load snippet YAML
            with open(snippet_path) as f:
                snippet_content = f.read()

                # Substitute variables
                for var_name, var_value in cloud_init_vars.items():
                    snippet_content = snippet_content.replace(f"${{{var_name}}}", str(var_value))

                snippet_data = yaml.safe_load(snippet_content)

                if snippet_data:
                    # Merge snippet into merged_cloud_init
                    self._deep_merge(merged_cloud_init, snippet_data)

        # Store full merged cloud-init as YAML string for direct passthrough
        if merged_cloud_init:
            yaml_str = yaml.dump(merged_cloud_init, default_flow_style=False, sort_keys=False)
            # Escape ${...} sequences for terraform heredoc (prevents interpolation)
            config["cloud_init_user_data"] = yaml_str.replace("${", "$${")

        return vm_copy

    def _deep_merge(self, base: dict[str, Any], overlay: dict[str, Any]) -> None:
        """Deep merge overlay dict into base dict (modifies base in-place)."""
        for key, value in overlay.items():
            if key in base:
                if isinstance(base[key], dict) and isinstance(value, dict):
                    self._deep_merge(base[key], value)
                elif isinstance(base[key], list) and isinstance(value, list):
                    base[key].extend(value)
                else:
                    base[key] = value
            else:
                base[key] = value

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

    @override
    def get_resource_types(self) -> list[str]:
        """Get supported resource types."""
        return ["vm", "container", "template", "network", "storage"]

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
        }
