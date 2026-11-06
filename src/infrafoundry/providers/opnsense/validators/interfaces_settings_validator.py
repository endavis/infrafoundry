"""Interface-settings validator for OPNsense (#1092).

Pure-check, never-mutate validator for the ``interfaces.settings`` singleton.
Unknown keys are errors; boolean fields must be ``bool``,
``vlan_hardware_filtering`` one of ``enable``/``default``/``disable``,
``dhcp6_duid`` a string and ``dhcp6_ra_timeout`` a non-negative integer.
"""

from __future__ import annotations

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport

from ..services.interfaces_settings import BOOL_FIELDS, FIELD_MAP, VLAN_FILTER_VALUES


class InterfacesSettingsValidator:
    """Validates ``interfaces.settings`` singleton resources."""

    def __init__(self, report: ValidationReport) -> None:
        """Initialize validator.

        Args:
            report: ValidationReport to add results to.
        """
        self.report = report

    def validate(self, resources: list[ResourceConfig]) -> None:
        """Validate ``interfaces.settings`` resources."""
        for resource in resources:
            self._validate_one(resource)

    def _error(self, check: str, message: str) -> None:
        self.report.add_check(
            check_name=check, passed=False, message=message, level=ValidationLevel.ERROR
        )

    def _validate_one(self, resource: ResourceConfig) -> None:
        check = f"interfaces_settings_{resource.name}"
        config = resource.config
        for key in sorted(set(config) - set(FIELD_MAP)):
            self._error(f"{check}_{key}", f"interfaces.settings has unknown key '{key}'")
        for key in FIELD_MAP:
            if key not in config:
                continue
            value = config[key]
            name = f"{check}_{key}"
            if key in BOOL_FIELDS:
                if not isinstance(value, bool):
                    self._error(
                        name,
                        f"interfaces.settings {key} must be a boolean, got {type(value).__name__}",
                    )
            elif key == "vlan_hardware_filtering":
                if not isinstance(value, str) or value not in VLAN_FILTER_VALUES:
                    self._error(
                        name,
                        "interfaces.settings vlan_hardware_filtering must be one of: "
                        + ", ".join(VLAN_FILTER_VALUES),
                    )
            elif key == "dhcp6_duid":
                if not isinstance(value, str):
                    self._error(name, "interfaces.settings dhcp6_duid must be a string")
            elif isinstance(value, bool) or not isinstance(value, int) or value < 0:
                self._error(name, f"interfaces.settings {key} must be a non-negative integer")
