"""Firewall-alias validation for OPNsense (ADR-0014, #775).

Plan-time validation for the ``aliases`` resource type. The validator
is deliberately split from the service-side
``alias_configs_from_resources`` parser: the parser raises on hard
schema violations (missing required fields, non-bool booleans), while
the validator surfaces softer problems (name length / charset, unknown
``type``, malformed ``content`` per type, duplicate names within YAML)
as ``ValidationReport`` entries.

Validation surface:

- ``name``: 1-32 chars, charset ``[A-Za-z0-9_]`` (OPNsense's wire rule;
  the GUI rejects names that don't match this pattern). Reserved names
  (``pkg-*``, ``__*``, ``bogons``, ``virusprot``, ``sshlockout``,
  ``bogonsv6``) are rejected because OPNsense uses them for system
  aliases and the API will fail at apply time.
- ``type``: one of the OPNsense-supported alias kinds. Unknown kinds
  flag a soft warning (the wire surface keeps changing across OPNsense
  versions; we don't want a too-strict allowlist to break a new release
  the moment it ships).
- ``content``: shape per type — IP/CIDR for ``host`` / ``network``,
  port number/range for ``port`` / ``urltable_ports``, country code for
  ``geoip``, URL for ``url`` / ``urltable``, etc.
- ``proto``: ``IPv4`` / ``IPv6`` only, and only meaningful when
  ``type == geoip``.
- ``updatefreq``: must parse as a positive number (string preserved
  verbatim to retain decimal precision).
- ``categories``: list of strings (UUIDs from the OPNsense category
  catalog); empty list is fine.
- ``counters``: bool.
- ``interface``: only meaningful when ``type == dynipv6host``.
- Uniqueness: two YAML entries with the same wire ``name`` collide
  server-side; flag it at plan time.
"""

from __future__ import annotations

import ipaddress
import re
from typing import Any

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport

# Recognized alias types per the OPNsense GUI's "Type" dropdown on the
# Firewall → Aliases form. Unknown values produce a warning (not an
# error) — OPNsense's wire surface evolves with each minor release and
# we'd rather not block a new release the moment a new kind ships.
_KNOWN_ALIAS_TYPES: frozenset[str] = frozenset(
    {
        "host",
        "network",
        "networkgroup",
        "port",
        "url",
        "urljson",
        "urltable",
        "urltable_ports",
        "geoip",
        "mac",
        "asn",
        "bgpasn",
        "dynipv6host",
        "openvpn",
        "authgroup",
        "external",
        "internal",
    }
)

# OPNsense's wire rule for alias names. The GUI's `Validators::regex` matches
# exactly this charset; longer or differently-cased names produce a
# server-side validation error at apply time.
_NAME_RE = re.compile(r"^[A-Za-z0-9_]+$")
_NAME_MAX_LEN = 32

# Names OPNsense reserves for system aliases. Operators who ship one of
# these in YAML will get a server-side rejection; flag at plan time.
_RESERVED_NAME_PREFIXES: tuple[str, ...] = ("pkg-", "__")
_RESERVED_NAMES: frozenset[str] = frozenset({"bogons", "bogonsv6", "sshlockout", "virusprot"})

# Port aliases accept either bare port numbers or hyphenated ranges.
_PORT_RE = re.compile(r"^\d+(-\d+)?$")
# GeoIP content is a 2-letter country code per ISO 3166-1 alpha-2.
_GEOIP_RE = re.compile(r"^[A-Z]{2}$")
# MAC alias content is a colon-separated hex string; OPNsense accepts
# partial matches (e.g., ``aa:bb`` for a vendor-prefix alias) so the
# regex is permissive about length.
_MAC_RE = re.compile(r"^([0-9a-fA-F]{2})(:[0-9a-fA-F]{2}){0,5}$")


class AliasValidator:
    """Validates OPNsense firewall-alias resources."""

    def __init__(self, report: ValidationReport) -> None:
        """Initialize validator.

        Args:
            report: ValidationReport to add results to.
        """
        self.report = report

    def validate(self, aliases: list[ResourceConfig]) -> None:
        """Validate alias resources.

        Args:
            aliases: ``aliases`` ``ResourceConfig`` entries.
        """
        seen_names: dict[str, str] = {}
        for alias in aliases:
            self._validate_one(alias, seen_names=seen_names)

    def _validate_one(
        self,
        alias: ResourceConfig,
        *,
        seen_names: dict[str, str],
    ) -> None:
        """Run all checks for a single alias entry."""
        wire_name = self._validate_name(alias)
        alias_type = self._validate_type(alias)
        self._validate_content(alias, alias_type)
        self._validate_proto(alias, alias_type)
        self._validate_updatefreq(alias)
        self._validate_categories(alias)
        self._validate_bool(alias, "enabled")
        self._validate_bool(alias, "counters")
        self._validate_bool(alias, "lock")
        self._validate_description(alias)

        if wire_name is not None:
            self._validate_uniqueness(alias, wire_name, seen_names)

    # ------------------------------------------------------------------
    # name
    # ------------------------------------------------------------------

    def _validate_name(self, alias: ResourceConfig) -> str | None:
        """Validate the ``config.name`` (wire identity)."""
        config_name = alias.config.get("name", alias.name)
        if not isinstance(config_name, str) or not config_name:
            self.report.add_check(
                check_name=f"alias_{alias.name}_name",
                passed=False,
                message=(
                    f"alias '{alias.name}' requires a non-empty string 'name' "
                    f"(or a non-empty top-level resource name)"
                ),
                level=ValidationLevel.ERROR,
            )
            return None

        if len(config_name) > _NAME_MAX_LEN:
            self.report.add_check(
                check_name=f"alias_{alias.name}_name",
                passed=False,
                message=(
                    f"alias '{alias.name}' name '{config_name}' exceeds "
                    f"{_NAME_MAX_LEN} characters (OPNsense wire limit)"
                ),
                level=ValidationLevel.ERROR,
            )
            return None

        if not _NAME_RE.match(config_name):
            self.report.add_check(
                check_name=f"alias_{alias.name}_name",
                passed=False,
                message=(
                    f"alias '{alias.name}' name '{config_name}' must match "
                    f"^[A-Za-z0-9_]+$ (OPNsense wire rule; hyphens, dots, "
                    f"and other punctuation are rejected by the API)"
                ),
                level=ValidationLevel.ERROR,
            )
            return None

        if _is_reserved_name(config_name):
            self.report.add_check(
                check_name=f"alias_{alias.name}_name",
                passed=False,
                message=(
                    f"alias '{alias.name}' name '{config_name}' collides with "
                    f"an OPNsense reserved system-alias name; rename to avoid "
                    f"a server-side rejection at apply time"
                ),
                level=ValidationLevel.ERROR,
            )
            return None

        return config_name

    # ------------------------------------------------------------------
    # type
    # ------------------------------------------------------------------

    def _validate_type(self, alias: ResourceConfig) -> str | None:
        """Validate the ``config.type`` field. Returns the type or None."""
        alias_type = alias.config.get("type")
        if alias_type is None:
            self.report.add_check(
                check_name=f"alias_{alias.name}_type",
                passed=False,
                message=f"alias '{alias.name}' missing required field 'type'",
                level=ValidationLevel.ERROR,
            )
            return None
        if not isinstance(alias_type, str) or not alias_type:
            self.report.add_check(
                check_name=f"alias_{alias.name}_type",
                passed=False,
                message=f"alias '{alias.name}' type must be a non-empty string",
                level=ValidationLevel.ERROR,
            )
            return None
        if alias_type not in _KNOWN_ALIAS_TYPES:
            # Soft warning — OPNsense adds new alias kinds across releases
            # and we don't want a too-strict allowlist to block them.
            self.report.add_check(
                check_name=f"alias_{alias.name}_type",
                passed=False,
                message=(
                    f"alias '{alias.name}' type '{alias_type}' is not a known "
                    f"OPNsense alias kind; expected one of "
                    f"{sorted(_KNOWN_ALIAS_TYPES)}"
                ),
                level=ValidationLevel.WARNING,
            )
            return alias_type
        if alias_type in _SYSTEM_ONLY_TYPES:
            # ``internal`` / ``external`` are operator-unwritable. The
            # diff engine filters them server-side, but flagging at plan
            # time gives the operator a clearer signal than a silent
            # no-op apply.
            self.report.add_check(
                check_name=f"alias_{alias.name}_type",
                passed=False,
                message=(
                    f"alias '{alias.name}' type '{alias_type}' is OPNsense-managed "
                    f"and cannot be created or edited via the alias API"
                ),
                level=ValidationLevel.ERROR,
            )
            return alias_type
        return alias_type

    # ------------------------------------------------------------------
    # content (per type)
    # ------------------------------------------------------------------

    def _validate_content(self, alias: ResourceConfig, alias_type: str | None) -> None:
        """Validate ``config.content`` shape against the alias type."""
        content = alias.config.get("content")
        if content is None:
            # Some alias kinds (e.g., empty placeholder) don't strictly
            # require content; defer the requirement check to OPNsense.
            return
        if not isinstance(content, list):
            self.report.add_check(
                check_name=f"alias_{alias.name}_content",
                passed=False,
                message=(f"alias '{alias.name}' content must be a list"),
                level=ValidationLevel.ERROR,
            )
            return
        for idx, entry in enumerate(content):
            if not isinstance(entry, str):
                self.report.add_check(
                    check_name=f"alias_{alias.name}_content_{idx}",
                    passed=False,
                    message=(
                        f"alias '{alias.name}' content[{idx}] must be a string, "
                        f"got {type(entry).__name__}"
                    ),
                    level=ValidationLevel.ERROR,
                )
                continue
            if alias_type is not None:
                self._validate_content_entry(alias, alias_type, idx, entry)

    def _validate_content_entry(
        self,
        alias: ResourceConfig,
        alias_type: str,
        idx: int,
        entry: str,
    ) -> None:
        """Validate a single content list entry against its alias type."""
        check_name = f"alias_{alias.name}_content_{idx}"

        if alias_type in {"host", "network"}:
            if not _is_valid_ip_or_cidr(entry):
                self.report.add_check(
                    check_name=check_name,
                    passed=False,
                    message=(
                        f"alias '{alias.name}' content[{idx}] '{entry}' is not a "
                        f"valid IP address or CIDR for type '{alias_type}'"
                    ),
                    level=ValidationLevel.ERROR,
                )
            return

        if alias_type in {"port", "urltable_ports"}:
            if not _PORT_RE.match(entry):
                self.report.add_check(
                    check_name=check_name,
                    passed=False,
                    message=(
                        f"alias '{alias.name}' content[{idx}] '{entry}' is not a "
                        f"valid port number or hyphenated range for type "
                        f"'{alias_type}'"
                    ),
                    level=ValidationLevel.ERROR,
                )
            return

        if alias_type == "geoip":
            if not _GEOIP_RE.match(entry):
                self.report.add_check(
                    check_name=check_name,
                    passed=False,
                    message=(
                        f"alias '{alias.name}' content[{idx}] '{entry}' is not a "
                        f"valid 2-letter ISO 3166-1 alpha-2 country code for "
                        f"type 'geoip'"
                    ),
                    level=ValidationLevel.ERROR,
                )
            return

        if alias_type == "mac":
            if not _MAC_RE.match(entry):
                self.report.add_check(
                    check_name=check_name,
                    passed=False,
                    message=(
                        f"alias '{alias.name}' content[{idx}] '{entry}' is not a "
                        f"valid MAC address (or partial vendor prefix) for "
                        f"type 'mac'"
                    ),
                    level=ValidationLevel.ERROR,
                )
            return

        # ``url`` / ``urltable`` / ``urljson`` / ``networkgroup`` /
        # ``asn`` / ``bgpasn`` / ``dynipv6host`` / ``openvpn`` /
        # ``authgroup`` — accept any non-empty string. The OPNsense API
        # is the authority for the per-type schema; we limit ourselves
        # to the kinds where a regex is safe to apply.

    # ------------------------------------------------------------------
    # proto
    # ------------------------------------------------------------------

    def _validate_proto(self, alias: ResourceConfig, alias_type: str | None) -> None:
        """Validate ``config.proto`` (geoip-specific)."""
        if "proto" not in alias.config:
            return
        proto = alias.config["proto"]
        if not isinstance(proto, str):
            self.report.add_check(
                check_name=f"alias_{alias.name}_proto",
                passed=False,
                message=(
                    f"alias '{alias.name}' proto must be a string, got {type(proto).__name__}"
                ),
                level=ValidationLevel.ERROR,
            )
            return
        if proto and proto not in {"IPv4", "IPv6"}:
            self.report.add_check(
                check_name=f"alias_{alias.name}_proto",
                passed=False,
                message=(f"alias '{alias.name}' proto '{proto}' must be 'IPv4' or 'IPv6'"),
                level=ValidationLevel.ERROR,
            )
            return
        if proto and alias_type is not None and alias_type != "geoip":
            self.report.add_check(
                check_name=f"alias_{alias.name}_proto",
                passed=False,
                message=(
                    f"alias '{alias.name}' proto is only meaningful when "
                    f"type='geoip' (current type='{alias_type}')"
                ),
                level=ValidationLevel.WARNING,
            )

    # ------------------------------------------------------------------
    # updatefreq
    # ------------------------------------------------------------------

    def _validate_updatefreq(self, alias: ResourceConfig) -> None:
        """Validate ``config.updatefreq`` parses as a positive number."""
        if "updatefreq" not in alias.config:
            return
        value = alias.config["updatefreq"]
        if not isinstance(value, str):
            self.report.add_check(
                check_name=f"alias_{alias.name}_updatefreq",
                passed=False,
                message=(
                    f"alias '{alias.name}' updatefreq must be a string "
                    f"(preserved verbatim for decimal precision), "
                    f"got {type(value).__name__}"
                ),
                level=ValidationLevel.ERROR,
            )
            return
        if not value:
            return
        try:
            parsed = float(value)
        except ValueError:
            self.report.add_check(
                check_name=f"alias_{alias.name}_updatefreq",
                passed=False,
                message=(
                    f"alias '{alias.name}' updatefreq '{value}' is not a valid number (in days)"
                ),
                level=ValidationLevel.ERROR,
            )
            return
        if parsed <= 0:
            self.report.add_check(
                check_name=f"alias_{alias.name}_updatefreq",
                passed=False,
                message=(f"alias '{alias.name}' updatefreq '{value}' must be positive (in days)"),
                level=ValidationLevel.ERROR,
            )

    # ------------------------------------------------------------------
    # categories
    # ------------------------------------------------------------------

    def _validate_categories(self, alias: ResourceConfig) -> None:
        """Validate ``config.categories`` is a list of strings."""
        if "categories" not in alias.config:
            return
        categories = alias.config["categories"]
        if not isinstance(categories, list):
            self.report.add_check(
                check_name=f"alias_{alias.name}_categories",
                passed=False,
                message=(f"alias '{alias.name}' categories must be a list"),
                level=ValidationLevel.ERROR,
            )
            return
        for idx, cat in enumerate(categories):
            if not isinstance(cat, str):
                self.report.add_check(
                    check_name=f"alias_{alias.name}_categories_{idx}",
                    passed=False,
                    message=(
                        f"alias '{alias.name}' categories[{idx}] must be a string, "
                        f"got {type(cat).__name__}"
                    ),
                    level=ValidationLevel.ERROR,
                )

    # ------------------------------------------------------------------
    # bool fields
    # ------------------------------------------------------------------

    def _validate_bool(self, alias: ResourceConfig, field_name: str) -> None:
        if field_name not in alias.config:
            return
        value = alias.config[field_name]
        if not isinstance(value, bool):
            self.report.add_check(
                check_name=f"alias_{alias.name}_{field_name}",
                passed=False,
                message=(
                    f"alias '{alias.name}' {field_name} must be a boolean "
                    f"(true/false), got {type(value).__name__}"
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
                check_name=f"alias_{alias.name}_description",
                passed=False,
                message=(
                    f"alias '{alias.name}' description must be a string, got {type(value).__name__}"
                ),
                level=ValidationLevel.ERROR,
            )

    # ------------------------------------------------------------------
    # uniqueness
    # ------------------------------------------------------------------

    def _validate_uniqueness(
        self,
        alias: ResourceConfig,
        wire_name: str,
        seen_names: dict[str, str],
    ) -> None:
        """Reject two YAML entries with the same wire ``name``."""
        prior = seen_names.get(wire_name)
        if prior is not None:
            self.report.add_check(
                check_name=f"alias_{alias.name}_uniqueness",
                passed=False,
                message=(
                    f"alias '{alias.name}' duplicates the wire name "
                    f"'{wire_name}' of '{prior}'; OPNsense enforces alias "
                    f"name uniqueness server-side"
                ),
                level=ValidationLevel.ERROR,
            )
            return
        seen_names[wire_name] = alias.name


# Operator-unwritable alias kinds. Defined at module scope for clarity
# on the validator surface; the diff engine has its own copy in
# ``services/alias.py`` to avoid a cross-package import cycle.
_SYSTEM_ONLY_TYPES: frozenset[str] = frozenset({"internal", "external"})


def _is_reserved_name(name: str) -> bool:
    """Return True if ``name`` is reserved by OPNsense for system use."""
    if name in _RESERVED_NAMES:
        return True
    return any(name.startswith(prefix) for prefix in _RESERVED_NAME_PREFIXES)


def _is_valid_ip_or_cidr(value: str) -> bool:
    """Return True if ``value`` parses as an IP address or CIDR network."""
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        pass
    try:
        # ``strict=False`` allows host bits set, matching OPNsense's
        # acceptance of e.g. ``192.168.1.10/24`` for host aliases.
        ipaddress.ip_network(value, strict=False)
        return True
    except ValueError:
        return False


def _is_known_type(value: Any) -> bool:
    """Helper for tests — returns True if ``value`` is a recognized alias type."""
    return isinstance(value, str) and value in _KNOWN_ALIAS_TYPES
