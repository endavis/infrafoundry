"""AWS provider for InfraFoundry.

Generates ``hashicorp/aws`` Terraform for EC2 instances, security groups and
EBS volumes. Credentials come from Terraform's standard AWS chain; only the
region and profile are passed through ``provider_settings.aws``.
"""

import copy
import json
import logging
from pathlib import Path
from typing import Any, ClassVar, override

from infrafoundry.core.config.models import EnvironmentConfig
from infrafoundry.core.exceptions import SchemaValidationError
from infrafoundry.core.provider import ProviderBase, ResourceConfig
from infrafoundry.core.provider_mixins import (
    CloudInitMixin,
    ResourceGrouperMixin,
    TemplateRendererMixin,
    TerraformGeneratorMixin,
    collect_terraform_secret_vars,
)
from infrafoundry.core.tailscale import process_tailscale_config
from infrafoundry.core.validation import ValidationLevel, ValidationReport, run_validators
from infrafoundry.providers.tailscale.hcl import hcl_list, hcl_string

from .validator import AWSValidator, check_tailscale_blocks, env_region_set
from .validators import (
    EbsVolumeValidator,
    InstanceValidator,
    SecurityGroupValidator,
    SettingsValidator,
)
from .validators.context import AWSConfigContext, AWSSettingsContext

logger = logging.getLogger(__name__)


def _hcl_json(value: Any) -> str:
    """Render ``value`` as a JSON object that HCL reads, with interpolation escaped."""
    return json.dumps(value).replace("${", "$${").replace("%{", "%%{")


class AWSProvider(
    ProviderBase,
    TemplateRendererMixin,
    ResourceGrouperMixin,
    TerraformGeneratorMixin,
    CloudInitMixin,
):
    """AWS provider for managing security groups, EC2 instances and EBS volumes."""

    _AWS_TFVARS_MAPPING: ClassVar[dict[str, str]] = {
        "region": "aws_region",
        "profile": "aws_profile",
    }

    def __init__(self, config_dir: Path, output_dir: Path) -> None:
        """Initialize AWS provider."""
        super().__init__("aws", config_dir, output_dir)
        self.fail_on_missing_snippets = False
        # Resources from the most recent generate_terraform call, so
        # get_terraform_env_vars can resolve their ``terraform_secrets``.
        self._last_terraform_resources: list[ResourceConfig] = []
        self._setup_template_environment()
        self.jinja_env.filters["hcl_string"] = hcl_string
        self.jinja_env.filters["hcl_list"] = hcl_list
        self.jinja_env.filters["hcl_json"] = _hcl_json

    @override
    def validate_config(self, config: dict[str, Any]) -> bool:
        """Validate AWS resource configuration."""
        return all(field in config for field in ["name"])

    @override
    def validate_connectivity(
        self, env_config: EnvironmentConfig, report: ValidationReport
    ) -> None:
        """Check the provider settings (config only, no network call)."""
        AWSValidator(env_config, report).validate_connectivity()

    @override
    def validate_references(
        self,
        resources: list[ResourceConfig],
        env_config: EnvironmentConfig,
        report: ValidationReport,
    ) -> None:
        """Validate AWS resource configuration and cross-references."""
        AWSValidator(env_config, report).validate_references(resources)

    def validate_references_in_context(
        self,
        resources: list[ResourceConfig],
        reference_resources: list[ResourceConfig],
        env_config: EnvironmentConfig,
        report: ValidationReport,
    ) -> None:
        """Validate *resources*, resolving names against *reference_resources* (#1568)."""
        AWSValidator(env_config, report).validate_references(resources, reference_resources)

    def validate_offline(
        self,
        resources: list[ResourceConfig],
        reference_resources: list[ResourceConfig],
        env_config: EnvironmentConfig,
        report: ValidationReport,
    ) -> None:
        """Run AWS validation, which is already offline (#1433)."""
        # validate_references of this provider makes no network call, so it is the offline part.
        AWSValidator(env_config, report).validate_references(resources)

    @override
    def get_resource_types(self) -> list[str]:
        """Get supported resource types."""
        return ["security_group", "instance", "ebs_volume"]

    @override
    def get_terraform_resource_types(self) -> dict[str, list[str]]:
        """Map InfraFoundry resource types to terraform resource types."""
        return {
            "security_group": ["aws_security_group"],
            "instance": ["aws_instance"],
            "ebs_volume": ["aws_ebs_volume"],
        }

    @override
    def get_dependencies(self) -> dict[str, list[str]]:
        """Get resource dependencies."""
        return {
            "security_group": [],
            "instance": ["security_group"],
            "ebs_volume": ["instance"],
        }

    @override
    def get_state_addresses_kept_on_destroy(self, resources: list[ResourceConfig]) -> list[str]:
        """Return the protected ``ebs_volume`` addresses to forget on destroy.

        A volume with ``prevent_destroy`` (the default) cannot be destroyed by
        Terraform, so it is dropped from state and left in AWS.

        Args:
            resources: The resources this destroy covers.

        Returns:
            Terraform addresses of ``ebs_volume`` resources that are protected.
        """
        return [
            f"aws_ebs_volume.{r.name.replace('-', '_')}"
            for r in resources
            if r.type == "ebs_volume" and r.config.get("prevent_destroy", True) is not False
        ]

    @override
    def get_terraform_env_vars(self) -> dict[str, str]:
        """Return TF_VAR_* env vars (region, profile and resource secrets)."""
        return self.build_terraform_env_vars(
            "aws", self._AWS_TFVARS_MAPPING, resources=self._last_terraform_resources
        )

    @override
    def generate_terraform(self, resources: list[ResourceConfig]) -> None:
        """Generate Terraform configuration for AWS resources."""
        resources_by_type = self.prepare_terraform_generation(resources)
        self._validate_resource_configs(resources)

        # Process instances first so ``tailscale:`` blocks populate
        # ``terraform_secrets`` before the secret variables are collected.
        instances = [
            self._process_cloud_init_snippets(i) for i in resources_by_type.get("instance", [])
        ]
        if instances:
            resources_by_type["instance"] = instances
        processed = [r for group in resources_by_type.values() for r in group]
        self._last_terraform_resources = processed

        self.render_backend()
        secret_vars = collect_terraform_secret_vars(processed)
        self.render_provider_and_variables(variables_context={"terraform_secret_vars": secret_vars})

        groups = resources_by_type.get("security_group", [])
        if groups:
            self.render_and_write_terraform(
                "aws/security_groups.tf.j2",
                context={"security_groups": groups},
                output_name="security_groups.tf",
            )
        if instances:
            self.render_and_write_terraform(
                "aws/instances.tf.j2",
                context={"instances": instances, "security_group_names": [g.name for g in groups]},
                output_name="instances.tf",
            )
        volumes = resources_by_type.get("ebs_volume", [])
        if volumes:
            self.render_and_write_terraform(
                "aws/ebs_volumes.tf.j2",
                context={"ebs_volumes": volumes},
                output_name="ebs_volumes.tf",
            )
        self.render_outputs_terraform(resources_by_type)

    def _process_cloud_init_snippets(self, instance: ResourceConfig) -> ResourceConfig:
        """Merge cloud-init snippets or the tailscale module into the instance config.

        Args:
            instance: Instance resource config.

        Returns:
            A copy with ``tailscale_module_config`` or ``cloud_init_merged`` set,
            or neither when no cloud-init is configured.
        """
        instance_copy = copy.deepcopy(instance)
        # user_data_base64 expects base64, the module's default.
        tailscale_module_config = process_tailscale_config(instance_copy, base64_encode=True)
        if tailscale_module_config is not None:
            instance_copy.config["tailscale_module_config"] = tailscale_module_config
            return instance_copy
        merged = self._merge_cloud_init_snippets(instance_copy.config)
        if merged:
            instance_copy.config["cloud_init_merged"] = merged
        return instance_copy

    def _validate_resource_configs(self, resources: list[ResourceConfig]) -> None:
        """Run the config validators; raise on ERROR-level findings.

        Args:
            resources: All resources being generated.

        Raises:
            SchemaValidationError: If any check failed at ERROR level.
        """
        report = ValidationReport()
        env_config = self._load_environment_config()
        settings = dict(env_config.get_provider_settings("aws") or {}) if env_config else {}
        run_validators(
            (SettingsValidator(report),),
            AWSSettingsContext(provider_settings=settings, env_region=env_region_set()),
        )
        check_tailscale_blocks(resources, report)
        run_validators(
            (
                SecurityGroupValidator(report),
                InstanceValidator(report),
                EbsVolumeValidator(report),
            ),
            AWSConfigContext.from_resources(resources),
        )
        for result in report.results:
            if not result.passed and result.level == ValidationLevel.WARNING:
                logger.warning("[%s] %s", result.check_name, result.message)
        if report.has_errors():
            lines = [
                f"  - [{r.check_name}] {r.message}"
                for r in report.results
                if not r.passed and r.level == ValidationLevel.ERROR
            ]
            raise SchemaValidationError(
                "AWS resource configuration validation failed:\n" + "\n".join(lines)
            )

    @override
    def generate_ansible(self, resources: list[ResourceConfig]) -> None:
        """AWS is Terraform-only; create the output directories."""
        self.ensure_directories()
