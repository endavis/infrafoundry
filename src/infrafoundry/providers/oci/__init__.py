"""OCI (Oracle Cloud Infrastructure) provider for InfraFoundry."""

import copy
from pathlib import Path
from typing import Any, ClassVar, override

import yaml

from infrafoundry.core.provider import ProviderBase, ResourceConfig
from infrafoundry.core.provider_mixins import (
    ResourceGrouperMixin,
    TemplateRendererMixin,
    TerraformGeneratorMixin,
)
from infrafoundry.core.types import EnvironmentData
from infrafoundry.core.validation import ValidationReport

from .validator import OCIValidator


class OCIProvider(
    ProviderBase,
    TemplateRendererMixin,
    ResourceGrouperMixin,
    TerraformGeneratorMixin,
):
    """OCI provider for managing VCNs, subnets, and compute instances."""

    _OCI_TFVARS_MAPPING: ClassVar[dict[str, str]] = {
        "tenancy_ocid": "oci_tenancy_ocid",
        "user_ocid": "oci_user_ocid",
        "fingerprint": "oci_fingerprint",
        "private_key_path": "oci_private_key_path",
        "region": "oci_region",
        "compartment_ocid": "oci_compartment_ocid",
    }

    def __init__(self, config_dir: Path, output_dir: Path) -> None:
        """Initialize OCI provider."""
        super().__init__("oci", config_dir, output_dir)
        self.fail_on_missing_snippets = False
        self._setup_template_environment()

    @override
    def validate_config(self, config: dict[str, Any]) -> bool:
        """Validate OCI resource configuration."""
        required_fields = ["name"]
        return all(field in config for field in required_fields)

    @override
    def validate_connectivity(self, env_config: EnvironmentData, report: ValidationReport) -> None:
        """Validate connectivity to OCI API."""
        validator = OCIValidator(env_config, report)
        validator.validate_connectivity()

    @override
    def validate_references(
        self, resources: list[ResourceConfig], env_config: EnvironmentData, report: ValidationReport
    ) -> None:
        """Validate that referenced OCI resources exist."""
        validator = OCIValidator(env_config, report)
        validator.validate_references(resources)

    @override
    def get_terraform_env_vars(self) -> dict[str, str]:
        """Return TF_VAR_* env vars for OCI provider."""
        return self.build_terraform_env_vars(
            provider_name="oci",
            mapping=self._OCI_TFVARS_MAPPING,
        )

    @override
    def generate_terraform(self, resources: list[ResourceConfig]) -> None:
        """Generate Terraform configuration for OCI resources."""
        resources_by_type = self.prepare_terraform_generation(resources)

        # Generate backend configuration if remote backend is configured
        self.render_backend()

        # Generate provider configuration and variables
        self.render_provider_and_variables()

        # Generate VCN and subnet resources
        if "vcn" in resources_by_type or "subnet" in resources_by_type:
            self._generate_vcn_terraform(
                resources_by_type.get("vcn", []),
                resources_by_type.get("subnet", []),
            )

        # Generate compute instances
        if "instance" in resources_by_type:
            self._generate_instances_terraform(resources_by_type["instance"])

        # Generate outputs
        self.render_outputs_terraform(resources_by_type)

    def _generate_vcn_terraform(
        self, vcns: list[ResourceConfig], subnets: list[ResourceConfig]
    ) -> None:
        """Generate Terraform for OCI VCNs and subnets."""
        self.render_and_write_terraform(
            "oci/vcn.tf.j2",
            context={"vcns": vcns, "subnets": subnets},
            output_name="vcn.tf",
        )

    def _generate_instances_terraform(self, instances: list[ResourceConfig]) -> None:
        """Generate Terraform for OCI compute instances."""
        processed_instances = []
        for instance in instances:
            processed = self._process_cloud_init_snippets(instance)
            processed_instances.append(processed)

        self.render_and_write_terraform(
            "oci/instances.tf.j2",
            context={"instances": processed_instances},
            output_name="instances.tf",
        )

    def _process_cloud_init_snippets(self, instance: ResourceConfig) -> ResourceConfig:
        """Process cloud-init snippets and merge them into instance config."""
        instance_copy = copy.deepcopy(instance)
        config = instance_copy.config

        if "cloud_init_snippets" not in config:
            return instance_copy

        snippet_names = config.get("cloud_init_snippets", [])
        cloud_init_vars = config.get("cloud_init_vars", {})

        merged_cloud_init: dict[Any, Any] = {}

        for snippet_name in snippet_names:
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
                continue

            with open(snippet_path) as f:
                snippet_content = f.read()

                for var_name, var_value in cloud_init_vars.items():
                    snippet_content = snippet_content.replace(f"${{{var_name}}}", str(var_value))

                snippet_data = yaml.safe_load(snippet_content)

                if snippet_data:
                    self._deep_merge(merged_cloud_init, snippet_data)

        if merged_cloud_init:
            config["cloud_init_merged"] = merged_cloud_init

        return instance_copy

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

    @override
    def generate_ansible(self, resources: list[ResourceConfig]) -> None:
        """Generate Ansible playbooks for OCI post-configuration."""
        self.ensure_directories()

        instances = [r for r in resources if r.type == "instance"]

        # Generate ansible.cfg with roles_path
        # config_dir is {config_repo}/envs, parent is config repo root
        roles_dir = self.config_dir.parent / "roles"
        content = self.render_template(
            "oci/ansible.cfg.j2",
            {
                "roles_path": str(roles_dir.resolve()),
            },
        )
        self._write_ansible_file("ansible.cfg", content)

        # Build role_groups: ordered dict of {role_name: [instances]}
        role_groups: dict[str, list[ResourceConfig]] = {}
        for inst in instances:
            for role in inst.config.get("ansible_roles", []):
                if role not in role_groups:
                    role_groups[role] = []
                role_groups[role].append(inst)

        # Generate playbook and inventory with role grouping
        content = self.render_template("oci/playbook.yml.j2", {"role_groups": role_groups})
        self._write_ansible_file("playbook.yml", content)

        content = self.render_template("oci/inventory.yml.j2", {"role_groups": role_groups})
        self._write_ansible_file("inventory.yml", content)

    @override
    def get_resource_types(self) -> list[str]:
        """Get supported resource types."""
        return ["vcn", "subnet", "instance"]

    @override
    def get_terraform_resource_types(self) -> dict[str, list[str]]:
        """Map InfraFoundry resource types to terraform resource types."""
        return {
            "instance": ["oci_core_instance"],
            "vcn": ["oci_core_vcn"],
        }

    @override
    def get_dependencies(self) -> dict[str, list[str]]:
        """Get resource dependencies."""
        return {
            "instance": ["vcn", "subnet"],
            "subnet": ["vcn"],
            "vcn": [],
        }
