"""Provider-settings validation for the AWS provider (config only, no network)."""

from __future__ import annotations

from typing import override

from infrafoundry.core.protocols import SpecializedValidator
from infrafoundry.core.validation import ValidationLevel, ValidationReport

from ._common import fail
from .context import AWSSettingsContext

#: Credential keys that must never appear in YAML.
FORBIDDEN_KEYS = ("access_key", "secret_key", "token", "session_token")


class SettingsValidator(SpecializedValidator[AWSSettingsContext]):
    """Rejects credentials in settings and warns when no region is configured."""

    def __init__(self, report: ValidationReport) -> None:
        """Initialize the validator.

        Args:
            report: ValidationReport to add results to
        """
        self.report = report

    @override
    def validate(self, context: AWSSettingsContext) -> None:
        """Check ``provider_settings.aws``.

        Args:
            context: The settings and whether a region comes from the environment.
        """
        settings = context.provider_settings
        for key in FORBIDDEN_KEYS:
            if key in settings:
                fail(
                    self.report,
                    f"aws_settings_{key}",
                    f"provider_settings.aws.{key} is not allowed: credentials come from the "
                    "standard AWS chain (environment, shared config, SSO, instance role)",
                )
        if not settings.get("region") and not context.env_region:
            fail(
                self.report,
                "aws_settings_region",
                "No region in provider_settings.aws and no AWS_REGION or AWS_DEFAULT_REGION "
                "set; Terraform falls back to the shared config",
                ValidationLevel.WARNING,
            )
        self.report.add_check(
            check_name="aws_credentials",
            passed=True,
            message="AWS credentials are resolved by Terraform's AWS provider chain",
            level=ValidationLevel.INFO,
        )
