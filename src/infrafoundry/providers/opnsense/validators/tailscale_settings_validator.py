"""Tailscale settings validator for OPNsense (#787).

Plan-time validation for the ``tailscale.settings`` dotted resource type —
a dict-shape singleton. The validator is pure-check; it never mutates
``resource.config``.

Field-shape checks:

- ``enable``: boolean-ish value accepted.
- ``login_timeout``: positive integer (seconds; default 10).
- ``listen_port``: integer 1-65535.
- ``accept_dns``: boolean-ish.
- ``advertise_exit_node``: boolean-ish.
- ``use_exit_node``: string (optional; empty = no exit node).
- ``accept_subnet_routes``: boolean-ish.
- ``enable_ssh``: boolean-ish.
- ``enable_snat``: boolean-ish (inverted to ``disableSNAT`` on wire).
"""

from __future__ import annotations

from typing import Any

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport

# Boolean-ish values accepted for bool fields.
_TRUTHY: frozenset[str] = frozenset({"1", "true", "yes", "on"})
_FALSY: frozenset[str] = frozenset({"0", "false", "no", "off", ""})
_BOOL_STRINGS: frozenset[str] = _TRUTHY | _FALSY

_BOOL_FIELDS: tuple[str, ...] = (
    "enable",
    "accept_dns",
    "advertise_exit_node",
    "accept_subnet_routes",
    "enable_ssh",
    "enable_snat",
)


class TailscaleSettingsValidator:
    """Validates the ``tailscale.settings`` singleton resource.

    Args:
        report: ``ValidationReport`` to add results to.
    """

    def __init__(self, report: ValidationReport) -> None:
        """Initialize the validator.

        Args:
            report: Validation report to populate.
        """
        self.report = report

    def validate(self, resources: list[ResourceConfig]) -> None:
        """Validate the tailscale.settings singleton.

        Args:
            resources: ``tailscale.settings`` ``ResourceConfig`` entries
                (zero or one). Zero resources is valid (feature not used).
        """
        if not resources:
            return
        for resource in resources:
            self._validate_one(resource)

    def _validate_one(self, resource: ResourceConfig) -> None:
        """Validate a single tailscale.settings resource."""
        config = resource.config

        # Boolean-ish fields
        for field in _BOOL_FIELDS:
            if field in config:
                self._check_bool_field(field, config[field], resource.name)

        # login_timeout: positive integer
        if "login_timeout" in config:
            self._check_positive_int("login_timeout", config["login_timeout"], resource.name)

        # listen_port: integer 1-65535
        if "listen_port" in config:
            self._check_port("listen_port", config["listen_port"], resource.name)

        # use_exit_node: optional string
        if "use_exit_node" in config:
            val = config["use_exit_node"]
            if val is not None and not isinstance(val, str):
                self.report.add_check(
                    check_name=f"tailscale.settings[{resource.name}].use_exit_node",
                    passed=False,
                    message=f"use_exit_node must be a string, got {type(val).__name__}",
                    level=ValidationLevel.ERROR,
                )

    def _check_bool_field(self, field: str, value: Any, resource_name: str) -> None:
        """Validate a bool-ish field."""
        if isinstance(value, bool):
            return
        if isinstance(value, int) and value in (0, 1):
            return
        if isinstance(value, str) and value.lower() in _BOOL_STRINGS:
            return
        self.report.add_check(
            check_name=f"tailscale.settings[{resource_name}].{field}",
            passed=False,
            message=(f"{field} must be a boolean-ish value (true/false/0/1/yes/no), got {value!r}"),
            level=ValidationLevel.ERROR,
        )

    def _check_positive_int(self, field: str, value: Any, resource_name: str) -> None:
        """Validate a positive integer field."""
        try:
            int_val = int(str(value).strip())
            if int_val <= 0:
                raise ValueError("non-positive")
        except (ValueError, TypeError):
            self.report.add_check(
                check_name=f"tailscale.settings[{resource_name}].{field}",
                passed=False,
                message=f"{field} must be a positive integer, got {value!r}",
                level=ValidationLevel.ERROR,
            )

    def _check_port(self, field: str, value: Any, resource_name: str) -> None:
        """Validate a TCP/UDP port field (1-65535)."""
        try:
            int_val = int(str(value).strip())
            if not (1 <= int_val <= 65535):
                raise ValueError("out of range")
        except (ValueError, TypeError):
            self.report.add_check(
                check_name=f"tailscale.settings[{resource_name}].{field}",
                passed=False,
                message=f"{field} must be an integer 1-65535, got {value!r}",
                level=ValidationLevel.ERROR,
            )
