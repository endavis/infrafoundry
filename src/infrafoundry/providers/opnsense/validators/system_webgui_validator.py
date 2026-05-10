"""System WebGUI validator for OPNsense (#806).

Pure-check, never-mutate validator for the ``system.webgui`` singleton
resource type. Surfaces shape errors (non-string fields, bogus protocol,
non-numeric port) at plan time so operators get clean errors before any
API call.

The validator does NOT mutate ``resource.config`` — strict invariant for
all OPNsense validators.

Cross-reference resolution for ``ssl_certificate_ref`` is deferred until
the trust-system surface ships in #807; today the validator type-checks
the string but does not resolve it against any sibling cert resource.
"""

from __future__ import annotations

from typing import Any

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport

# Accepted values for the WebGUI listener protocol (XML sentinel).
_PROTOCOLS: frozenset[str] = frozenset({"http", "https"})


class SystemWebguiValidator:
    """Validates ``system.webgui`` singleton resources."""

    def __init__(self, report: ValidationReport) -> None:
        """Initialize validator.

        Args:
            report: ValidationReport to add results to.
        """
        self.report = report

    def validate(self, resources: list[ResourceConfig]) -> None:
        """Validate ``system.webgui`` resources."""
        for resource in resources:
            self._validate_one(resource)

    def _validate_one(self, resource: ResourceConfig) -> None:
        check = f"system_webgui_{resource.name}"
        config = resource.config

        # protocol — must be "http" or "https" (case-sensitive match for
        # OPNsense wire form); permit empty/None for partial config.
        protocol = config.get("protocol")
        if protocol is not None:
            if not isinstance(protocol, str):
                self.report.add_check(
                    check_name=f"{check}_protocol",
                    passed=False,
                    message=(
                        f"system.webgui '{resource.name}' protocol must be a string, "
                        f"got {type(protocol).__name__}"
                    ),
                    level=ValidationLevel.ERROR,
                )
            elif protocol and protocol not in _PROTOCOLS:
                self.report.add_check(
                    check_name=f"{check}_protocol",
                    passed=False,
                    message=(
                        f"system.webgui '{resource.name}' protocol must be one of "
                        f"{sorted(_PROTOCOLS)!r}, got {protocol!r}"
                    ),
                    level=ValidationLevel.ERROR,
                )

        # port — int or numeric string in 1..65535; empty string / None ok.
        port = config.get("port")
        if port not in (None, "") and not _is_valid_port(port):
            self.report.add_check(
                check_name=f"{check}_port",
                passed=False,
                message=(
                    f"system.webgui '{resource.name}' port must be an integer "
                    f"1..65535, got {port!r}"
                ),
                level=ValidationLevel.ERROR,
            )

        # Plain string fields.
        for field in ("ssl_certificate_ref", "ssl_certref", "ssl_ciphers", "compression"):
            value = config.get(field)
            if value is not None and not isinstance(value, str):
                self.report.add_check(
                    check_name=f"{check}_{field}",
                    passed=False,
                    message=(
                        f"system.webgui '{resource.name}' {field} must be a string, "
                        f"got {type(value).__name__}"
                    ),
                    level=ValidationLevel.ERROR,
                )

        # interfaces — list of strings or comma-joined string.
        interfaces = config.get("interfaces")
        if interfaces is not None and not isinstance(interfaces, list | str):
            self.report.add_check(
                check_name=f"{check}_interfaces",
                passed=False,
                message=(
                    f"system.webgui '{resource.name}' interfaces must be a list or "
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
                            f"system.webgui '{resource.name}' interfaces entry must be a "
                            f"non-empty string, got {entry!r}"
                        ),
                        level=ValidationLevel.ERROR,
                    )

        # TODO #807: when trust-system ships, resolve ``ssl_certificate_ref``
        # against the live cert collection and surface ReferenceValidationError
        # at plan time on miss. For now we only type-check the field.


def _is_valid_port(value: Any) -> bool:
    """Accept int OR numeric string in the 1..65535 range."""
    if isinstance(value, bool):
        # bool is a subclass of int; reject explicitly so True/False aren't
        # silently treated as port 1/0.
        return False
    if isinstance(value, int):
        return 1 <= value <= 65535
    if isinstance(value, str):
        try:
            port_int = int(value)
        except ValueError:
            return False
        return 1 <= port_int <= 65535
    return False
