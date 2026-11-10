"""Name and singleton validation for Tailscale resources."""

from __future__ import annotations

from typing import override

from infrafoundry.core.protocols import SpecializedValidator
from infrafoundry.core.validation import ValidationReport

from ._common import TF_NAME_RE, fail
from .context import TailscaleConfigContext

#: Tailnet-wide types: Tailscale holds one of each per tailnet.
SINGLETON_TYPES = ("acl", "dns_nameservers", "dns_preferences", "dns_search_paths")


class NamingValidator(SpecializedValidator[TailscaleConfigContext]):
    """Checks resource names are unique and Terraform-safe, and singletons occur once."""

    def __init__(self, report: ValidationReport) -> None:
        """Initialize the validator.

        Args:
            report: ValidationReport to add results to
        """
        self.report = report

    @override
    def validate(self, context: TailscaleConfigContext) -> None:
        """Check names across all resources.

        Args:
            context: Context whose resources are checked.
        """
        seen: dict[str, str] = {}
        for resource in context.resources:
            if not TF_NAME_RE.match(resource.name):
                fail(
                    self.report,
                    f"tailscale_name_{resource.name}",
                    f"Resource name '{resource.name}' is not a valid Terraform name "
                    "(letters, digits, '_' and '-'; must not start with a digit)",
                )
            if resource.name in seen:
                fail(
                    self.report,
                    f"tailscale_duplicate_name_{resource.name}",
                    f"Resource name '{resource.name}' is used by both a '{seen[resource.name]}' "
                    f"and a '{resource.type}' resource; names must be unique across types",
                )
            seen[resource.name] = resource.type
        for rtype in SINGLETON_TYPES:
            names = [r.name for r in context.resources if r.type == rtype]
            if len(names) > 1:
                fail(
                    self.report,
                    f"tailscale_singleton_{rtype}",
                    f"At most one '{rtype}' resource is allowed per environment, "
                    f"found {len(names)}: {sorted(names)}",
                )
