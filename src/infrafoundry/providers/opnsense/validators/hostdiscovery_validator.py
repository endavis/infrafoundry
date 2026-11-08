"""Host-discovery validator for OPNsense (#792).

Pure-check, never-mutate validator for the ``hostdiscovery`` singleton. Unknown
keys are errors; ``enabled``/``promisc``/``verbose`` must be ``bool``,
``skip_nets`` a list of CIDRs, ``interface`` a list of interface keys that
resolve to a managed ``interfaces.assignments`` entry or a live interface, and
the expire intervals non-negative integers.
"""

from __future__ import annotations

import ipaddress
from typing import Any, override

from infrafoundry.core.protocols import SpecializedValidator
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.opnsense.validators.context import OPNsenseValidationContext

from ..services.hostdiscovery import BOOL_FIELDS, FIELD_MAP, INT_FIELDS, LIST_FIELDS


class HostDiscoveryValidator(SpecializedValidator[OPNsenseValidationContext]):
    """Validates ``hostdiscovery`` singleton resources."""

    def __init__(self, report: ValidationReport) -> None:
        """Initialize validator.

        Args:
            report: ValidationReport to add results to.
        """
        self.report = report

    @override
    def validate(self, context: OPNsenseValidationContext) -> None:
        """Validate ``hostdiscovery`` resources.

        Args:
            context: Validation context carrying the resources and lookups this validator checks.
        """
        for resource in context.resources:
            self._validate_one(
                resource,
                interface_assignment_names=context.interface_assignment_names,
                existing_interfaces=context.existing_interfaces,
            )

    def _error(self, check: str, message: str) -> None:
        self.report.add_check(
            check_name=check, passed=False, message=message, level=ValidationLevel.ERROR
        )

    def _validate_one(
        self,
        resource: ResourceConfig,
        *,
        interface_assignment_names: set[str],
        existing_interfaces: dict[str, Any],
    ) -> None:
        check = f"hostdiscovery_{resource.name}"
        config = resource.config
        for key in sorted(set(config) - set(FIELD_MAP)):
            self._error(f"{check}_{key}", f"hostdiscovery has unknown key '{key}'")
        for key in FIELD_MAP:
            if key not in config:
                continue
            value = config[key]
            name = f"{check}_{key}"
            if key in BOOL_FIELDS:
                if not isinstance(value, bool):
                    self._error(
                        name, f"hostdiscovery {key} must be a boolean, got {type(value).__name__}"
                    )
            elif key in LIST_FIELDS:
                self._validate_list(
                    key,
                    value,
                    name,
                    interface_assignment_names=interface_assignment_names,
                    existing_interfaces=existing_interfaces,
                )
            elif key in INT_FIELDS and (
                isinstance(value, bool) or not isinstance(value, int) or value < 0
            ):
                self._error(name, f"hostdiscovery {key} must be a non-negative integer")

    def _validate_list(
        self,
        key: str,
        value: Any,
        name: str,
        *,
        interface_assignment_names: set[str],
        existing_interfaces: dict[str, Any],
    ) -> None:
        if not isinstance(value, list):
            self._error(name, f"hostdiscovery {key} must be a list, got {type(value).__name__}")
            return
        for index, entry in enumerate(value):
            entry_name = f"{name}_{index}"
            if not isinstance(entry, str) or not entry.strip():
                self._error(entry_name, f"hostdiscovery {key}[{index}] must be a non-empty string")
            elif "," in entry:
                self._error(entry_name, f"hostdiscovery {key}[{index}] must not contain a comma")
            elif key == "skip_nets":
                try:
                    ipaddress.ip_network(entry.strip(), strict=False)
                except ValueError:
                    self._error(
                        entry_name,
                        f"hostdiscovery skip_nets[{index}] {entry!r} is not a valid CIDR",
                    )
            elif entry in interface_assignment_names or entry in existing_interfaces:
                self.report.add_check(
                    check_name=entry_name,
                    passed=True,
                    message=f"Interface {entry!r} resolved for hostdiscovery",
                    level=ValidationLevel.INFO,
                )
            else:
                self._error(
                    entry_name,
                    f"hostdiscovery interface {entry!r} is unknown; expected a managed "
                    f"interfaces.assignments name or a live OPNsense interface",
                )
