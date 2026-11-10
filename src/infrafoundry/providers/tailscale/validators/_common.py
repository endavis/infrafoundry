"""Shared helpers for the Tailscale sub-validators."""

from __future__ import annotations

import re
from typing import Any

from infrafoundry.core.validation import ValidationLevel, ValidationReport

TAG_RE = re.compile(r"^tag:\S+$")
TF_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")


def fail(
    report: ValidationReport,
    check_name: str,
    message: str,
    level: ValidationLevel = ValidationLevel.ERROR,
) -> None:
    """Record a failed check."""
    report.add_check(check_name=check_name, passed=False, message=message, level=level)


def check_tags(
    report: ValidationReport,
    resource_name: str,
    tags: Any,
    acl_policy: dict[str, Any] | None,
) -> bool:
    """Validate a tag list and warn about tags missing from ``tagOwners``.

    Args:
        report: Report to add findings to.
        resource_name: Resource the tags belong to.
        tags: The value to check; expected to be a list of ``tag:...`` strings.
        acl_policy: Structured ACL policy, or None when none is declared.

    Returns:
        True when ``tags`` is a list whose entries all have the ``tag:`` form.
    """
    check = f"tailscale_tags_{resource_name}"
    if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
        fail(report, check, f"'{resource_name}': tags must be a list of strings")
        return False
    bad = [t for t in tags if not TAG_RE.match(t)]
    if bad:
        fail(report, check, f"'{resource_name}': tags must look like 'tag:name', got {bad}")
        return False
    if acl_policy is not None:
        owners = acl_policy.get("tagOwners")
        known = set(owners) if isinstance(owners, dict) else set()
        missing = [t for t in tags if t not in known]
        if missing:
            fail(
                report,
                f"tailscale_tag_owners_{resource_name}",
                f"'{resource_name}': tags {missing} are not in the acl policy's tagOwners",
                ValidationLevel.WARNING,
            )
    return True
