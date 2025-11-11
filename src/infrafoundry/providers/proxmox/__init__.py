"""Proxmox provider for InfraFoundry."""

from pathlib import Path
from typing import Any, override

from infrafoundry.core.provider import ProviderBase, ResourceConfig
from infrafoundry.core.provider_mixins import ResourceGrouperMixin, TemplateRendererMixin
from infrafoundry.core.validation import ValidationReport

from .validator import ProxmoxValidator


class ProxmoxProvider(ProviderBase, TemplateRendererMixin, ResourceGrouperMixin):
    """Proxmox VE provider for managing VMs, templates, and networks."""

    def __init__(self, config_dir: Path, output_dir: Path) -> None:
        """Initialize Proxmox provider."""
        super().__init__("proxmox", config_dir, output_dir)
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
        content = self.render_template("proxmox/vms.tf.j2", {"vms": vms})
        self._write_terraform_file("vms.tf", content)

    def _generate_templates_terraform(self, templates: list[ResourceConfig]) -> None:
        """Generate Terraform for Proxmox templates."""
        content = self.render_template("proxmox/templates.tf.j2", {"templates": templates})
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
        """Generate terraform.tfvars from settings.yaml (SSH config + provider settings)."""
        from infrafoundry.core.config import ConfigManager

        if not self._current_environment:
            return

        env_name = self._current_environment
        config_manager = ConfigManager(self.config_dir)

        try:
            env_config = config_manager.load_environment(env_name)
        except FileNotFoundError:
            return

        tfvars_lines = ["# Configuration from settings.yaml\n"]

        # Get provider-specific settings (API credentials, endpoints, etc.)
        provider_settings = env_config.get_provider_settings("proxmox")
        if provider_settings:
            # API endpoint
            if "api_url" in provider_settings:
                tfvars_lines.append(f'proxmox_api_url = "{provider_settings["api_url"]}"\n')

            # API token (preferred for bpg/proxmox provider)
            if "api_token" in provider_settings:
                tfvars_lines.append(f'proxmox_api_token = "{provider_settings["api_token"]}"\n')

            # Default node
            if "node" in provider_settings:
                tfvars_lines.append(f'proxmox_node = "{provider_settings["node"]}"\n')

            # Default storage
            if "storage" in provider_settings:
                tfvars_lines.append(f'proxmox_storage = "{provider_settings["storage"]}"\n')

        # Get SSH config for this provider (provider-specific or global)
        ssh_config = env_config.get_ssh_config("proxmox")
        if ssh_config:
            if ssh_config.user:
                tfvars_lines.append(f'proxmox_ssh_user = "{ssh_config.user}"\n')

            if ssh_config.key_path:
                tfvars_lines.append(f'proxmox_ssh_key_path = "{ssh_config.key_path}"\n')

            if ssh_config.port and ssh_config.port != 22:
                tfvars_lines.append(f"proxmox_ssh_port = {ssh_config.port}\n")

        # Generate tfvars if we have more than just the header comment
        if len(tfvars_lines) > 1:
            dest = self.terraform_dir / "terraform.tfvars"
            dest.write_text("".join(tfvars_lines))

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
