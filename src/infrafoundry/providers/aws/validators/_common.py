"""Shared helpers for the AWS sub-validators."""

from __future__ import annotations

import ipaddress
import re
from typing import Any

from infrafoundry.core.validation import ValidationLevel, ValidationReport

RULE_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def fail(
    report: ValidationReport,
    check_name: str,
    message: str,
    level: ValidationLevel = ValidationLevel.ERROR,
) -> None:
    """Record a failed check."""
    report.add_check(check_name=check_name, passed=False, message=message, level=level)


def parse_cidr(value: Any, version: int) -> str | None:
    """Check that ``value`` is a network address of the given IP family.

    Args:
        value: The configured CIDR.
        version: Required IP version, 4 or 6.

    Returns:
        An error message, or None when ``value`` is a valid CIDR with no host
        bits set and the right family.
    """
    if not isinstance(value, str):
        return f"must be a string, got {type(value).__name__}"
    try:
        network = ipaddress.ip_network(value, strict=True)
    except ValueError as exc:
        return f"'{value}' is not a valid CIDR ({exc})"
    if network.version != version:
        return f"'{value}' is an IPv{network.version} CIDR; expected IPv{version}"
    return None
