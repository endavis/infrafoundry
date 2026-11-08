"""Syslog-settings validator for OPNsense (#804).

Pure-check, never-mutate validator for the ``syslog.settings`` singleton. Unknown
keys are errors; ``enabled`` and ``log_local`` must be ``bool``; ``max_preserve``
and ``max_file_size`` must be non-negative integers.
"""

from __future__ import annotations

from typing import override

from infrafoundry.core.protocols import SpecializedValidator
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.opnsense.validators.context import OPNsenseValidationContext

from ..services.syslog_settings import BOOL_FIELDS, FIELD_MAP


class SyslogSettingsValidator(SpecializedValidator[OPNsenseValidationContext]):
    """Validates ``syslog.settings`` singleton resources."""

    def __init__(self, report: ValidationReport) -> None:
        """Initialize validator.

        Args:
            report: ValidationReport to add results to.
        """
        self.report = report

    @override
    def validate(self, context: OPNsenseValidationContext) -> None:
        """Validate ``syslog.settings`` resources.

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
        check = f"syslog_settings_{resource.name}"
        config = resource.config
        for key in sorted(set(config) - set(FIELD_MAP)):
            self._error(f"{check}_{key}", f"syslog.settings has unknown key '{key}'")
        for key in FIELD_MAP:
            if key not in config:
                continue
            value = config[key]
            name = f"{check}_{key}"
            if key in BOOL_FIELDS:
                if not isinstance(value, bool):
                    self._error(
                        name,
                        f"syslog.settings {key} must be a boolean, got {type(value).__name__}",
                    )
            elif isinstance(value, bool) or not isinstance(value, int) or value < 0:
                self._error(name, f"syslog.settings {key} must be a non-negative integer")
