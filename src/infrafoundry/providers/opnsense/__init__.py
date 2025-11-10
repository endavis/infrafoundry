"""OPNsense provider for InfraFoundry."""

import base64
from pathlib import Path
from typing import Any, override

from jinja2 import Environment, FileSystemLoader

from infrafoundry.core.provider import ProviderBase, ResourceConfig


class OPNsenseProvider(ProviderBase):
    """OPNsense provider for managing firewall rules, VLANs, and routing."""

    def __init__(self, config_dir: Path, output_dir: Path) -> None:
        """Initialize OPNsense provider."""
        super().__init__("opnsense", config_dir, output_dir)
        self.template_dir = Path(__file__).parent / "templates"
        self.jinja_env = Environment(
            loader=FileSystemLoader(str(self.template_dir)),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        # Add base64 encoding filter for Ansible templates
        self.jinja_env.filters["b64encode"] = lambda s: base64.b64encode(s.encode()).decode()

    @override
    def validate_config(self, config: dict[str, Any]) -> bool:
        """Validate OPNsense configuration."""
        required_fields = ["name"]
        return all(field in config for field in required_fields)

    @override
    def generate_terraform(self, resources: list[ResourceConfig]) -> None:
        """Generate Terraform configuration for OPNsense resources."""
        self.ensure_directories()

        # Group resources by type
        resources_by_type: dict[str, list[ResourceConfig]] = {}
        for resource in resources:
            if resource.type not in resources_by_type:
                resources_by_type[resource.type] = []
            resources_by_type[resource.type].append(resource)

        # Generate provider configuration
        provider_template = self.jinja_env.get_template("opnsense/provider.tf.j2")
        provider_content = provider_template.render()
        (self.terraform_dir / "provider.tf").write_text(provider_content)

        # Generate variables file
        variables_template = self.jinja_env.get_template("opnsense/variables.tf.j2")
        variables_content = variables_template.render()
        (self.terraform_dir / "variables.tf").write_text(variables_content)

        # Generate resources by type
        if "firewall_rules" in resources_by_type:
            self._generate_firewall_rules_terraform(resources_by_type["firewall_rules"])

        if "vlans" in resources_by_type:
            self._generate_vlans_terraform(resources_by_type["vlans"])

        if "aliases" in resources_by_type:
            self._generate_aliases_terraform(resources_by_type["aliases"])

        if "dhcp_static_maps" in resources_by_type:
            self._generate_dhcp_static_maps_terraform(resources_by_type["dhcp_static_maps"])

        # Generate outputs
        outputs_template = self.jinja_env.get_template("opnsense/outputs.tf.j2")
        outputs_content = outputs_template.render(
            resources_by_type=resources_by_type,
        )
        (self.terraform_dir / "outputs.tf").write_text(outputs_content)

    def _generate_firewall_rules_terraform(self, rules: list[ResourceConfig]) -> None:
        """Generate Terraform for OPNsense firewall rules."""
        template = self.jinja_env.get_template("opnsense/firewall_rules.tf.j2")
        content = template.render(rules=rules)
        (self.terraform_dir / "firewall_rules.tf").write_text(content)

    def _generate_vlans_terraform(self, vlans: list[ResourceConfig]) -> None:
        """Generate Terraform for OPNsense VLANs."""
        template = self.jinja_env.get_template("opnsense/vlans.tf.j2")
        content = template.render(vlans=vlans)
        (self.terraform_dir / "vlans.tf").write_text(content)

    def _generate_aliases_terraform(self, aliases: list[ResourceConfig]) -> None:
        """Generate Terraform for OPNsense aliases."""
        template = self.jinja_env.get_template("opnsense/aliases.tf.j2")
        content = template.render(aliases=aliases)
        (self.terraform_dir / "aliases.tf").write_text(content)

    def _generate_dhcp_static_maps_terraform(self, static_maps: list[ResourceConfig]) -> None:
        """Generate Terraform for OPNsense DHCP static mappings."""
        template = self.jinja_env.get_template("opnsense/dhcp_static_maps.tf.j2")
        content = template.render(static_maps=static_maps)
        (self.terraform_dir / "dhcp_static_maps.tf").write_text(content)

    @override
    def generate_ansible(self, resources: list[ResourceConfig]) -> None:
        """Generate Ansible playbooks for OPNsense configuration."""
        self.ensure_directories()

        # Generate main playbook
        playbook_template = self.jinja_env.get_template("opnsense/playbook.yml.j2")
        playbook_content = playbook_template.render(resources=resources)
        (self.ansible_dir / "playbook.yml").write_text(playbook_content)

        # Generate inventory
        inventory_template = self.jinja_env.get_template("opnsense/inventory.yml.j2")
        inventory_content = inventory_template.render()
        (self.ansible_dir / "inventory.yml").write_text(inventory_content)

    @override
    def get_resource_types(self) -> list[str]:
        """Get supported resource types."""
        return ["firewall_rules", "vlans", "aliases", "dhcp_static_maps"]

    @override
    def get_dependencies(self) -> dict[str, list[str]]:
        """Get resource dependencies."""
        return {
            "firewall_rules": ["aliases", "vlans"],
            "vlans": [],
            "aliases": [],
            "dhcp_static_maps": ["vlans"],
        }
