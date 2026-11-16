"""Validation logic for the AWS provider (config checks only, no network calls)."""

from __future__ import annotations

import copy
import os

from infrafoundry.core.config.models import EnvironmentConfig
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.tailscale import TailscaleSchemaError, process_tailscale_config
from infrafoundry.core.validation import ValidationLevel, ValidationReport, run_validators
from infrafoundry.core.validation_helpers import (
    BaseAPIValidator,
    validate_terraform_secrets_references,
)

from .validators import (
    EbsVolumeValidator,
    InstanceValidator,
    SecurityGroupValidator,
    SettingsValidator,
)
from .validators.context import AWSConfigContext, AWSSettingsContext


def env_region_set() -> bool:
    """Return True when the AWS region comes from the environment."""
    return bool(os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION"))


def check_tailscale_blocks(resources: list[ResourceConfig], report: ValidationReport) -> None:
    """Validate each instance's ``tailscale:`` block, recording schema errors.

    Works on a deep copy so the resource's ``terraform_secrets`` is not changed.

    Args:
        resources: All AWS resources.
        report: Report to add findings to.
    """
    for resource in resources:
        if resource.type != "instance" or (resource.config or {}).get("tailscale") is None:
            continue
        try:
            process_tailscale_config(copy.deepcopy(resource), base64_encode=True)
        except TailscaleSchemaError as exc:
            report.add_check(
                check_name=f"aws_tailscale_schema_{resource.name}",
                passed=False,
                message=str(exc),
                level=ValidationLevel.ERROR,
            )


class AWSValidator:
    """Validates AWS configuration.

    Credentials are resolved by Terraform's AWS provider, so no network call is made.
    """

    def __init__(self, env_config: EnvironmentConfig, report: ValidationReport) -> None:
        """Initialize the AWS validator.

        Args:
            env_config: Environment configuration including provider_settings
            report: ValidationReport to add results to
        """
        self.env_config = env_config
        self.report = report
        self.api_validator = BaseAPIValidator("aws", env_config, report)
        self.provider_settings = self.api_validator.provider_settings

    def validate_connectivity(self) -> None:
        """Check the provider settings (no network call)."""
        SettingsValidator(self.report).validate(
            AWSSettingsContext(
                provider_settings=self.provider_settings,
                env_region=env_region_set(),
            )
        )

    def validate_references(self, resources: list[ResourceConfig]) -> None:
        """Run the tailscale, secret-reference and resource-config validators.

        Args:
            resources: Resources to validate
        """
        check_tailscale_blocks(resources, self.report)
        validate_terraform_secrets_references("aws", resources, self.env_config, self.report)
        run_validators(
            (
                SecurityGroupValidator(self.report),
                InstanceValidator(self.report),
                EbsVolumeValidator(self.report),
            ),
            AWSConfigContext.from_resources(resources),
        )
