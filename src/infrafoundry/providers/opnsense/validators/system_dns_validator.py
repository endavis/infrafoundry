"""System DNS validator for OPNsense (#806).

Pure-check validator for the ``system.dns`` singleton.
"""

from __future__ import annotations

import ipaddress
from typing import Any

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport


class SystemDnsValidator:
    """Validates ``system.dns`` singleton resources."""

    def __init__(self, report: ValidationReport) -> None:
        """Initialize validator.

        Args:
            report: ValidationReport to add results to.
        """
        self.report = report

    def validate(self, resources: list[ResourceConfig]) -> None:
        """Validate ``system.dns`` resources."""
        for resource in resources:
            self._validate_one(resource)

    def _validate_one(self, resource: ResourceConfig) -> None:
        check = f"system_dns_{resource.name}"
        config = resource.config

        # dns_servers — must be a list of valid IPs
        dns_servers = config.get("dns_servers")
        if dns_servers is not None:
            if not isinstance(dns_servers, list):
                self.report.add_check(
                    check_name=f"{check}_dns_servers",
                    passed=False,
                    message=(
                        f"system.dns '{resource.name}' dns_servers must be a list, "
                        f"got {type(dns_servers).__name__}"
                    ),
                    level=ValidationLevel.ERROR,
                )
            else:
                for entry in dns_servers:
                    self._check_ip(resource, check, "dns_servers", entry)

        # dns_allow_override — bool sentinel ("0"/"1") or bool
        override = config.get("dns_allow_override")
        if override is not None and not _is_bool_or_sentinel(override):
            self.report.add_check(
                check_name=f"{check}_dns_allow_override",
                passed=False,
                message=(
                    f"system.dns '{resource.name}' dns_allow_override must be "
                    f"a bool or '0'/'1' string, got {override!r}"
                ),
                level=ValidationLevel.ERROR,
            )

        # dns_allow_override_exclude — list of strings
        exclude = config.get("dns_allow_override_exclude")
        if exclude is not None and not isinstance(exclude, list):
            self.report.add_check(
                check_name=f"{check}_dns_allow_override_exclude",
                passed=False,
                message=(
                    f"system.dns '{resource.name}' dns_allow_override_exclude must "
                    f"be a list, got {type(exclude).__name__}"
                ),
                level=ValidationLevel.ERROR,
            )

        # dns_gateways — dict of {1..8: gateway_name}
        gateways = config.get("dns_gateways")
        if gateways is not None and not isinstance(gateways, dict | list):
            self.report.add_check(
                check_name=f"{check}_dns_gateways",
                passed=False,
                message=(
                    f"system.dns '{resource.name}' dns_gateways must be a dict or "
                    f"list, got {type(gateways).__name__}"
                ),
                level=ValidationLevel.ERROR,
            )

    def _check_ip(
        self,
        resource: ResourceConfig,
        check: str,
        field_name: str,
        value: Any,
    ) -> None:
        """Validate that *value* is a parseable IP address (v4 or v6)."""
        if not isinstance(value, str) or not value:
            self.report.add_check(
                check_name=f"{check}_{field_name}",
                passed=False,
                message=(
                    f"system.dns '{resource.name}' {field_name} entry must be a "
                    f"non-empty string, got {value!r}"
                ),
                level=ValidationLevel.ERROR,
            )
            return
        try:
            ipaddress.ip_address(value)
        except ValueError as exc:
            self.report.add_check(
                check_name=f"{check}_{field_name}",
                passed=False,
                message=(
                    f"system.dns '{resource.name}' {field_name} entry {value!r} is "
                    f"not a valid IP address: {exc}"
                ),
                level=ValidationLevel.ERROR,
            )


def _is_bool_or_sentinel(value: Any) -> bool:
    """Accept Python booleans and OPNsense's ``"0"``/``"1"`` string sentinels."""
    if isinstance(value, bool):
        return True
    if isinstance(value, str):
        return value in ("0", "1", "")
    return False
