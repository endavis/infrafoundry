"""DNS resource validation."""

from __future__ import annotations

import ipaddress
from typing import override

from infrafoundry.core.protocols import SpecializedValidator
from infrafoundry.core.validation import ValidationReport

from ._common import fail
from .context import TailscaleConfigContext


class DnsValidator(SpecializedValidator[TailscaleConfigContext]):
    """Checks ``dns_nameservers``, ``dns_preferences`` and ``dns_search_paths``."""

    def __init__(self, report: ValidationReport) -> None:
        """Initialize the validator.

        Args:
            report: ValidationReport to add results to
        """
        self.report = report

    @override
    def validate(self, context: TailscaleConfigContext) -> None:
        """Check each DNS resource.

        Args:
            context: Context whose resources are checked.
        """
        for resource in context.resources:
            config = resource.config
            name = resource.name
            check = f"tailscale_dns_{name}"
            if resource.type == "dns_nameservers":
                servers = config.get("nameservers")
                if not isinstance(servers, list) or not servers:
                    fail(self.report, check, f"'{name}': nameservers must be a non-empty list")
                    continue
                for server in servers:
                    try:
                        ipaddress.ip_address(server)
                    except (ValueError, TypeError):
                        fail(
                            self.report,
                            check,
                            f"'{name}': nameserver {server!r} is not an IP address",
                        )
            elif resource.type == "dns_preferences":
                if not isinstance(config.get("magic_dns"), bool):
                    fail(self.report, check, f"'{name}': magic_dns must be true or false")
            elif resource.type == "dns_search_paths":
                paths = config.get("search_paths")
                if (
                    not isinstance(paths, list)
                    or not paths
                    or not all(isinstance(p, str) and p for p in paths)
                ):
                    fail(
                        self.report,
                        check,
                        f"'{name}': search_paths must be a non-empty list of non-empty strings",
                    )
