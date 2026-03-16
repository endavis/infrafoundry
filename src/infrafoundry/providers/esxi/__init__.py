"""ESXi provider for InfraFoundry."""

import copy
import logging
from pathlib import Path
from typing import Any, override

from infrafoundry.core.provider import ProviderBase, ResourceConfig
from infrafoundry.core.provider_mixins import (
    ResourceGrouperMixin,
    TemplateRendererMixin,
    TerraformGeneratorMixin,
)
from infrafoundry.core.types import EnvironmentData
from infrafoundry.core.validation import ValidationReport

from .validator import EsxiValidator

logger = logging.getLogger(__name__)


class EsxiProvider(
    ProviderBase,
    TemplateRendererMixin,
    ResourceGrouperMixin,
    TerraformGeneratorMixin,
):
    """ESXi provider for managing resources inside ESXi hosts.

    Supports managing vswitches, portgroups, and VMs on one or more ESXi hosts
    using the josenk/esxi Terraform provider with aliased provider blocks.
    """

    def __init__(self, config_dir: Path, output_dir: Path) -> None:
        """Initialize ESXi provider."""
        super().__init__("esxi", config_dir, output_dir)
        self._setup_template_environment()

    @staticmethod
    def _host_alias(name: str) -> str:
        """Normalize a host name to a valid Terraform alias.

        Converts hyphens and dots to underscores for use in Terraform
        provider aliases and resource names.

        Args:
            name: Host name to normalize (e.g., 'esxi-ontap-01')

        Returns:
            Normalized alias (e.g., 'esxi_ontap_01')
        """
        return name.replace("-", "_").replace(".", "_")

    @override
    def validate_config(self, config: dict[str, Any]) -> bool:
        """Validate ESXi resource configuration.

        Args:
            config: Configuration dictionary to validate

        Returns:
            True if valid, False otherwise
        """
        required_fields = ["name"]
        return all(field in config for field in required_fields)

    @override
    def validate_connectivity(self, env_config: EnvironmentData, report: ValidationReport) -> None:
        """Validate connectivity to ESXi hosts."""
        validator = EsxiValidator(env_config, report)
        validator.validate_connectivity()

    @override
    def validate_references(
        self, resources: list[ResourceConfig], env_config: EnvironmentData, report: ValidationReport
    ) -> None:
        """Validate that referenced ESXi resources exist."""
        validator = EsxiValidator(env_config, report)
        validator.validate_references(resources)

    @override
    def generate_terraform(self, resources: list[ResourceConfig]) -> None:
        """Generate Terraform configuration for ESXi resources."""
        resources_by_type = self.prepare_terraform_generation(resources)

        # Generate backend configuration if remote backend is configured
        self.render_backend()

        # Collect unique hosts from resources
        hosts = self._collect_hosts(resources)

        # Generate provider and variables with host context
        self.render_and_write_terraform(
            "esxi/provider.tf.j2",
            context={"hosts": hosts},
            output_name="provider.tf",
        )
        self.render_and_write_terraform(
            "esxi/variables.tf.j2",
            context={"hosts": hosts},
            output_name="variables.tf",
        )

        # Generate multi-host tfvars
        self._generate_multi_host_tfvars(hosts)

        # Generate resources by type
        if "vswitch" in resources_by_type:
            self._generate_vswitches_terraform(resources_by_type["vswitch"])

        if "portgroup" in resources_by_type:
            self._generate_portgroups_terraform(resources_by_type["portgroup"])

        if "vm" in resources_by_type:
            processed_vms = [self._normalize_vm_config(vm) for vm in resources_by_type["vm"]]
            self._generate_vms_terraform(processed_vms)

        if "ovf_deployment" in resources_by_type:
            self._generate_ovf_deployments_terraform(resources_by_type["ovf_deployment"])

        # Generate outputs
        self.render_outputs_terraform(resources_by_type)

    @override
    def generate_ansible(self, resources: list[ResourceConfig]) -> None:
        """Generate Ansible playbooks for ESXi post-configuration.

        Args:
            resources: List of resources to generate Ansible for
        """
        # Minimal stub: ESXi management is primarily Terraform-based
        self.ensure_directories()

    @override
    def get_resource_types(self) -> list[str]:
        """Get supported resource types."""
        return ["vswitch", "portgroup", "vm", "ovf_deployment"]

    @override
    def get_terraform_resource_types(self) -> dict[str, list[str]]:
        """Map InfraFoundry resource types to terraform resource types."""
        return {
            "vm": ["esxi_guest"],
            "ovf_deployment": ["terraform_data"],
            "vswitch": ["esxi_vswitch"],
            "portgroup": ["esxi_portgroup"],
        }

    @override
    def get_dependencies(self) -> dict[str, list[str]]:
        """Get resource dependencies."""
        return {
            "vm": ["vswitch", "portgroup"],
            "ovf_deployment": ["vswitch", "portgroup"],
            "portgroup": ["vswitch"],
            "vswitch": [],
        }

    def _collect_hosts(self, resources: list[ResourceConfig]) -> list[dict[str, str]]:
        """Collect unique hosts from all resources.

        Args:
            resources: List of resources to extract hosts from

        Returns:
            List of host dicts with 'name' and 'alias' keys, sorted by name
        """
        host_names: set[str] = set()
        for resource in resources:
            host = resource.config.get("host")
            if host:
                host_names.add(host)

        return sorted(
            [{"name": name, "alias": self._host_alias(name)} for name in host_names],
            key=lambda h: h["name"],
        )

    def _generate_multi_host_tfvars(self, hosts: list[dict[str, str]]) -> None:
        """Generate terraform.tfvars with per-host non-sensitive settings.

        Writes hostname and username to tfvars. Passwords are NOT written to
        disk — they must be provided via TF_VAR_esxi_password_<alias>
        environment variables.

        Args:
            hosts: List of host dicts with 'name' and 'alias' keys
        """
        env_config = self._load_environment_config()
        if not env_config:
            return

        provider_settings = env_config.get_provider_settings("esxi")
        if not provider_settings:
            return

        lines = [self._TFVARS_HEADER]
        hosts_config = provider_settings.get("hosts", {})

        for host in hosts:
            alias = host["alias"]
            host_settings = hosts_config.get(host["name"], {})

            hostname = host_settings.get("hostname", host["name"])
            username = host_settings.get("username", "root")

            lines.append(self._format_tfvar_line(f"esxi_hostname_{alias}", hostname))
            lines.append(self._format_tfvar_line(f"esxi_username_{alias}", username))
            # Password is sensitive — provide via TF_VAR_esxi_password_<alias>

        self._write_tfvars_lines(lines)

    def _normalize_vm_config(self, vm: ResourceConfig) -> ResourceConfig:
        """Normalize VM config for template consumption.

        Ensures the network field is always a list of dicts.

        Args:
            vm: The VM resource config to normalize.

        Returns:
            The VM resource config with normalized network field.
        """
        vm_copy = copy.deepcopy(vm)
        config = vm_copy.config

        network = config.get("network")
        if isinstance(network, dict):
            config["network"] = [network]

        return vm_copy

    def _generate_vswitches_terraform(self, vswitches: list[ResourceConfig]) -> None:
        """Generate Terraform for ESXi vswitches."""
        self.render_and_write_terraform(
            "esxi/vswitch.tf.j2",
            context={"vswitches": vswitches, "host_alias": self._host_alias},
            output_name="vswitch.tf",
        )

    def _generate_portgroups_terraform(self, portgroups: list[ResourceConfig]) -> None:
        """Generate Terraform for ESXi portgroups."""
        self.render_and_write_terraform(
            "esxi/portgroup.tf.j2",
            context={"portgroups": portgroups, "host_alias": self._host_alias},
            output_name="portgroup.tf",
        )

    def _generate_vms_terraform(self, vms: list[ResourceConfig]) -> None:
        """Generate Terraform for ESXi VMs (guests)."""
        self.render_and_write_terraform(
            "esxi/vm.tf.j2",
            context={"vms": vms, "host_alias": self._host_alias},
            output_name="vm.tf",
        )

    def _generate_ovf_deployments_terraform(self, ovf_deployments: list[ResourceConfig]) -> None:
        """Generate Terraform for ESXi OVF deployments."""
        self.render_and_write_terraform(
            "esxi/ovf_deployment.tf.j2",
            context={"ovf_deployments": ovf_deployments, "host_alias": self._host_alias},
            output_name="ovf_deployment.tf",
        )
