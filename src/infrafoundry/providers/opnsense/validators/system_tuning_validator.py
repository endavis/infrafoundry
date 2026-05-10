"""System tuning (sysctl) validator for OPNsense (#806).

Pure-check, never-mutate validator for the ``system.tuning`` singleton
resource type. Type-checks each sysctl item entry: ``tunable``,
``value``, and ``descr`` must be scalars (string-castable).

The validator does NOT mutate ``resource.config`` — strict invariant for
all OPNsense validators. No secrets, no cross-references.
"""

from __future__ import annotations

from typing import Any

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport

# Accepted scalar types for a sysctl item field (str / int / bool /
# float). The wire form is ultimately a string but YAML may yield other
# scalars and the service layer string-casts at extract time.
_SCALAR_TYPES: tuple[type, ...] = (str, int, bool, float)


class SystemTuningValidator:
    """Validates ``system.tuning`` singleton resources."""

    def __init__(self, report: ValidationReport) -> None:
        """Initialize validator.

        Args:
            report: ValidationReport to add results to.
        """
        self.report = report

    def validate(self, resources: list[ResourceConfig]) -> None:
        """Validate ``system.tuning`` resources."""
        for resource in resources:
            self._validate_one(resource)

    def _validate_one(self, resource: ResourceConfig) -> None:
        check = f"system_tuning_{resource.name}"
        config = resource.config

        items = config.get("items")
        if items is None:
            return

        if not isinstance(items, list):
            self.report.add_check(
                check_name=f"{check}_items",
                passed=False,
                message=(
                    f"system.tuning '{resource.name}' items must be a list, "
                    f"got {type(items).__name__}"
                ),
                level=ValidationLevel.ERROR,
            )
            return

        for index, entry in enumerate(items):
            self._validate_item(resource, check, index, entry)

    def _validate_item(
        self,
        resource: ResourceConfig,
        check: str,
        index: int,
        entry: Any,
    ) -> None:
        if not isinstance(entry, dict):
            self.report.add_check(
                check_name=f"{check}_items_{index}",
                passed=False,
                message=(
                    f"system.tuning '{resource.name}' items[{index}] must be a dict, "
                    f"got {type(entry).__name__}"
                ),
                level=ValidationLevel.ERROR,
            )
            return

        # ``tunable`` is required (the sysctl name); ``value`` is required
        # (the value to set). ``descr`` is optional.
        tunable = entry.get("tunable")
        if not isinstance(tunable, str) or not tunable:
            self.report.add_check(
                check_name=f"{check}_items_{index}_tunable",
                passed=False,
                message=(
                    f"system.tuning '{resource.name}' items[{index}] tunable must be "
                    f"a non-empty string, got {tunable!r}"
                ),
                level=ValidationLevel.ERROR,
            )

        value = entry.get("value")
        if value is None or not isinstance(value, _SCALAR_TYPES):
            self.report.add_check(
                check_name=f"{check}_items_{index}_value",
                passed=False,
                message=(
                    f"system.tuning '{resource.name}' items[{index}] value must be a "
                    f"scalar (str/int/bool/float), got {type(value).__name__}"
                ),
                level=ValidationLevel.ERROR,
            )

        descr = entry.get("descr")
        if descr is not None and not isinstance(descr, str):
            self.report.add_check(
                check_name=f"{check}_items_{index}_descr",
                passed=False,
                message=(
                    f"system.tuning '{resource.name}' items[{index}] descr must be a "
                    f"string, got {type(descr).__name__}"
                ),
                level=ValidationLevel.ERROR,
            )
