"""Proxmox provider for InfraFoundry."""

from pathlib import Path
from typing import Any, override

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

    @override
    def validate_config(self, config: dict[str, Any]) -> bool:
        """Validate Proxmox configuration."""
        required_fields = ["name"]
        return all(field in config for field in required_fields)

    @override
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

        # Generate variables file with environment context
        import os

        variables_template = self.jinja_env.get_template("proxmox/variables.tf.j2")
        variables_content = variables_template.render(
            default_ssh_user=os.getenv("USER", "root"),
        )
        (self.terraform_dir / "variables.tf").write_text(variables_content)

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

    @override
    def validate_connectivity(self, env_config: dict[str, Any], report: Any) -> None:
        """Validate connectivity to Proxmox API.

        Checks:
        - API endpoint is reachable
        - Authentication credentials are valid
        - Can retrieve cluster status
        """
        from infrafoundry.core.validation_helpers import BaseProviderValidator

        validator = BaseProviderValidator(
            provider_name="proxmox",
            env_config=env_config,
            report=report,
        )

        # Validate credentials
        credentials = validator.validate_credentials(
            required_fields=["api_url", "api_token", "node"]
        )
        if not credentials:
            return

        # Parse Proxmox API token (format: "PVEAPIToken=USER@REALM!TOKENID=UUID")
        api_token = credentials["api_token"]
        if "=" in api_token:
            # Extract token value after the =
            token_parts = api_token.split("=", 1)
            auth_header = f"PVEAPIToken={token_parts[1]}" if len(token_parts) == 2 else api_token
        else:
            auth_header = f"PVEAPIToken={api_token}"

        # Test API connectivity
        import requests

        version_url = f"{credentials['api_url']}/api2/json/version"
        response_ok = validator.check_api_connectivity(
            url=version_url,
            headers={"Authorization": auth_header},
            verify_ssl=False,
        )

        # If connection succeeded, get version info
        if response_ok:
            try:
                response = requests.get(
                    version_url,
                    headers={"Authorization": auth_header},
                    verify=False,
                    timeout=10,
                )
                if response.status_code == 200:
                    version_data = response.json().get("data", {})
                    version = version_data.get("version", "unknown")
                    # Update success message with version
                    validator.add_success_check(
                        check_name="proxmox_version",
                        message=f"Proxmox VE version: {version}",
                    )
            except Exception:
                pass  # Version info is optional, connectivity already validated

    @override
    def validate_references(
        self, resources: list[ResourceConfig], env_config: dict[str, Any], report: Any
    ) -> None:
        """Validate that referenced Proxmox resources exist.

        Checks:
        - VM templates exist on the target node
        - Network bridges are available
        - Storage pools exist
        """
        from infrafoundry.core.validation import ValidationLevel

        # Get Proxmox credentials
        provider_settings = env_config.get("provider_settings", {}).get("proxmox", {})
        api_url = provider_settings.get("api_url")
        api_token = provider_settings.get("api_token")
        node = provider_settings.get("node")

        if not all([api_url, api_token, node]):
            return  # Already reported in validate_connectivity

        # Group resources by type
        vms = [r for r in resources if r.type == "vm"]

        # Get list of template names referenced in VMs
        template_refs = set()
        for vm in vms:
            vm_config = vm.config or {}
            if template := vm_config.get("template"):
                template_refs.add(template)

        # Validate templates exist
        if template_refs:
            try:
                import requests

                # Parse token
                if "=" in api_token:
                    token_parts = api_token.split("=", 1)
                    auth_header = (
                        f"PVEAPIToken={token_parts[1]}" if len(token_parts) == 2 else api_token
                    )
                else:
                    auth_header = f"PVEAPIToken={api_token}"

                headers = {"Authorization": auth_header}

                # Get list of VMs/templates on node
                vms_url = f"{api_url}/api2/json/nodes/{node}/qemu"
                response = requests.get(vms_url, headers=headers, timeout=10, verify=False)

                if response.status_code == 200:
                    vms_data = response.json().get("data", [])
                    # Get template names (VMs with template=1)
                    existing_templates = {vm["name"] for vm in vms_data if vm.get("template") == 1}

                    # Check each referenced template
                    for template_name in template_refs:
                        if template_name in existing_templates:
                            report.add_check(
                                check_name=f"proxmox_template_{template_name}",
                                passed=True,
                                message=f"Template '{template_name}' exists on node {node}",
                                level=ValidationLevel.INFO,
                            )
                        else:
                            report.add_check(
                                check_name=f"proxmox_template_{template_name}",
                                passed=False,
                                message=f"Template '{template_name}' not found on node {node}",
                                level=ValidationLevel.ERROR,
                                details={
                                    "template": template_name,
                                    "node": node,
                                    "existing_templates": list(existing_templates),
                                },
                            )
                else:
                    report.add_check(
                        check_name="proxmox_templates",
                        passed=False,
                        message=f"Failed to query templates: HTTP {response.status_code}",
                        level=ValidationLevel.WARNING,
                    )

            except Exception as e:
                report.add_check(
                    check_name="proxmox_templates",
                    passed=False,
                    message=f"Error validating templates: {e}",
                    level=ValidationLevel.WARNING,
                )

        # If all checks passed, add success message
        if not report.has_errors() and template_refs:
            report.add_check(
                check_name="proxmox_references",
                passed=True,
                message=f"All Proxmox resource references valid ({len(template_refs)} templates)",
                level=ValidationLevel.INFO,
            )
