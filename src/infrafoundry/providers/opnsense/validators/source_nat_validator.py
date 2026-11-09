"""Outbound NAT mode validator for OPNsense (#1333).

Pure-check, never-mutate validator for the ``firewall.source_nat`` singleton.
Unknown keys are errors; ``snat_mode`` must be a string from ``ALLOWED_MODES``.
"""

from __future__ import annotations

from typing import override

from infrafoundry.core.protocols import SpecializedValidator
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.opnsense.validators.context import OPNsenseValidationContext

from ..services.source_nat import ALLOWED_MODES, FIELD_MAP


class SourceNatValidator(SpecializedValidator[OPNsenseValidationContext]):
    """Validates ``firewall.source_nat`` singleton resources."""

    def __init__(self, report: ValidationReport) -> None:
        """Initialize validator.

        Args:
            report: ValidationReport to add results to.
        """
        self.report = report

    @override
    def validate(self, context: OPNsenseValidationContext) -> None:
        """Validate ``firewall.source_nat`` resources.

        Args:
            context: Validation context carrying the resources this validator checks.
        """
        for resource in context.resources:
            self._validate_one(resource)

    def _error(self, check: str, message: str) -> None:
        self.report.add_check(
            check_name=check, passed=False, message=message, level=ValidationLevel.ERROR
        )

    def _validate_one(self, resource: ResourceConfig) -> None:
        check = f"source_nat_{resource.name}"
        config = resource.config
        for key in sorted(set(config) - set(FIELD_MAP)):
            self._error(f"{check}_{key}", f"firewall.source_nat has unknown key '{key}'")
        if "snat_mode" not in config:
            return
        mode = config["snat_mode"]
        if not isinstance(mode, str):
            self._error(
                f"{check}_snat_mode",
                f"firewall.source_nat snat_mode must be a string, got {type(mode).__name__}",
            )
        elif mode not in ALLOWED_MODES:
            self._error(
                f"{check}_snat_mode",
                f"firewall.source_nat snat_mode must be one of {', '.join(ALLOWED_MODES)}",
            )
