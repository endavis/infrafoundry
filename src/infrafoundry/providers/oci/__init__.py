"""OCI (Oracle Cloud Infrastructure) provider for InfraFoundry."""

import copy
from pathlib import Path
from typing import Any, ClassVar, override

from infrafoundry.core.config.models import EnvironmentConfig
from infrafoundry.core.provider import ProviderBase, ResourceConfig
from infrafoundry.core.provider_mixins import (
    CloudInitMixin,
    ResourceGrouperMixin,
    TemplateRendererMixin,
    TerraformGeneratorMixin,
    sanitize_secret_ref_to_tf_var,
)
from infrafoundry.core.tailscale import process_tailscale_config
from infrafoundry.core.validation import ValidationReport

from .validator import OCIValidator


class OCIProvider(
    ProviderBase,
    TemplateRendererMixin,
    ResourceGrouperMixin,
    TerraformGeneratorMixin,
    CloudInitMixin,
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
        # Cache of resources from the most recent generate_terraform call.
        # Used by get_terraform_env_vars to resolve resource-level
        # ``terraform_secrets`` references into TF_VAR_* env vars.
        self._last_terraform_resources: list[ResourceConfig] = []
        self._setup_template_environment()

    @override
    def validate_config(self, config: dict[str, Any]) -> bool:
        """Validate OCI resource configuration."""
        required_fields = ["name"]
        return all(field in config for field in required_fields)

    @override
    def validate_connectivity(
        self, env_config: EnvironmentConfig, report: ValidationReport
    ) -> None:
        """Validate connectivity to OCI API."""
        validator = OCIValidator(env_config, report)
        validator.validate_connectivity()

    @override
    def validate_references(
        self,
        resources: list[ResourceConfig],
        env_config: EnvironmentConfig,
        report: ValidationReport,
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
            resources=self._last_terraform_resources,
        )

    @override
    def generate_terraform(self, resources: list[ResourceConfig]) -> None:
        """Generate Terraform configuration for OCI resources."""
        resources_by_type = self.prepare_terraform_generation(resources)

        # Pre-process instances FIRST so any ``tailscale:`` blocks
        # auto-populate ``terraform_secrets`` on the resource. This must
        # happen before ``collect_terraform_secret_refs`` runs so the
        # variables.tf template sees the dynamic sensitive vars.
        processed_instances = [
            self._process_cloud_init_snippets(instance)
            for instance in resources_by_type.get("instance", [])
        ]
        if processed_instances:
            resources_by_type["instance"] = processed_instances

        # Cache the post-processed resources so get_terraform_env_vars can
        # resolve all ``terraform_secrets`` references (including the ones
        # auto-populated by process_tailscale_config) at apply time.
        all_processed: list[ResourceConfig] = []
        for type_name, type_resources in resources_by_type.items():
            if type_name == "instance":
                all_processed.extend(type_resources)
            else:
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

        # Generate provider configuration and variables
        self.render_provider_and_variables(
            variables_context={"terraform_secret_vars": terraform_secret_vars},
        )

        # Generate VCN and subnet resources
        if "vcn" in resources_by_type or "subnet" in resources_by_type:
            self._generate_vcn_terraform(
                resources_by_type.get("vcn", []),
                resources_by_type.get("subnet", []),
            )

        # Generate compute instances (already processed above)
        if processed_instances:
            self.render_and_write_terraform(
                "oci/instances.tf.j2",
                context={"instances": processed_instances},
                output_name="instances.tf",
            )

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
        """Generate Terraform for OCI compute instances.

        Note: ``generate_terraform`` now pre-processes instances inline so
        the secrets→TF_VAR_* bridge can see auto-populated terraform_secrets
        before variables.tf is rendered. This method is kept for backwards
        compatibility but the inline path in ``generate_terraform`` is the
        primary entry point.
        """
        processed_instances = [self._process_cloud_init_snippets(i) for i in instances]
        self.render_and_write_terraform(
            "oci/instances.tf.j2",
            context={"instances": processed_instances},
            output_name="instances.tf",
        )

    def _process_cloud_init_snippets(self, instance: ResourceConfig) -> ResourceConfig:
        """Process cloud-init snippets or tailscale module and merge into config.

        Two mutually exclusive paths:

        - If the instance config has a ``tailscale:`` block, it is validated
          and normalized into a ``tailscale_module_config`` dict. The
          resource's ``terraform_secrets`` list is auto-populated with the
          referenced secret paths so the framework's secrets→TF_VAR_* bridge
          (phase 1 of #212) injects the values at apply time.
        - Otherwise, any ``cloud_init_snippets`` are loaded, merged, and
          stored as ``cloud_init_merged`` for the existing template path.

        Args:
            instance: Instance resource config.

        Returns:
            Copy of the instance config with exactly one of
            ``cloud_init_merged`` or ``tailscale_module_config`` set
            (or neither, if no cloud-init is configured).
        """
        instance_copy = copy.deepcopy(instance)
        # OCI's user_data expects base64; the Tailscale module's default
        # ``base64_encode = true`` matches that, so we pass True here.
        tailscale_module_config = process_tailscale_config(instance_copy, base64_encode=True)
        if tailscale_module_config is not None:
            instance_copy.config["tailscale_module_config"] = tailscale_module_config
            return instance_copy
        merged = self._merge_cloud_init_snippets(instance_copy.config)
        if merged:
            instance_copy.config["cloud_init_merged"] = merged
        return instance_copy

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
