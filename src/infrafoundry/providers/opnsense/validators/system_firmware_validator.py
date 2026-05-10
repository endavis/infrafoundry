"""System firmware validator for OPNsense (#806).

Pure-check, never-mutate validator for the ``system.firmware`` singleton
resource type. The most operator-impactful validation is the plugin-list
shape check: members must look like ``os-*`` package names so a typo
doesn't silently install nothing on apply.

Plugin-name format mismatches are warning-level only (not error) so
operators can still install official-but-non-``os-`` packages out-of-band
without the validator blocking them.

The validator does NOT mutate ``resource.config`` — strict invariant for
all OPNsense validators.
"""

from __future__ import annotations

import re

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport

# OPNsense contrib plugins are conventionally named ``os-<slug>`` where
# ``<slug>`` is lowercase alphanumeric plus hyphens. We warn (don't error)
# on format mismatches so the operator can still pin a non-conforming
# name if needed.
_PLUGIN_NAME_RE = re.compile(r"^os-[a-z0-9][a-z0-9\-]*$")


class SystemFirmwareValidator:
    """Validates ``system.firmware`` singleton resources."""

    def __init__(self, report: ValidationReport) -> None:
        """Initialize validator.

        Args:
            report: ValidationReport to add results to.
        """
        self.report = report

    def validate(self, resources: list[ResourceConfig]) -> None:
        """Validate ``system.firmware`` resources."""
        for resource in resources:
            self._validate_one(resource)

    def _validate_one(self, resource: ResourceConfig) -> None:
        check = f"system_firmware_{resource.name}"
        config = resource.config

        # plugins — list of strings; members should match ``os-*`` (warning).
        plugins = config.get("plugins")
        if plugins is not None:
            if not isinstance(plugins, list):
                self.report.add_check(
                    check_name=f"{check}_plugins",
                    passed=False,
                    message=(
                        f"system.firmware '{resource.name}' plugins must be a list, "
                        f"got {type(plugins).__name__}"
                    ),
                    level=ValidationLevel.ERROR,
                )
            else:
                for entry in plugins:
                    if not isinstance(entry, str) or not entry:
                        self.report.add_check(
                            check_name=f"{check}_plugins_entry",
                            passed=False,
                            message=(
                                f"system.firmware '{resource.name}' plugins entry must "
                                f"be a non-empty string, got {entry!r}"
                            ),
                            level=ValidationLevel.ERROR,
                        )
                    elif not _PLUGIN_NAME_RE.match(entry):
                        # Warning-level: the operator may legitimately
                        # install non-``os-*`` packages.
                        self.report.add_check(
                            check_name=f"{check}_plugins_naming",
                            passed=False,
                            message=(
                                f"system.firmware '{resource.name}' plugin "
                                f"{entry!r} does not match the expected "
                                f"``os-<slug>`` naming convention"
                            ),
                            level=ValidationLevel.WARNING,
                        )

        # Plain string settings fields.
        for field in ("mirror", "flavour", "type", "subscription", "reboot"):
            value = config.get(field)
            if value is not None and not isinstance(value, str):
                self.report.add_check(
                    check_name=f"{check}_{field}",
                    passed=False,
                    message=(
                        f"system.firmware '{resource.name}' {field} must be a string, "
                        f"got {type(value).__name__}"
                    ),
                    level=ValidationLevel.ERROR,
                )
