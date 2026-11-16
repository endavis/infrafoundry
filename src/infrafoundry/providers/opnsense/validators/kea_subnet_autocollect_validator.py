"""Kea DHCPv4 subnet auto-collect validator for OPNsense (#1432).

Plan-time check (offline: YAML only) for ``kea.dhcp4.subnets`` resources. A subnet with
``auto_collect: true`` that also sets explicit routers, DNS servers or NTP servers gets a
WARNING: saving the Kea DHCPv4 settings (``kea/dhcpv4/set``) re-runs auto-collect on
OPNsense, which overwrites those values. The fix is ``auto_collect: false``.

It is a WARNING, never an ERROR, because the combination is accepted by OPNsense and the
explicit values can be correct until the next save.

The list of keys auto-collect fills is the issue's assumption (routers, DNS, NTP); it is
not verified against OPNsense source.
"""

from __future__ import annotations

from typing import override

from infrafoundry.core.protocols import SpecializedValidator
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.opnsense.validators.context import OPNsenseValidationContext

_SUBNETS = "kea.dhcp4.subnets"
# Assumption from #1432, not verified against OPNsense source: YAML keys that auto-collect
# overwrites. ``dns_servers`` is sent on the wire as ``domain_name_servers``.
_AUTO_COLLECTED_KEYS: tuple[str, ...] = ("routers", "dns_servers", "ntp_servers")


class KeaSubnetAutoCollectValidator(SpecializedValidator[OPNsenseValidationContext]):
    """Warns when a Kea DHCPv4 subnet combines ``auto_collect`` with explicit options."""

    def __init__(self, report: ValidationReport) -> None:
        """Initialize the validator.

        Args:
            report: ``ValidationReport`` to add results to.
        """
        self.report = report

    @override
    def validate(self, context: OPNsenseValidationContext) -> None:
        """Warn for each subnet that sets ``auto_collect: true`` with explicit options.

        Args:
            context: Context whose ``resources`` hold the Kea DHCPv4 subnets.
        """
        for resource in context.resources:
            if resource.type != _SUBNETS:
                continue
            config = resource.config
            if config.get("auto_collect") is not True:
                continue
            conflicts = [key for key in _AUTO_COLLECTED_KEYS if config.get(key)]
            if not conflicts:
                continue
            cidr = config.get("subnet")
            where = f"kea subnet '{resource.name}'" + (f" ({cidr})" if cidr else "")
            self.report.add_check(
                check_name=f"kea_subnet_{resource.name}_auto_collect_option_data",
                passed=False,
                level=ValidationLevel.WARNING,
                message=(
                    f"{where} sets auto_collect: true and explicit {', '.join(conflicts)}; "
                    "OPNsense re-runs auto-collect when the Kea DHCPv4 settings are saved "
                    "and overwrites these values. Set auto_collect: false to keep them."
                ),
            )
