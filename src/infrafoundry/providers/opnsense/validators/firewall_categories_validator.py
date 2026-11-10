"""Firewall category validator for OPNsense (#1286).

Plan-time checks for ``firewall.categories`` (no live-box access).

- Unknown keys are ERRORs; the box-assigned ``uuid`` carries a hint.
- ``name`` must be a non-empty string, and not ``infrafoundry`` (the provider's marker).
- ``auto`` and ``lock`` must be booleans.
- ``color`` must be a string: empty, or ``#rrggbb`` / ``rrggbb``.
- Duplicate effective names within the type.
"""

from __future__ import annotations

import re
from typing import Any, override

from infrafoundry.core.protocols import SpecializedValidator
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.opnsense.services import firewall_categories as svc
from infrafoundry.providers.opnsense.services._category_marker import INFRAFOUNDRY_CATEGORY_NAME
from infrafoundry.providers.opnsense.validators.context import OPNsenseValidationContext

_COLOR = re.compile(r"^#?[0-9A-Fa-f]{6}$")


class FirewallCategoryValidator(SpecializedValidator[OPNsenseValidationContext]):
    """Validates ``firewall.categories`` resources at plan time."""

    def __init__(self, report: ValidationReport) -> None:
        """Initialize the validator.

        Args:
            report: ``ValidationReport`` to add results to.
        """
        self.report = report

    @override
    def validate(self, context: OPNsenseValidationContext) -> None:
        """Validate all firewall category resources.

        Args:
            context: Context whose ``resources`` hold the categories.
        """
        resources = [r for r in context.resources if r.type == "firewall.categories"]
        if not resources:
            return
        self._check_duplicates(resources)
        for resource in resources:
            self._validate_one(resource)

    def _error(self, check: str, message: str) -> None:
        self.report.add_check(
            check_name=check, passed=False, message=message, level=ValidationLevel.ERROR
        )

    def _check_duplicates(self, resources: list[ResourceConfig]) -> None:
        seen: set[str] = set()
        dupes: set[str] = set()
        for r in resources:
            wire = svc.category_name_of(r.name, r.config)
            (dupes if wire in seen else seen).add(wire)
        if dupes:
            self._error(
                "firewall_categories_unique_names",
                f"firewall.categories resources share names: {sorted(dupes)!r}. "
                f"The name is the identity on the box; make each unique.",
            )

    def _validate_one(self, resource: ResourceConfig) -> None:
        name, config = resource.name, resource.config
        label = f"firewall category '{name}'"
        prefix = f"firewall_category_{name}"
        self._check_keys(prefix, label, config)
        wire = config.get("name")
        if wire is not None and (not isinstance(wire, str) or not wire.strip()):
            self._error(f"{prefix}_name", f"{label} name must be a non-empty string")
        elif svc.category_name_of(name, config) == INFRAFOUNDRY_CATEGORY_NAME:
            self._error(
                f"{prefix}_reserved_name",
                f"{label} uses the reserved name '{INFRAFOUNDRY_CATEGORY_NAME}' "
                f"(the provider's own marker category)",
            )
        for flag in ("auto", "lock"):
            if flag in config and not isinstance(config[flag], bool):
                self._error(f"{prefix}_{flag}", f"{label} {flag} must be a boolean")
        color = config.get("color")
        if color is not None:
            if not isinstance(color, str):
                self._error(f"{prefix}_color", f"{label} color must be a string")
            elif color and not _COLOR.match(color):
                self._error(
                    f"{prefix}_color",
                    f"{label} color must be empty or a hex color like '#336699'",
                )

    def _check_keys(self, prefix: str, label: str, config: dict[str, Any]) -> None:
        for key in sorted(set(config) - svc.ALLOWED_KEYS):
            if key in svc.BOX_ASSIGNED_KEYS:
                message = f"{label} must not set '{key}': the box assigns it"
            else:
                message = f"{label} has unknown key '{key}'; allowed: {sorted(svc.ALLOWED_KEYS)}"
            self._error(f"{prefix}_unknown_key_{key}", message)
