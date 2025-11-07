"""Proxmox provider for InfraFoundry."""

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

from infrafoundry.core.provider import ProviderBase, ResourceConfig


class ProxmoxProvider(ProviderBase):
    """Proxmox VE provider for managing VMs, templates, and networks."""

    def __init__(self, config_dir: Path, output_dir: Path) -> None:
        """Initialize Proxmox provider."""
        super().__init__("proxmox", config_dir, output_dir)
        self.template_dir = Path(__file__).parent / "templates"
        self.jinja_env = Environment(
            loader=FileSystemLoader(str(self.template_dir)),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def validate_config(self, config: dict[str, Any]) -> bool:
        """Validate Proxmox configuration."""
        required_fields = ["name"]
        return all(field in config for field in required_fields)

    def generate_terraform(self, resources: list[ResourceConfig]) -> None:
        """Generate Terraform configuration for Proxmox resources."""
        self.ensure_directories()

        # Group resources by type
        resources_by_type: dict[str, list[ResourceConfig]] = {}
        for resource in resources:
            if resource.type not in resources_by_type:
                resources_by_type[resource.type] = []
            resources_by_type[resource.type].append(resource)

        # Generate provider configuration
        provider_template = self.jinja_env.get_template("proxmox/provider.tf.j2")
        provider_content = provider_template.render()
        (self.terraform_dir / "provider.tf").write_text(provider_content)

        # Generate variables file
        variables_template = self.jinja_env.get_template("proxmox/variables.tf.j2")
        variables_content = variables_template.render()
        (self.terraform_dir / "variables.tf").write_text(variables_content)

        # Generate resources by type
        if "vms" in resources_by_type:
            self._generate_vms_terraform(resources_by_type["vms"])

        if "templates" in resources_by_type:
            self._generate_templates_terraform(resources_by_type["templates"])

        if "networks" in resources_by_type:
            self._generate_networks_terraform(resources_by_type["networks"])

        # Generate outputs
        outputs_template = self.jinja_env.get_template("proxmox/outputs.tf.j2")
        outputs_content = outputs_template.render(
            resources_by_type=resources_by_type,
        )
        (self.terraform_dir / "outputs.tf").write_text(outputs_content)

    def _generate_vms_terraform(self, vms: list[ResourceConfig]) -> None:
        """Generate Terraform for Proxmox VMs."""
        template = self.jinja_env.get_template("proxmox/vms.tf.j2")
        content = template.render(vms=vms)
        (self.terraform_dir / "vms.tf").write_text(content)

    def _generate_templates_terraform(self, templates: list[ResourceConfig]) -> None:
        """Generate Terraform for Proxmox templates."""
        template = self.jinja_env.get_template("proxmox/templates.tf.j2")
        content = template.render(templates=templates)
        (self.terraform_dir / "templates.tf").write_text(content)

    def _generate_networks_terraform(self, networks: list[ResourceConfig]) -> None:
        """Generate Terraform for Proxmox networks."""
        template = self.jinja_env.get_template("proxmox/networks.tf.j2")
        content = template.render(networks=networks)
        (self.terraform_dir / "networks.tf").write_text(content)

    def generate_ansible(self, resources: list[ResourceConfig]) -> None:
        """Generate Ansible playbooks for Proxmox post-configuration."""
        self.ensure_directories()

        # Generate main playbook
        playbook_template = self.jinja_env.get_template("proxmox/playbook.yml.j2")
        playbook_content = playbook_template.render(resources=resources)
        (self.ansible_dir / "playbook.yml").write_text(playbook_content)

        # Generate inventory
        inventory_template = self.jinja_env.get_template("proxmox/inventory.yml.j2")
        inventory_content = inventory_template.render(resources=resources)
        (self.ansible_dir / "inventory.yml").write_text(inventory_content)

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
        tasks_template = self.jinja_env.get_template("proxmox/roles/common/main.yml.j2")
        tasks_content = tasks_template.render()
        (tasks_dir / "main.yml").write_text(tasks_content)

    def get_resource_types(self) -> list[str]:
        """Get supported resource types."""
        return ["vms", "templates", "networks"]

    def get_dependencies(self) -> dict[str, list[str]]:
        """Get resource dependencies."""
        return {
            "vms": ["templates", "networks"],
            "templates": [],
            "networks": [],
        }
