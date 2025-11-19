"""Proxmox provider for InfraFoundry."""

from pathlib import Path
from typing import Any, override

from infrafoundry.core.provider import ProviderBase, ResourceConfig
from infrafoundry.core.provider_mixins import (
    ResourceGrouperMixin,
    TemplateRendererMixin,
    TerraformGeneratorMixin,
)
from infrafoundry.core.validation import ValidationReport

from .validator import ProxmoxValidator


class ProxmoxProvider(
    ProviderBase,
    TemplateRendererMixin,
    ResourceGrouperMixin,
    TerraformGeneratorMixin,
):
    """Proxmox VE provider for managing VMs, templates, and networks."""

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
    def validate_connectivity(self, env_config: dict[str, Any], report: ValidationReport) -> None:
        """Validate connectivity to Proxmox API."""
        validator = ProxmoxValidator(env_config, report)
        validator.validate_connectivity()

    @override
    def validate_references(
        self, resources: list[ResourceConfig], env_config: dict[str, Any], report: ValidationReport
    ) -> None:
        """Validate that referenced Proxmox resources exist."""
        validator = ProxmoxValidator(env_config, report)
        validator.validate_references(resources)

    @override
    def generate_terraform(self, resources: list[ResourceConfig]) -> None:
        """Generate Terraform configuration for Proxmox resources."""
        self.ensure_directories()

        # Use ResourceGrouperMixin to group resources by type
        resources_by_type = self.group_resources_by_type(resources)

        # Generate provider configuration
        content = self.render_template("proxmox/provider.tf.j2", {})
        self._write_terraform_file("provider.tf", content)

        # Generate variables file with environment context
        import os

        content = self.render_template(
            "proxmox/variables.tf.j2",
            {"default_ssh_user": os.getenv("USER", "root")},
        )
        self._write_terraform_file("variables.tf", content)

        # Copy or generate terraform.tfvars from environment config
        self._generate_tfvars()

        # Generate resources by type
        if "vm" in resources_by_type:
            self._generate_vms_terraform(resources_by_type["vm"])

        if "template" in resources_by_type:
            self._generate_templates_terraform(resources_by_type["template"])

        if "network" in resources_by_type:
            self._generate_networks_terraform(resources_by_type["network"])

        # Generate outputs
        content = self.render_template(
            "proxmox/outputs.tf.j2",
            {"resources_by_type": resources_by_type},
        )
        self._write_terraform_file("outputs.tf", content)

    def _generate_vms_terraform(self, vms: list[ResourceConfig]) -> None:
        """Generate Terraform for Proxmox VMs."""
        # Process VMs to merge cloud-init snippets
        processed_vms = []
        for vm in vms:
            processed_vm = self._process_cloud_init_snippets(vm)
            processed_vms.append(processed_vm)

        content = self.render_template("proxmox/vms.tf.j2", {"vms": processed_vms})
        self._write_terraform_file("vms.tf", content)

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
        merged_cloud_init = {}

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

        # Convert merged cloud-init to the format expected by the template
        if merged_cloud_init:
            # Handle hostname
            if "hostname" in merged_cloud_init:
                config["cloud_init_hostname"] = merged_cloud_init["hostname"]
            if "fqdn" in merged_cloud_init:
                config["cloud_init_fqdn"] = merged_cloud_init.get(
                    "fqdn", merged_cloud_init.get("hostname")
                )

            # Handle users
            if "users" in merged_cloud_init:
                config["cloud_init_users"] = merged_cloud_init["users"]

            # Handle packages
            if "packages" in merged_cloud_init:
                config["cloud_init_packages"] = merged_cloud_init["packages"]

            # Handle runcmd
            if "runcmd" in merged_cloud_init:
                config["cloud_init_runcmd"] = merged_cloud_init["runcmd"]

            # Handle network config - store as raw YAML for template
            if "network" in merged_cloud_init:
                config["cloud_init_network"] = merged_cloud_init["network"]

        return vm_copy

    def _deep_merge(self, base: dict, overlay: dict) -> None:
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
        """Generate Terraform for Proxmox templates."""
        from urllib.parse import urlparse

        from infrafoundry.core.config import ConfigManager

        # Extract SSH hostname from API URL for templates that need it
        ssh_hostname = None
        if self._current_environment:
            config_manager = ConfigManager(self.config_dir)
            try:
                env_config = config_manager.load_environment(self._current_environment)
                provider_settings = env_config.get_provider_settings("proxmox")
                if provider_settings and "api_url" in provider_settings:
                    parsed = urlparse(provider_settings["api_url"])
                    ssh_hostname = parsed.hostname
            except FileNotFoundError:
                pass

        content = self.render_template(
            "proxmox/templates.tf.j2", {"templates": templates, "ssh_hostname": ssh_hostname}
        )
        self._write_terraform_file("templates.tf", content)

    def _generate_networks_terraform(self, networks: list[ResourceConfig]) -> None:
        """Generate Terraform for Proxmox networks."""
        content = self.render_template("proxmox/networks.tf.j2", {"networks": networks})
        self._write_terraform_file("networks.tf", content)

    def _copy_tfvars_if_exists(self) -> None:
        """Copy environment-specific terraform.tfvars if it exists."""
        import shutil

        # Look for terraform.tfvars in the config directory
        # The config_dir points to envs/{env}, so we need to go up and check
        potential_tfvars = self.config_dir / "terraform.tfvars"

        if potential_tfvars.exists():
            dest = self.terraform_dir / "terraform.tfvars"
            shutil.copy2(potential_tfvars, dest)

    def _generate_tfvars(self) -> None:
        """Generate terraform.tfvars from provider and SSH settings."""
        mapping = {
            "api_url": "proxmox_api_url",
            "api_token": "proxmox_api_token",
            "node": "proxmox_node",
            "storage": "proxmox_storage",
        }
        self._generate_tfvars_with_mapping(
            provider_name="proxmox",
            mapping=mapping,
            include_ssh=True,
            ssh_prefix="proxmox",
        )

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
    def get_resource_types(self) -> list[str]:
        """Get supported resource types."""
        return ["vm", "template", "network"]

    @override
    def get_dependencies(self) -> dict[str, list[str]]:
        """Get resource dependencies."""
        return {
            "vm": ["template", "network"],
            "template": [],
            "network": [],
        }
