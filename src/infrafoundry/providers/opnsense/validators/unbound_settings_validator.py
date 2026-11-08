"""Unbound general and advanced settings validator for OPNsense (#1091).

Pure-check, never-mutate validator for the ``unbound.settings`` singleton. Every problem
reported by :func:`~infrafoundry.providers.opnsense.services.unbound_settings.check_config`
(the same check ``build_desired`` raises on) becomes an ERROR: unknown keys, fields owned by
``unbound.advanced``, and wrongly typed or out-of-range values.
"""

from __future__ import annotations

from typing import override

from infrafoundry.core.protocols import SpecializedValidator
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.opnsense.validators.context import OPNsenseValidationContext

from ..services.unbound_settings import check_config


class UnboundSettingsValidator(SpecializedValidator[OPNsenseValidationContext]):
    """Validates ``unbound.settings`` singleton resources."""

    def __init__(self, report: ValidationReport) -> None:
        """Initialize validator.

        Args:
            report: ValidationReport to add results to.
        """
        self.report = report

    @override
    def validate(self, context: OPNsenseValidationContext) -> None:
        """Validate ``unbound.settings`` resources.

        Args:
            context: Validation context carrying the resources this validator checks.
        """
        for resource in context.resources:
            for suffix, message in check_config(resource.config):
                self.report.add_check(
                    check_name=f"unbound_settings_{resource.name}_{suffix}",
                    passed=False,
                    message=message,
                    level=ValidationLevel.ERROR,
                )
