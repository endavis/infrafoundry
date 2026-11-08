"""Unbound advanced-settings validator for OPNsense (#1254).

Pure-check, never-mutate validator for the ``unbound.advanced`` singleton.
Unknown keys are errors; each present field must be a list of non-empty strings
without commas or whitespace (a comma would split an entry on the wire), and
``private_addresses`` entries must be valid CIDR networks.
"""

from __future__ import annotations

import ipaddress
from typing import override

from infrafoundry.core.protocols import SpecializedValidator
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.opnsense.validators.context import OPNsenseValidationContext

_FIELDS: tuple[str, ...] = ("private_domains", "insecure_domains", "private_addresses")


class UnboundAdvancedValidator(SpecializedValidator[OPNsenseValidationContext]):
    """Validates ``unbound.advanced`` singleton resources."""

    def __init__(self, report: ValidationReport) -> None:
        """Initialize validator.

        Args:
            report: ValidationReport to add results to.
        """
        self.report = report

    @override
    def validate(self, context: OPNsenseValidationContext) -> None:
        """Validate ``unbound.advanced`` resources.

        Args:
            context: Validation context carrying the resources and lookups this validator checks.
        """
        resources = context.resources
        for resource in resources:
            self._validate_one(resource)

    def _error(self, check: str, message: str) -> None:
        self.report.add_check(
            check_name=check, passed=False, message=message, level=ValidationLevel.ERROR
        )

    def _validate_one(self, resource: ResourceConfig) -> None:
        check = f"unbound_advanced_{resource.name}"
        config = resource.config
        for key in sorted(set(config) - set(_FIELDS)):
            self._error(f"{check}_{key}", f"unbound.advanced has unknown key '{key}'")
        for key in _FIELDS:
            if key not in config:
                continue
            value = config[key]
            if not isinstance(value, list):
                self._error(
                    f"{check}_{key}",
                    f"unbound.advanced {key} must be a list, got {type(value).__name__}",
                )
                continue
            for index, entry in enumerate(value):
                self._validate_entry(check, key, index, entry)

    def _validate_entry(self, check: str, key: str, index: int, entry: object) -> None:
        name = f"{check}_{key}_{index}"
        if not isinstance(entry, str) or not entry:
            self._error(name, f"unbound.advanced {key}[{index}] must be a non-empty string")
            return
        if "," in entry or any(ch.isspace() for ch in entry):
            self._error(
                name, f"unbound.advanced {key}[{index}] must not contain commas or whitespace"
            )
            return
        if key == "private_addresses":
            try:
                ipaddress.ip_network(entry, strict=False)
            except ValueError:
                self._error(
                    name, f"unbound.advanced {key}[{index}] '{entry}' is not a valid CIDR network"
                )
