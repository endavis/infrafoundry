"""Instance validation for the AWS provider."""

from __future__ import annotations

from typing import override

from infrafoundry.core.protocols import SpecializedValidator
from infrafoundry.core.validation import ValidationReport

from ._common import fail
from .context import AWSConfigContext


class InstanceValidator(SpecializedValidator[AWSConfigContext]):
    """Checks ``instance`` resources."""

    def __init__(self, report: ValidationReport) -> None:
        """Initialize the validator.

        Args:
            report: ValidationReport to add results to
        """
        self.report = report

    @override
    def validate(self, context: AWSConfigContext) -> None:
        """Check every ``instance`` resource.

        Args:
            context: Resources and the declared security group names.
        """
        for resource in context.resources:
            if resource.type != "instance":
                continue
            name = resource.name
            config = resource.config
            prefix = f"aws_instance_{name}"
            has_ami = bool(config.get("ami"))
            has_ssm = bool(config.get("ami_ssm_parameter"))
            if has_ami == has_ssm:
                fail(
                    self.report,
                    f"{prefix}_ami",
                    f"instance '{name}': set exactly one of ami or ami_ssm_parameter",
                )
            for key in ("instance_type", "subnet_id"):
                if not config.get(key):
                    fail(self.report, f"{prefix}_{key}", f"instance '{name}': {key} is required")
            groups = config.get("security_groups") or []
            if not isinstance(groups, list):
                fail(
                    self.report,
                    f"{prefix}_security_groups",
                    f"instance '{name}': security_groups must be a list",
                )
                groups = []
            for ref in groups:
                if isinstance(ref, str) and ref.startswith("sg-"):
                    continue
                if ref not in context.security_group_names:
                    fail(
                        self.report,
                        f"{prefix}_security_groups",
                        f"instance '{name}': security group '{ref}' is not a declared "
                        "security_group or an sg- id",
                    )
            self._check_ipv6(name, config)

    def _check_ipv6(self, name: str, config: dict[str, object]) -> None:
        """Validate the IPv6 settings."""
        if not config.get("ipv6_only"):
            return
        if config.get("associate_public_ip_address") is True:
            fail(
                self.report,
                f"aws_instance_{name}_ipv6_only",
                f"instance '{name}': ipv6_only conflicts with associate_public_ip_address: true",
            )
        count = config.get("ipv6_address_count", 1)
        if not isinstance(count, int) or isinstance(count, bool) or count < 1:
            fail(
                self.report,
                f"aws_instance_{name}_ipv6_address_count",
                f"instance '{name}': ipv6_address_count must be an integer >= 1 with ipv6_only",
            )
