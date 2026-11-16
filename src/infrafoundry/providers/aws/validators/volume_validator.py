"""EBS volume validation for the AWS provider."""

from __future__ import annotations

import re
from typing import override

from infrafoundry.core.protocols import SpecializedValidator
from infrafoundry.core.validation import ValidationReport

from ._common import fail
from .context import AWSConfigContext

DEVICE_NAME_RE = re.compile(r"^/dev/(sd[f-p]|xvd[f-p])$")
VOLUME_TYPES = frozenset({"gp3", "gp2", "io1", "io2", "st1", "sc1", "standard"})


class EbsVolumeValidator(SpecializedValidator[AWSConfigContext]):
    """Checks ``ebs_volume`` resources."""

    def __init__(self, report: ValidationReport) -> None:
        """Initialize the validator.

        Args:
            report: ValidationReport to add results to
        """
        self.report = report

    @override
    def validate(self, context: AWSConfigContext) -> None:
        """Check every ``ebs_volume`` resource.

        Args:
            context: Resources and the declared instances.
        """
        for resource in context.resources:
            if resource.type != "ebs_volume":
                continue
            name = resource.name
            config = resource.config
            prefix = f"aws_ebs_volume_{name}"
            zone = config.get("availability_zone")
            if not zone:
                fail(
                    self.report,
                    f"{prefix}_availability_zone",
                    f"ebs_volume '{name}': availability_zone is required",
                )
            size = config.get("size")
            if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
                fail(
                    self.report,
                    f"{prefix}_size",
                    f"ebs_volume '{name}': size is required and must be an integer > 0",
                )
            volume_type = config.get("type", "gp3")
            if volume_type not in VOLUME_TYPES:
                fail(
                    self.report,
                    f"{prefix}_type",
                    f"ebs_volume '{name}': type must be one of {sorted(VOLUME_TYPES)}, "
                    f"got {volume_type!r}",
                )
            device = config.get("device_name", "/dev/sdf")
            if not isinstance(device, str) or not DEVICE_NAME_RE.match(device):
                fail(
                    self.report,
                    f"{prefix}_device_name",
                    f"ebs_volume '{name}': device_name must match /dev/sd[f-p] or /dev/xvd[f-p], "
                    f"got {device!r}",
                )
            instance = config.get("instance")
            instance_id = config.get("instance_id")
            if bool(instance) == bool(instance_id):
                fail(
                    self.report,
                    f"{prefix}_instance",
                    f"ebs_volume '{name}': set exactly one of instance or instance_id",
                )
            elif instance:
                target = context.instances_by_name.get(str(instance))
                if target is None:
                    fail(
                        self.report,
                        f"{prefix}_instance",
                        f"ebs_volume '{name}': instance '{instance}' is not a declared instance",
                    )
                else:
                    instance_zone = target.config.get("availability_zone")
                    if instance_zone and zone and instance_zone != zone:
                        fail(
                            self.report,
                            f"{prefix}_availability_zone",
                            f"ebs_volume '{name}': availability_zone '{zone}' differs from "
                            f"instance '{instance}' zone '{instance_zone}'",
                        )
