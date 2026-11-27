"""DNS resource validation."""

from __future__ import annotations

import ipaddress
from typing import Any, override

from infrafoundry.core.protocols import SpecializedValidator
from infrafoundry.core.validation import ValidationReport

from ._common import DOMAIN_RE, MAX_DOMAIN_LENGTH, fail
from .context import TailscaleConfigContext


class DnsValidator(SpecializedValidator[TailscaleConfigContext]):
    """Checks the DNS types: nameservers, preferences, search paths and split nameservers."""

    def __init__(self, report: ValidationReport) -> None:
        """Initialize the validator.

        Args:
            report: ValidationReport to add results to
        """
        self.report = report

    def _check_addresses(self, name: str, check: str, servers: Any, *, unique: bool) -> None:
        """Check that ``servers`` is a non-empty list of IP addresses.

        Args:
            name: Resource name for messages.
            check: Check name to record failures under.
            servers: The value to check.
            unique: Whether a repeated address is an error (the provider stores a set).
        """
        if not isinstance(servers, list) or not servers:
            fail(self.report, check, f"'{name}': nameservers must be a non-empty list")
            return
        seen: set[str] = set()
        for server in servers:
            try:
                address = ipaddress.ip_address(server)
            except (ValueError, TypeError):
                fail(self.report, check, f"'{name}': nameserver {server!r} is not an IP address")
                continue
            if unique and str(address) in seen:
                fail(self.report, check, f"'{name}': nameserver {server!r} is listed twice")
            seen.add(str(address))

    def _check_split(self, name: str, check: str, resource_config: dict[str, Any]) -> None:
        """Check one ``dns_split_nameservers`` resource."""
        domain = resource_config.get("domain")
        if (
            not isinstance(domain, str)
            or not domain
            or len(domain) > MAX_DOMAIN_LENGTH
            or not DOMAIN_RE.match(domain)
        ):
            fail(
                self.report,
                check,
                f"'{name}': domain must be a DNS name without a trailing dot, got {domain!r}",
            )
        self._check_addresses(name, check, resource_config.get("nameservers"), unique=True)

    @override
    def validate(self, context: TailscaleConfigContext) -> None:
        """Check each DNS resource.

        Args:
            context: Context whose resources are checked.
        """
        split_owners: dict[str, list[str]] = {}
        for resource in context.resources:
            config = resource.config
            name = resource.name
            check = f"tailscale_dns_{name}"
            if resource.type == "dns_nameservers":
                self._check_addresses(name, check, config.get("nameservers"), unique=False)
            elif resource.type == "dns_split_nameservers":
                self._check_split(name, check, config)
                domain = config.get("domain")
                if isinstance(domain, str) and domain:
                    split_owners.setdefault(domain.lower(), []).append(name)
                    if resource.import_id and resource.import_id.lower() != domain.lower():
                        fail(
                            self.report,
                            check,
                            f"'{name}': import_id {resource.import_id!r} must equal the "
                            f"domain {domain!r}; importing another route would replace it",
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
        for domain, owners in split_owners.items():
            if len(owners) > 1:
                fail(
                    self.report,
                    f"tailscale_dns_split_duplicate_domain_{domain}",
                    f"domain {domain!r} is declared by {', '.join(repr(o) for o in owners)}; "
                    "declare one dns_split_nameservers resource per domain",
                )
