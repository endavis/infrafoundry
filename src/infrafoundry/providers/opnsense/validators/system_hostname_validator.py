"""System hostname validator for OPNsense (#806).

Pure-check, never-mutate validator for the ``system.hostname`` singleton
resource type. Surfaces shape errors (non-string fields, empty hostname,
bogus timezone) at plan time so operators get clean errors before any
API call.

The validator does NOT mutate ``resource.config`` — that's a strict
invariant for all OPNsense validators (see kea_reservation_validator.py,
static_route_validator.py for the established pattern).
"""

from __future__ import annotations

import re

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport

# RFC-952/1123 hostname (single label or FQDN-ish). Permissive — OPNsense
# accepts what BSD does; we only block obviously-bad values.
_HOSTNAME_RE = re.compile(r"^[a-zA-Z0-9]([a-zA-Z0-9\-\.]*[a-zA-Z0-9])?$")


class SystemHostnameValidator:
    """Validates ``system.hostname`` singleton resources."""

    def __init__(self, report: ValidationReport) -> None:
        """Initialize validator.

        Args:
            report: ValidationReport to add results to.
        """
        self.report = report

    def validate(self, resources: list[ResourceConfig]) -> None:
        """Validate ``system.hostname`` resources.

        Args:
            resources: ``system.hostname`` ``ResourceConfig`` entries
                (loader emits at most one — defensive plural here).
        """
        for resource in resources:
            self._validate_one(resource)

    def _validate_one(self, resource: ResourceConfig) -> None:
        check = f"system_hostname_{resource.name}"
        config = resource.config

        hostname = config.get("hostname")
        if hostname is not None:
            if not isinstance(hostname, str) or not hostname:
                self.report.add_check(
                    check_name=f"{check}_hostname",
                    passed=False,
                    message=(
                        f"system.hostname '{resource.name}' hostname must be a "
                        f"non-empty string, got {type(hostname).__name__}"
                    ),
                    level=ValidationLevel.ERROR,
                )
            elif not _HOSTNAME_RE.match(hostname):
                self.report.add_check(
                    check_name=f"{check}_hostname",
                    passed=False,
                    message=(
                        f"system.hostname '{resource.name}' hostname "
                        f"{hostname!r} contains invalid characters"
                    ),
                    level=ValidationLevel.ERROR,
                )

        for field in ("domain", "timezone", "language"):
            value = config.get(field)
            if value is not None and not isinstance(value, str):
                self.report.add_check(
                    check_name=f"{check}_{field}",
                    passed=False,
                    message=(
                        f"system.hostname '{resource.name}' {field} must be a string, "
                        f"got {type(value).__name__}"
                    ),
                    level=ValidationLevel.ERROR,
                )
