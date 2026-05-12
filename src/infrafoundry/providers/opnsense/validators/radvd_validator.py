"""Radvd validator for OPNsense (#788).

Plan-time validation for the ``radvd`` dotted resource type — a
dict-shape singleton whose ``interfaces`` mapping carries one inner
mapping per interface. The validator is pure-check; it never mutates
``resource.config`` (per the singleton-validator convention established
by #806).

Cross-reference targets:

- ``interfaces.<key>``: each key (e.g. ``opt1``) must reference either a
  managed ``interfaces.assignments[].name`` OR a live overview interface.
  Mirrors ``gateway_validator._validate_interface()``.

Field-shape checks per inner mapping:

- ``mode`` ∈ {``router``, ``unmanaged``, ``managed``, ``assist``,
  ``stateless``} (NOT ``disabled`` — use ``enabled: false``).
- ``priority`` ∈ {``low``, ``medium``, ``high``}.
- ``min_interval`` ≤ ``max_interval`` (positive integers).
- ``routes``: each entry parses as a valid IPv6 CIDR.
- ``dns_servers``: each entry parses as a valid IPv6 address.
- ``domain_search``: each entry parses as a valid DNS domain.
- Boolean-ish fields (``enabled``, ``dns``) accept bool/int/str truthy
  forms.
"""

from __future__ import annotations

import ipaddress
import re
from typing import Any

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport

# Valid mode values per the live OPNsense schema (probe-788.md, 2026-05-10).
_VALID_MODES: frozenset[str] = frozenset({"router", "unmanaged", "managed", "assist", "stateless"})

# Valid priority values per the wire's ``AdvDefaultPreference`` schema.
_VALID_PRIORITIES: frozenset[str] = frozenset({"low", "medium", "high"})

# Truthy / falsy single-select values for the optional tri-state fields.
_VALID_TRISTATE: frozenset[str] = frozenset({"", "on", "off"})

# RFC 1123 DNS-name check (single label or dotted FQDN). Borrowed from
# ``gateway_validator``'s ``_HOSTNAME_RE``.
_HOSTNAME_RE = re.compile(
    r"^(?=.{1,253}$)(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.(?!-)[A-Za-z0-9-]{1,63}(?<!-))*$"
)


class RadvdValidator:
    """Validates OPNsense radvd singleton + per-interface inner fields."""

    def __init__(self, report: ValidationReport) -> None:
        """Initialize the validator.

        Args:
            report: ``ValidationReport`` to add results to.
        """
        self.report = report

    def validate(
        self,
        resources: list[ResourceConfig],
        interface_assignment_names: set[str],
        existing_interfaces: dict[str, Any],
    ) -> None:
        """Validate the radvd singleton.

        Args:
            resources: ``radvd`` ``ResourceConfig`` entries (zero or one).
            interface_assignment_names: Set of managed
                ``interfaces.assignments[].name`` values from YAML.
            existing_interfaces: Live interface map from
                ``OPNsenseValidator._get_existing_interfaces``.
        """
        if not resources:
            return
        # The loader's structural discrimination guarantees exactly one
        # singleton, but defensively iterate.
        for resource in resources:
            self._validate_one(
                resource,
                interface_assignment_names=interface_assignment_names,
                existing_interfaces=existing_interfaces,
            )

    def _validate_one(
        self,
        resource: ResourceConfig,
        *,
        interface_assignment_names: set[str],
        existing_interfaces: dict[str, Any],
    ) -> None:
        config = resource.config
        interfaces_block = config.get("interfaces", {})
        if not isinstance(interfaces_block, dict):
            self.report.add_check(
                check_name="radvd_interfaces_shape",
                passed=False,
                message=(
                    f"radvd.interfaces must be a mapping, got {type(interfaces_block).__name__}"
                ),
                level=ValidationLevel.ERROR,
            )
            return

        for interface_name, inner in interfaces_block.items():
            self._validate_interface_key(
                interface_name,
                interface_assignment_names=interface_assignment_names,
                existing_interfaces=existing_interfaces,
            )
            if not isinstance(inner, dict):
                self.report.add_check(
                    check_name=f"radvd_{interface_name}_shape",
                    passed=False,
                    message=(
                        f"radvd.interfaces.{interface_name} must be a mapping, "
                        f"got {type(inner).__name__}"
                    ),
                    level=ValidationLevel.ERROR,
                )
                continue
            self._validate_inner_fields(str(interface_name), inner)

    # ------------------------------------------------------------------
    # interface key xref
    # ------------------------------------------------------------------

    def _validate_interface_key(
        self,
        interface_name: Any,
        *,
        interface_assignment_names: set[str],
        existing_interfaces: dict[str, Any],
    ) -> None:
        if not isinstance(interface_name, str) or not interface_name:
            self.report.add_check(
                check_name="radvd_interface_key",
                passed=False,
                message=(
                    f"radvd.interfaces keys must be non-empty strings, got {interface_name!r}"
                ),
                level=ValidationLevel.ERROR,
            )
            return
        if interface_name in interface_assignment_names:
            self.report.add_check(
                check_name=f"radvd_{interface_name}_interface",
                passed=True,
                message=(
                    f"Interface {interface_name!r} resolved to managed "
                    f"interface_assignment for radvd"
                ),
                level=ValidationLevel.INFO,
            )
            return
        if interface_name in existing_interfaces:
            self.report.add_check(
                check_name=f"radvd_{interface_name}_interface",
                passed=True,
                message=(
                    f"Interface {interface_name!r} resolved to live OPNsense "
                    f"interface for radvd (no managed YAML reference)"
                ),
                level=ValidationLevel.INFO,
            )
            return
        self.report.add_check(
            check_name=f"radvd_{interface_name}_interface",
            passed=False,
            message=(
                f"radvd.interfaces.{interface_name} references unknown interface; "
                f"expected a managed interface_assignment name or a live OPNsense interface"
            ),
            level=ValidationLevel.ERROR,
        )

    # ------------------------------------------------------------------
    # inner field shape checks
    # ------------------------------------------------------------------

    def _validate_inner_fields(self, interface_name: str, inner: dict[str, Any]) -> None:
        self._validate_mode(interface_name, inner)
        self._validate_priority(interface_name, inner)
        self._validate_intervals(interface_name, inner)
        self._validate_routes(interface_name, inner)
        self._validate_dns_servers(interface_name, inner)
        self._validate_domain_search(interface_name, inner)
        self._validate_tristate(interface_name, inner, "deprecate_prefix")
        self._validate_tristate(interface_name, inner, "remove_adv_on_exit")
        self._validate_tristate(interface_name, inner, "remove_route")

    def _validate_mode(self, interface_name: str, inner: dict[str, Any]) -> None:
        if "mode" not in inner:
            return
        mode = inner["mode"]
        if not isinstance(mode, str) or mode not in _VALID_MODES:
            self.report.add_check(
                check_name=f"radvd_{interface_name}_mode",
                passed=False,
                message=(
                    f"radvd.interfaces.{interface_name}.mode must be one of "
                    f"{sorted(_VALID_MODES)}, got {mode!r}"
                ),
                level=ValidationLevel.ERROR,
            )

    def _validate_priority(self, interface_name: str, inner: dict[str, Any]) -> None:
        if "priority" not in inner:
            return
        priority = inner["priority"]
        if not isinstance(priority, str) or priority not in _VALID_PRIORITIES:
            self.report.add_check(
                check_name=f"radvd_{interface_name}_priority",
                passed=False,
                message=(
                    f"radvd.interfaces.{interface_name}.priority must be one of "
                    f"{sorted(_VALID_PRIORITIES)}, got {priority!r}"
                ),
                level=ValidationLevel.ERROR,
            )

    def _validate_intervals(self, interface_name: str, inner: dict[str, Any]) -> None:
        min_raw = inner.get("min_interval")
        max_raw = inner.get("max_interval")
        min_int = _coerce_positive_int(min_raw) if min_raw is not None else None
        max_int = _coerce_positive_int(max_raw) if max_raw is not None else None
        if min_raw is not None and min_int is None:
            self.report.add_check(
                check_name=f"radvd_{interface_name}_min_interval",
                passed=False,
                message=(
                    f"radvd.interfaces.{interface_name}.min_interval must be a "
                    f"positive integer, got {min_raw!r}"
                ),
                level=ValidationLevel.ERROR,
            )
        if max_raw is not None and max_int is None:
            self.report.add_check(
                check_name=f"radvd_{interface_name}_max_interval",
                passed=False,
                message=(
                    f"radvd.interfaces.{interface_name}.max_interval must be a "
                    f"positive integer, got {max_raw!r}"
                ),
                level=ValidationLevel.ERROR,
            )
        if min_int is not None and max_int is not None and min_int > max_int:
            self.report.add_check(
                check_name=f"radvd_{interface_name}_interval_order",
                passed=False,
                message=(
                    f"radvd.interfaces.{interface_name}.min_interval ({min_int}) must be "
                    f"<= max_interval ({max_int})"
                ),
                level=ValidationLevel.ERROR,
            )

    def _validate_routes(self, interface_name: str, inner: dict[str, Any]) -> None:
        if "routes" not in inner:
            return
        routes = inner["routes"]
        if not isinstance(routes, list):
            self.report.add_check(
                check_name=f"radvd_{interface_name}_routes_shape",
                passed=False,
                message=(
                    f"radvd.interfaces.{interface_name}.routes must be a list, "
                    f"got {type(routes).__name__}"
                ),
                level=ValidationLevel.ERROR,
            )
            return
        for index, entry in enumerate(routes):
            if not isinstance(entry, str) or not _is_ipv6_cidr(entry):
                self.report.add_check(
                    check_name=f"radvd_{interface_name}_routes_{index}",
                    passed=False,
                    message=(
                        f"radvd.interfaces.{interface_name}.routes[{index}] must be "
                        f"a valid IPv6 CIDR, got {entry!r}"
                    ),
                    level=ValidationLevel.ERROR,
                )

    def _validate_dns_servers(self, interface_name: str, inner: dict[str, Any]) -> None:
        if "dns_servers" not in inner:
            return
        servers = inner["dns_servers"]
        if not isinstance(servers, list):
            self.report.add_check(
                check_name=f"radvd_{interface_name}_dns_servers_shape",
                passed=False,
                message=(
                    f"radvd.interfaces.{interface_name}.dns_servers must be a list, "
                    f"got {type(servers).__name__}"
                ),
                level=ValidationLevel.ERROR,
            )
            return
        for index, entry in enumerate(servers):
            if not isinstance(entry, str) or not _is_ipv6_address(entry):
                self.report.add_check(
                    check_name=f"radvd_{interface_name}_dns_servers_{index}",
                    passed=False,
                    message=(
                        f"radvd.interfaces.{interface_name}.dns_servers[{index}] must be "
                        f"a valid IPv6 address, got {entry!r}"
                    ),
                    level=ValidationLevel.ERROR,
                )

    def _validate_domain_search(self, interface_name: str, inner: dict[str, Any]) -> None:
        if "domain_search" not in inner:
            return
        domains = inner["domain_search"]
        if not isinstance(domains, list):
            self.report.add_check(
                check_name=f"radvd_{interface_name}_domain_search_shape",
                passed=False,
                message=(
                    f"radvd.interfaces.{interface_name}.domain_search must be a list, "
                    f"got {type(domains).__name__}"
                ),
                level=ValidationLevel.ERROR,
            )
            return
        for index, entry in enumerate(domains):
            if not isinstance(entry, str) or not _HOSTNAME_RE.match(entry):
                self.report.add_check(
                    check_name=f"radvd_{interface_name}_domain_search_{index}",
                    passed=False,
                    message=(
                        f"radvd.interfaces.{interface_name}.domain_search[{index}] must be "
                        f"a valid DNS domain, got {entry!r}"
                    ),
                    level=ValidationLevel.ERROR,
                )

    def _validate_tristate(
        self, interface_name: str, inner: dict[str, Any], field_name: str
    ) -> None:
        if field_name not in inner:
            return
        value = inner[field_name]
        if not isinstance(value, str) or value not in _VALID_TRISTATE:
            self.report.add_check(
                check_name=f"radvd_{interface_name}_{field_name}",
                passed=False,
                message=(
                    f"radvd.interfaces.{interface_name}.{field_name} must be one of "
                    f"{sorted(_VALID_TRISTATE)} (empty = automatic), got {value!r}"
                ),
                level=ValidationLevel.ERROR,
            )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _coerce_positive_int(value: Any) -> int | None:
    """Return ``value`` as a positive int, or ``None`` if not coercible."""
    try:
        result = int(value)
    except (TypeError, ValueError):
        return None
    if result <= 0:
        return None
    return result


def _is_ipv6_cidr(value: str) -> bool:
    """Return True if *value* parses as an IPv6 network in CIDR form."""
    try:
        network = ipaddress.ip_network(value, strict=False)
    except ValueError:
        return False
    return isinstance(network, ipaddress.IPv6Network)


def _is_ipv6_address(value: str) -> bool:
    """Return True if *value* parses as a literal IPv6 address."""
    try:
        addr = ipaddress.ip_address(value)
    except ValueError:
        return False
    return isinstance(addr, ipaddress.IPv6Address)
