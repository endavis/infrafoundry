"""Tailscale subnets validator for OPNsense (#787).

Plan-time validation for the ``tailscale.subnets`` dotted resource type —
a list-shape collection. Each entry carries a ``cidr`` field that must be
a valid IPv4 or IPv6 CIDR. Duplicate CIDRs within the same resource list
are reported as errors.

The ``name`` field is the slug-form identity key synthesised by
``migrate()``; it is never validated beyond being non-empty (it is
auto-generated in the migrate path and operator-chosen in hand-authored
YAML). The validator only checks ``cidr``.
"""

from __future__ import annotations

import ipaddress

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport


class TailscaleSubnetsValidator:
    """Validates ``tailscale.subnets`` list entries.

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
        """Validate a list of tailscale.subnets entries.

        Args:
            resources: ``tailscale.subnets`` ``ResourceConfig`` entries.
                Empty list is valid (no subnets configured).
        """
        if not resources:
            return

        seen_cidrs: set[str] = set()
        for resource in resources:
            cidr_raw = resource.config.get("cidr")

            # cidr must be present
            if not cidr_raw:
                self.report.add_check(
                    check_name=f"tailscale.subnets[{resource.name}].cidr",
                    passed=False,
                    message=f"cidr is required for tailscale.subnets entry {resource.name!r}",
                    level=ValidationLevel.ERROR,
                )
                continue

            cidr = str(cidr_raw).strip()

            # Must parse as valid CIDR
            if not _is_valid_cidr(cidr):
                self.report.add_check(
                    check_name=f"tailscale.subnets[{resource.name}].cidr",
                    passed=False,
                    message=(
                        f"cidr {cidr!r} is not a valid IPv4 or IPv6 CIDR prefix "
                        f"(e.g. 192.168.1.0/24 or fd00::/48)"
                    ),
                    level=ValidationLevel.ERROR,
                )
                continue

            # Duplicate CIDR within this resource list
            if cidr in seen_cidrs:
                self.report.add_check(
                    check_name=f"tailscale.subnets[{resource.name}].cidr",
                    passed=False,
                    message=f"Duplicate tailscale subnet CIDR {cidr!r}",
                    level=ValidationLevel.ERROR,
                )
            else:
                seen_cidrs.add(cidr)


def _is_valid_cidr(value: str) -> bool:
    """Return True if *value* is a valid IPv4 or IPv6 network prefix."""
    try:
        ipaddress.ip_network(value, strict=False)
        return True
    except ValueError:
        return False
