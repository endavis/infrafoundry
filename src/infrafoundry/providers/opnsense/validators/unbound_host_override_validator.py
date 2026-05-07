"""Unbound host-override validation for OPNsense (ADR-0014, #776).

Plan-time validation for the ``unbound_host_override`` resource type. The
validator is deliberately split from the service-side
``unbound_host_override_configs_from_resources`` parser: the parser raises
on hard schema violations (missing required fields, non-bool booleans),
while the validator surfaces softer field-shape issues (rr-specific server
type mismatch — IPv4 for A, IPv6 for AAAA; missing/non-numeric mxprio for
MX; etc.) and uniqueness issues (duplicate ``(hostname, domain, rr)``
tuples within YAML) as ``ValidationReport`` entries.

Field rules:

- ``hostname``: required, non-empty string.
- ``domain``: required, non-empty string.
- ``rr``: optional, default ``A``. Must be one of ``A`` / ``AAAA`` / ``MX``.
- ``server``: optional. For ``rr=A`` must parse as IPv4; for ``rr=AAAA`` must
  parse as IPv6; for ``rr=MX`` is commonly absent (the MX target is
  ``mx``). Empty string is allowed across rr_types.
- ``mxprio``: required when ``rr=MX``. Must be a numeric string in range
  0-65535. Preserved as a string at the YAML layer to retain numeric
  precision (mirrors ``updatefreq`` handling on aliases).
- ``mx``: required when ``rr=MX``, otherwise ignored.
- ``description``: optional string.
- ``enabled``, ``lock``: must be booleans.
"""

from __future__ import annotations

import ipaddress

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport

# Allowed values for the ``rr`` discriminator. The parser already rejects
# the empty string and non-string values; this list narrows further.
_ALLOWED_RR: tuple[str, ...] = ("A", "AAAA", "MX")
_DEFAULT_RR = "A"


class UnboundHostOverrideValidator:
    """Validates OPNsense Unbound host-override resources."""

    def __init__(self, report: ValidationReport) -> None:
        """Initialize validator.

        Args:
            report: ValidationReport to add results to.
        """
        self.report = report

    def validate(self, overrides: list[ResourceConfig]) -> None:
        """Validate Unbound host-override resources.

        Args:
            overrides: ``unbound_host_override`` ``ResourceConfig`` entries.
        """
        seen_keys: dict[tuple[str, str, str], str] = {}
        for override in overrides:
            self._validate_one(override, seen_keys=seen_keys)

    def _validate_one(
        self,
        override: ResourceConfig,
        *,
        seen_keys: dict[tuple[str, str, str], str],
    ) -> None:
        """Run all checks for a single host-override entry."""
        hostname = self._validate_hostname(override)
        domain = self._validate_domain(override)
        rr = self._validate_rr(override)
        if rr is not None:
            self._validate_server(override, rr)
            self._validate_mx_fields(override, rr)
        self._validate_bool(override, "enabled")
        self._validate_bool(override, "lock")
        self._validate_description(override)

        if hostname is not None and domain is not None and rr is not None:
            self._validate_uniqueness(override, hostname, domain, rr, seen_keys)

    # ------------------------------------------------------------------
    # hostname / domain (required)
    # ------------------------------------------------------------------

    def _validate_hostname(self, override: ResourceConfig) -> str | None:
        """Validate the ``hostname`` field. Returns the value or None."""
        hostname = override.config.get("hostname")
        if hostname is None:
            self.report.add_check(
                check_name=f"unbound_host_override_{override.name}_hostname",
                passed=False,
                message=(
                    f"unbound_host_override '{override.name}' missing required field 'hostname'"
                ),
                level=ValidationLevel.ERROR,
            )
            return None
        if not isinstance(hostname, str) or not hostname:
            self.report.add_check(
                check_name=f"unbound_host_override_{override.name}_hostname",
                passed=False,
                message=(
                    f"unbound_host_override '{override.name}' hostname must be a non-empty string"
                ),
                level=ValidationLevel.ERROR,
            )
            return None
        return hostname

    def _validate_domain(self, override: ResourceConfig) -> str | None:
        """Validate the ``domain`` field. Returns the value or None."""
        domain = override.config.get("domain")
        if domain is None:
            self.report.add_check(
                check_name=f"unbound_host_override_{override.name}_domain",
                passed=False,
                message=(
                    f"unbound_host_override '{override.name}' missing required field 'domain'"
                ),
                level=ValidationLevel.ERROR,
            )
            return None
        if not isinstance(domain, str) or not domain:
            self.report.add_check(
                check_name=f"unbound_host_override_{override.name}_domain",
                passed=False,
                message=(
                    f"unbound_host_override '{override.name}' domain must be a non-empty string"
                ),
                level=ValidationLevel.ERROR,
            )
            return None
        return domain

    # ------------------------------------------------------------------
    # rr
    # ------------------------------------------------------------------

    def _validate_rr(self, override: ResourceConfig) -> str | None:
        """Validate the ``rr`` field. Returns the value or default ``A``."""
        if "rr" not in override.config:
            return _DEFAULT_RR
        value = override.config["rr"]
        if not isinstance(value, str) or value not in _ALLOWED_RR:
            self.report.add_check(
                check_name=f"unbound_host_override_{override.name}_rr",
                passed=False,
                message=(
                    f"unbound_host_override '{override.name}' rr {value!r} must be one of "
                    f"{', '.join(_ALLOWED_RR)}"
                ),
                level=ValidationLevel.ERROR,
            )
            return None
        return value

    # ------------------------------------------------------------------
    # server (rr-specific)
    # ------------------------------------------------------------------

    def _validate_server(self, override: ResourceConfig, rr: str) -> None:
        """Validate the ``server`` field against the rr type.

        Empty server is allowed (the GUI permits a record with only an MX
        target, for example). When non-empty, the address must parse as
        IPv4 for ``rr=A`` and IPv6 for ``rr=AAAA``. ``rr=MX`` typically
        carries no ``server`` (the target is ``mx``); a value is allowed
        but must still parse if provided.
        """
        if "server" not in override.config:
            return
        value = override.config["server"]
        if not isinstance(value, str):
            self.report.add_check(
                check_name=f"unbound_host_override_{override.name}_server",
                passed=False,
                message=(
                    f"unbound_host_override '{override.name}' server must be a string, "
                    f"got {type(value).__name__}"
                ),
                level=ValidationLevel.ERROR,
            )
            return
        if not value:
            return  # Empty is fine across rr types.
        try:
            address = ipaddress.ip_address(value)
        except ValueError:
            self.report.add_check(
                check_name=f"unbound_host_override_{override.name}_server",
                passed=False,
                message=(
                    f"unbound_host_override '{override.name}' server {value!r} is not a "
                    f"valid IPv4 or IPv6 address"
                ),
                level=ValidationLevel.ERROR,
            )
            return
        if rr == "A" and not isinstance(address, ipaddress.IPv4Address):
            self.report.add_check(
                check_name=f"unbound_host_override_{override.name}_server",
                passed=False,
                message=(
                    f"unbound_host_override '{override.name}' server {value!r} is not IPv4 "
                    f"(rr=A requires IPv4)"
                ),
                level=ValidationLevel.ERROR,
            )
        elif rr == "AAAA" and not isinstance(address, ipaddress.IPv6Address):
            self.report.add_check(
                check_name=f"unbound_host_override_{override.name}_server",
                passed=False,
                message=(
                    f"unbound_host_override '{override.name}' server {value!r} is not IPv6 "
                    f"(rr=AAAA requires IPv6)"
                ),
                level=ValidationLevel.ERROR,
            )

    # ------------------------------------------------------------------
    # mxprio / mx (MX-only)
    # ------------------------------------------------------------------

    def _validate_mx_fields(self, override: ResourceConfig, rr: str) -> None:
        """Validate ``mxprio`` and ``mx`` for MX records."""
        if rr != "MX":
            return

        mxprio = override.config.get("mxprio")
        if mxprio is None or mxprio == "":
            self.report.add_check(
                check_name=f"unbound_host_override_{override.name}_mxprio",
                passed=False,
                message=(f"unbound_host_override '{override.name}' mxprio is required when rr=MX"),
                level=ValidationLevel.ERROR,
            )
        elif not isinstance(mxprio, str):
            self.report.add_check(
                check_name=f"unbound_host_override_{override.name}_mxprio",
                passed=False,
                message=(
                    f"unbound_host_override '{override.name}' mxprio must be a string "
                    f"(preserved as string for numeric precision), "
                    f"got {type(mxprio).__name__}"
                ),
                level=ValidationLevel.ERROR,
            )
        else:
            try:
                priority = int(mxprio)
            except ValueError:
                self.report.add_check(
                    check_name=f"unbound_host_override_{override.name}_mxprio",
                    passed=False,
                    message=(
                        f"unbound_host_override '{override.name}' mxprio {mxprio!r} is "
                        f"not a numeric string"
                    ),
                    level=ValidationLevel.ERROR,
                )
            else:
                if priority < 0 or priority > 65535:
                    self.report.add_check(
                        check_name=f"unbound_host_override_{override.name}_mxprio",
                        passed=False,
                        message=(
                            f"unbound_host_override '{override.name}' mxprio {priority} "
                            f"out of range 0-65535"
                        ),
                        level=ValidationLevel.ERROR,
                    )

        mx = override.config.get("mx")
        if mx is None or mx == "":
            self.report.add_check(
                check_name=f"unbound_host_override_{override.name}_mx",
                passed=False,
                message=(f"unbound_host_override '{override.name}' mx is required when rr=MX"),
                level=ValidationLevel.ERROR,
            )
        elif not isinstance(mx, str):
            self.report.add_check(
                check_name=f"unbound_host_override_{override.name}_mx",
                passed=False,
                message=(
                    f"unbound_host_override '{override.name}' mx must be a string, "
                    f"got {type(mx).__name__}"
                ),
                level=ValidationLevel.ERROR,
            )

    # ------------------------------------------------------------------
    # uniqueness
    # ------------------------------------------------------------------

    def _validate_uniqueness(
        self,
        override: ResourceConfig,
        hostname: str,
        domain: str,
        rr: str,
        seen_keys: dict[tuple[str, str, str], str],
    ) -> None:
        """Reject two YAML entries with the same ``(hostname, domain, rr)`` tuple."""
        key = (hostname, domain, rr)
        prior = seen_keys.get(key)
        if prior is not None:
            self.report.add_check(
                check_name=f"unbound_host_override_{override.name}_uniqueness",
                passed=False,
                message=(
                    f"unbound_host_override '{override.name}' duplicates the "
                    f"(hostname, domain, rr) tuple of '{prior}' "
                    f"(hostname={hostname!r}, domain={domain!r}, rr={rr!r})"
                ),
                level=ValidationLevel.ERROR,
            )
            return
        seen_keys[key] = override.name

    # ------------------------------------------------------------------
    # bool fields
    # ------------------------------------------------------------------

    def _validate_bool(self, override: ResourceConfig, field_name: str) -> None:
        if field_name not in override.config:
            return
        value = override.config[field_name]
        if not isinstance(value, bool):
            self.report.add_check(
                check_name=f"unbound_host_override_{override.name}_{field_name}",
                passed=False,
                message=(
                    f"unbound_host_override '{override.name}' {field_name} must be a "
                    f"boolean (true/false), got {type(value).__name__}"
                ),
                level=ValidationLevel.ERROR,
            )

    # ------------------------------------------------------------------
    # description
    # ------------------------------------------------------------------

    def _validate_description(self, override: ResourceConfig) -> None:
        if "description" not in override.config:
            return
        value = override.config["description"]
        if not isinstance(value, str):
            self.report.add_check(
                check_name=f"unbound_host_override_{override.name}_description",
                passed=False,
                message=(
                    f"unbound_host_override '{override.name}' description must be a string, "
                    f"got {type(value).__name__}"
                ),
                level=ValidationLevel.ERROR,
            )
