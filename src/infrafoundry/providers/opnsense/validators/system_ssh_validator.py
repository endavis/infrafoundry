"""System SSH validator for OPNsense (#806).

Pure-check validator for the ``system.ssh`` singleton.
"""

from __future__ import annotations

from typing import Any

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport


class SystemSshValidator:
    """Validates ``system.ssh`` singleton resources."""

    def __init__(self, report: ValidationReport) -> None:
        """Initialize validator.

        Args:
            report: ValidationReport to add results to.
        """
        self.report = report

    def validate(self, resources: list[ResourceConfig]) -> None:
        """Validate ``system.ssh`` resources."""
        for resource in resources:
            self._validate_one(resource)

    def _validate_one(self, resource: ResourceConfig) -> None:
        check = f"system_ssh_{resource.name}"
        config = resource.config

        # Simple string fields
        for field in (
            "enabled",
            "group",
            "noauto",
            "kex",
            "ciphers",
            "macs",
            "keys",
            "keysig",
            "rekeylimit",
        ):
            value = config.get(field)
            if value is not None and not isinstance(value, str | bool | int):
                self.report.add_check(
                    check_name=f"{check}_{field}",
                    passed=False,
                    message=(
                        f"system.ssh '{resource.name}' {field} must be a string/bool/int, "
                        f"got {type(value).__name__}"
                    ),
                    level=ValidationLevel.ERROR,
                )

        # interfaces — list of strings or comma-joined string
        interfaces = config.get("interfaces")
        if interfaces is not None and not isinstance(interfaces, list | str):
            self.report.add_check(
                check_name=f"{check}_interfaces",
                passed=False,
                message=(
                    f"system.ssh '{resource.name}' interfaces must be a list or "
                    f"comma-joined string, got {type(interfaces).__name__}"
                ),
                level=ValidationLevel.ERROR,
            )
        elif isinstance(interfaces, list):
            for entry in interfaces:
                if not isinstance(entry, str) or not entry:
                    self.report.add_check(
                        check_name=f"{check}_interfaces",
                        passed=False,
                        message=(
                            f"system.ssh '{resource.name}' interfaces entry must be a "
                            f"non-empty string, got {entry!r}"
                        ),
                        level=ValidationLevel.ERROR,
                    )

    def _is_bool_or_sentinel(self, value: Any) -> bool:
        if isinstance(value, bool):
            return True
        if isinstance(value, str):
            return value in ("0", "1", "")
        return False
