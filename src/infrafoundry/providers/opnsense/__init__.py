"""OPNsense provider for InfraFoundry."""

import base64
import os
from pathlib import Path
from typing import Any, override

import requests

from infrafoundry.core.provider import ProviderBase, ResourceConfig
from infrafoundry.core.provider_mixins import ResourceGrouperMixin, TemplateRendererMixin
from infrafoundry.core.validation import ValidationLevel, ValidationReport


class OPNsenseProvider(ProviderBase, TemplateRendererMixin, ResourceGrouperMixin):
    """OPNsense provider for managing firewall rules, VLANs, and routing."""

    def __init__(self, config_dir: Path, output_dir: Path) -> None:
        """Initialize OPNsense provider."""
        super().__init__("opnsense", config_dir, output_dir)
        # Use TemplateRendererMixin to set up Jinja2 environment
        self._setup_template_environment()
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

        # Use ResourceGrouperMixin to group resources by type
        resources_by_type = self.group_resources_by_type(resources)

        # Generate provider configuration
        content = self.render_template("opnsense/provider.tf.j2", {})
        self._write_terraform_file("provider.tf", content)

        # Generate variables file
        content = self.render_template("opnsense/variables.tf.j2", {})
        self._write_terraform_file("variables.tf", content)

        # Generate terraform.tfvars from settings.yaml
        self._generate_tfvars()

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
        content = self.render_template(
            "opnsense/outputs.tf.j2",
            {"resources_by_type": resources_by_type},
        )
        self._write_terraform_file("outputs.tf", content)

    def _generate_firewall_rules_terraform(self, rules: list[ResourceConfig]) -> None:
        """Generate Terraform for OPNsense firewall rules."""
        content = self.render_template("opnsense/firewall_rules.tf.j2", {"rules": rules})
        self._write_terraform_file("firewall_rules.tf", content)

    def _generate_vlans_terraform(self, vlans: list[ResourceConfig]) -> None:
        """Generate Terraform for OPNsense VLANs."""
        content = self.render_template("opnsense/vlans.tf.j2", {"vlans": vlans})
        self._write_terraform_file("vlans.tf", content)

    def _generate_aliases_terraform(self, aliases: list[ResourceConfig]) -> None:
        """Generate Terraform for OPNsense aliases."""
        content = self.render_template("opnsense/aliases.tf.j2", {"aliases": aliases})
        self._write_terraform_file("aliases.tf", content)

    def _generate_dhcp_static_maps_terraform(self, static_maps: list[ResourceConfig]) -> None:
        """Generate Terraform for OPNsense DHCP static mappings."""
        content = self.render_template(
            "opnsense/dhcp_static_maps.tf.j2", {"static_maps": static_maps}
        )
        self._write_terraform_file("dhcp_static_maps.tf", content)

    def _generate_tfvars(self) -> None:
        """Generate terraform.tfvars from settings.yaml (provider settings)."""
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
        provider_settings = env_config.get_provider_settings("opnsense")
        if provider_settings:
            # API endpoint
            if "api_url" in provider_settings:
                tfvars_lines.append(f'opnsense_api_url = "{provider_settings["api_url"]}"\n')

            # API credentials
            if "api_key" in provider_settings:
                tfvars_lines.append(f'opnsense_api_key = "{provider_settings["api_key"]}"\n')

            if "api_secret" in provider_settings:
                tfvars_lines.append(f'opnsense_api_secret = "{provider_settings["api_secret"]}"\n')

        # Write terraform.tfvars if we have any variables
        if len(tfvars_lines) > 1:
            tfvars_path = self.terraform_dir / "terraform.tfvars"
            tfvars_path.write_text("".join(tfvars_lines))

    @override
    def generate_ansible(self, resources: list[ResourceConfig]) -> None:
        """Generate Ansible playbooks for OPNsense configuration."""
        self.ensure_directories()

        # Generate main playbook
        content = self.render_template("opnsense/playbook.yml.j2", {"resources": resources})
        self._write_ansible_file("playbook.yml", content)

        # Generate inventory
        content = self.render_template("opnsense/inventory.yml.j2", {})
        self._write_ansible_file("inventory.yml", content)

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

    @override
    def validate_connectivity(self, env_config: dict[str, Any], report: ValidationReport) -> None:
        """Validate connectivity to OPNsense API.

        Args:
            env_config: Environment configuration with provider_settings
            report: ValidationReport to add results to
        """
        provider_settings = env_config.get("provider_settings", {}).get("opnsense", {})
        api_url = provider_settings.get("api_url") or os.getenv("OPNSENSE_API_URL")
        api_key = provider_settings.get("api_key") or os.getenv("OPNSENSE_API_KEY")
        api_secret = provider_settings.get("api_secret") or os.getenv("OPNSENSE_API_SECRET")

        # Check if credentials are configured
        if not all([api_url, api_key, api_secret]):
            report.add_check(
                check_name="opnsense_credentials",
                passed=False,
                message=(
                    "OPNsense credentials not configured (api_url, api_key, api_secret required)"
                ),
                level=ValidationLevel.ERROR,
            )
            return

        # Test API connectivity
        try:
            response = requests.get(
                f"{api_url}/api/core/system/status",
                auth=(api_key, api_secret),
                verify=False,  # OPNsense often uses self-signed certs
                timeout=10,
            )
            if response.status_code == 200:
                report.add_check(
                    check_name="opnsense_connectivity",
                    passed=True,
                    message=f"Successfully connected to OPNsense at {api_url}",
                    level=ValidationLevel.INFO,
                )
            elif response.status_code == 401:
                report.add_check(
                    check_name="opnsense_connectivity",
                    passed=False,
                    message="OPNsense API credentials invalid (401 Unauthorized)",
                    level=ValidationLevel.ERROR,
                )
            else:
                report.add_check(
                    check_name="opnsense_connectivity",
                    passed=False,
                    message=f"OPNsense API returned status {response.status_code}",
                    level=ValidationLevel.WARNING,
                )
        except requests.exceptions.ConnectionError:
            report.add_check(
                check_name="opnsense_connectivity",
                passed=False,
                message=f"Cannot connect to OPNsense at {api_url} (connection refused)",
                level=ValidationLevel.ERROR,
            )
        except requests.exceptions.Timeout:
            report.add_check(
                check_name="opnsense_connectivity",
                passed=False,
                message=f"Connection to OPNsense at {api_url} timed out",
                level=ValidationLevel.ERROR,
            )
        except Exception as e:
            report.add_check(
                check_name="opnsense_connectivity",
                passed=False,
                message=f"Error connecting to OPNsense: {e}",
                level=ValidationLevel.ERROR,
            )

    @override
    def validate_references(
        self, resources: list[ResourceConfig], env_config: dict[str, Any], report: ValidationReport
    ) -> None:
        """Validate that referenced OPNsense resources exist.

        Checks that aliases referenced in firewall rules actually exist, etc.

        Args:
            resources: Resources to validate
            env_config: Environment configuration
            report: ValidationReport to add results to
        """
        # Group resources by type
        aliases = [r for r in resources if r.type == "aliases"]
        vlans = [r for r in resources if r.type == "vlans"]
        firewall_rules = [r for r in resources if r.type == "firewall_rules"]

        alias_names = {a.name for a in aliases}
        vlan_names = {v.name for v in vlans}

        # Check firewall rules reference valid aliases
        for rule in firewall_rules:
            rule_config = rule.config
            source_alias = rule_config.get("source", {}).get("alias")
            dest_alias = rule_config.get("destination", {}).get("alias")

            if source_alias and source_alias not in alias_names:
                report.add_check(
                    check_name=f"firewall_rule_{rule.name}_source_alias",
                    passed=False,
                    message=(
                        f"Firewall rule '{rule.name}' references "
                        f"undefined source alias '{source_alias}'"
                    ),
                    level=ValidationLevel.ERROR,
                    details={"rule": rule.name, "missing_alias": source_alias},
                )

            if dest_alias and dest_alias not in alias_names:
                report.add_check(
                    check_name=f"firewall_rule_{rule.name}_dest_alias",
                    passed=False,
                    message=(
                        f"Firewall rule '{rule.name}' references "
                        f"undefined destination alias '{dest_alias}'"
                    ),
                    level=ValidationLevel.ERROR,
                    details={"rule": rule.name, "missing_alias": dest_alias},
                )

        # Check DHCP static maps reference valid VLANs
        dhcp_maps = [r for r in resources if r.type == "dhcp_static_maps"]
        for dhcp_map in dhcp_maps:
            interface = dhcp_map.config.get("interface")
            if interface and interface not in vlan_names:
                report.add_check(
                    check_name=f"dhcp_static_map_{dhcp_map.name}_interface",
                    passed=False,
                    message=(
                        f"DHCP static map '{dhcp_map.name}' references undefined VLAN '{interface}'"
                    ),
                    level=ValidationLevel.WARNING,
                    details={"dhcp_map": dhcp_map.name, "missing_vlan": interface},
                )

        # If all checks passed, add a success message
        if not report.has_errors():
            report.add_check(
                check_name="opnsense_references",
                passed=True,
                message=(
                    f"All OPNsense resource references valid "
                    f"({len(firewall_rules)} rules, {len(aliases)} aliases, "
                    f"{len(vlans)} VLANs)"
                ),
                level=ValidationLevel.INFO,
            )
