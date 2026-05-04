"""Unbound host-alias validation for OPNsense (ADR-0014, #724).

Plan-time validation for the ``unbound_host_alias`` resource type. The
validator is deliberately split from the service-side
``unbound_host_alias_configs_from_resources`` parser: the parser raises
on hard schema violations (missing required fields, non-bool booleans),
while the validator surfaces softer cross-resource reference issues
(unknown ``host`` reference) and uniqueness issues
(duplicate ``(host, hostname)`` tuples within YAML) as
``ValidationReport`` entries.

Cross-reference targets:

- ``host``: must reference either a managed ``unbound_host_override``
  resource declared in YAML *or* a live host override returned by
  OPNsense's ``searchHostOverride``. The Terraform-managed existing
  ``unbound_host_override`` is currently the source of truth for live
  state; the validator accepts either form so operators can compose
  managed and live names freely.
"""

from __future__ import annotations

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport


class UnboundHostAliasValidator:
    """Validates OPNsense Unbound host-alias resources against managed + live state."""

    def __init__(self, report: ValidationReport) -> None:
        """Initialize validator.

        Args:
            report: ValidationReport to add results to.
        """
        self.report = report

    def validate(
        self,
        host_aliases: list[ResourceConfig],
        managed_host_override_names: set[str],
        existing_host_override_names: set[str],
    ) -> None:
        """Validate Unbound host-alias resources.

        Args:
            host_aliases: ``unbound_host_alias`` ``ResourceConfig`` entries.
            managed_host_override_names: Set of managed
                ``unbound_host_override`` names declared in YAML.
            existing_host_override_names: Set of live host-override names
                returned by OPNsense's ``searchHostOverride`` (the
                ``hostname.domain`` form, plus the bare hostname for
                short-name references).
        """
        seen_keys: dict[tuple[str, str], str] = {}
        for alias in host_aliases:
            self._validate_one(
                alias,
                managed_host_override_names=managed_host_override_names,
                existing_host_override_names=existing_host_override_names,
                seen_keys=seen_keys,
            )

    def _validate_one(
        self,
        alias: ResourceConfig,
        *,
        managed_host_override_names: set[str],
        existing_host_override_names: set[str],
        seen_keys: dict[tuple[str, str], str],
    ) -> None:
        """Run all checks for a single host-alias entry."""
        host = self._validate_host(
            alias,
            managed_host_override_names=managed_host_override_names,
            existing_host_override_names=existing_host_override_names,
        )
        hostname = self._validate_hostname(alias)
        self._validate_domain(alias)
        self._validate_bool(alias, "enabled")
        self._validate_bool(alias, "lock")
        self._validate_description(alias)

        if host is not None and hostname is not None:
            self._validate_uniqueness(alias, host, hostname, seen_keys)

    # ------------------------------------------------------------------
    # host (cross-ref)
    # ------------------------------------------------------------------

    def _validate_host(
        self,
        alias: ResourceConfig,
        *,
        managed_host_override_names: set[str],
        existing_host_override_names: set[str],
    ) -> str | None:
        """Validate the ``host`` cross-reference. Returns the value or None."""
        host = alias.config.get("host")
        if host is None:
            self.report.add_check(
                check_name=f"unbound_host_alias_{alias.name}_host",
                passed=False,
                message=(f"unbound_host_alias '{alias.name}' missing required field 'host'"),
                level=ValidationLevel.ERROR,
            )
            return None
        if not isinstance(host, str) or not host:
            self.report.add_check(
                check_name=f"unbound_host_alias_{alias.name}_host",
                passed=False,
                message=(f"unbound_host_alias '{alias.name}' host must be a non-empty string"),
                level=ValidationLevel.ERROR,
            )
            return None
        if host in managed_host_override_names or host in existing_host_override_names:
            self.report.add_check(
                check_name=f"unbound_host_alias_{alias.name}_host",
                passed=True,
                message=(f"Host '{host}' resolved for unbound_host_alias '{alias.name}'"),
                level=ValidationLevel.INFO,
            )
            return host
        self.report.add_check(
            check_name=f"unbound_host_alias_{alias.name}_host",
            passed=False,
            message=(
                f"unbound_host_alias '{alias.name}' references unknown host '{host}'; "
                f"expected a managed 'unbound_host_override' resource name or a live "
                f"OPNsense host override (hostname or hostname.domain)"
            ),
            level=ValidationLevel.ERROR,
        )
        return None

    # ------------------------------------------------------------------
    # hostname / domain (required)
    # ------------------------------------------------------------------

    def _validate_hostname(self, alias: ResourceConfig) -> str | None:
        """Validate the ``hostname`` field. Returns the value or None."""
        hostname = alias.config.get("hostname")
        if hostname is None:
            self.report.add_check(
                check_name=f"unbound_host_alias_{alias.name}_hostname",
                passed=False,
                message=(f"unbound_host_alias '{alias.name}' missing required field 'hostname'"),
                level=ValidationLevel.ERROR,
            )
            return None
        if not isinstance(hostname, str) or not hostname:
            self.report.add_check(
                check_name=f"unbound_host_alias_{alias.name}_hostname",
                passed=False,
                message=(f"unbound_host_alias '{alias.name}' hostname must be a non-empty string"),
                level=ValidationLevel.ERROR,
            )
            return None
        return hostname

    def _validate_domain(self, alias: ResourceConfig) -> None:
        """Validate the ``domain`` field is present and a non-empty string."""
        domain = alias.config.get("domain")
        if domain is None:
            self.report.add_check(
                check_name=f"unbound_host_alias_{alias.name}_domain",
                passed=False,
                message=(f"unbound_host_alias '{alias.name}' missing required field 'domain'"),
                level=ValidationLevel.ERROR,
            )
            return
        if not isinstance(domain, str) or not domain:
            self.report.add_check(
                check_name=f"unbound_host_alias_{alias.name}_domain",
                passed=False,
                message=(f"unbound_host_alias '{alias.name}' domain must be a non-empty string"),
                level=ValidationLevel.ERROR,
            )

    # ------------------------------------------------------------------
    # uniqueness
    # ------------------------------------------------------------------

    def _validate_uniqueness(
        self,
        alias: ResourceConfig,
        host: str,
        hostname: str,
        seen_keys: dict[tuple[str, str], str],
    ) -> None:
        """Reject two YAML entries with the same ``(host, hostname)`` tuple."""
        key = (host, hostname)
        prior = seen_keys.get(key)
        if prior is not None:
            self.report.add_check(
                check_name=f"unbound_host_alias_{alias.name}_uniqueness",
                passed=False,
                message=(
                    f"unbound_host_alias '{alias.name}' duplicates the (host, hostname) "
                    f"tuple of '{prior}' (host={host!r}, hostname={hostname!r})"
                ),
                level=ValidationLevel.ERROR,
            )
            return
        seen_keys[key] = alias.name

    # ------------------------------------------------------------------
    # bool fields
    # ------------------------------------------------------------------

    def _validate_bool(self, alias: ResourceConfig, field_name: str) -> None:
        if field_name not in alias.config:
            return
        value = alias.config[field_name]
        if not isinstance(value, bool):
            self.report.add_check(
                check_name=f"unbound_host_alias_{alias.name}_{field_name}",
                passed=False,
                message=(
                    f"unbound_host_alias '{alias.name}' {field_name} must be a "
                    f"boolean (true/false), got {type(value).__name__}"
                ),
                level=ValidationLevel.ERROR,
            )

    # ------------------------------------------------------------------
    # description
    # ------------------------------------------------------------------

    def _validate_description(self, alias: ResourceConfig) -> None:
        if "description" not in alias.config:
            return
        value = alias.config["description"]
        if not isinstance(value, str):
            self.report.add_check(
                check_name=f"unbound_host_alias_{alias.name}_description",
                passed=False,
                message=(
                    f"unbound_host_alias '{alias.name}' description must be a string, "
                    f"got {type(value).__name__}"
                ),
                level=ValidationLevel.ERROR,
            )
