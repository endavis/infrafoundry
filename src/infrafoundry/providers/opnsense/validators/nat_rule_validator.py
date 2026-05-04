"""NAT-rule validation for OPNsense (ADR-0014, #713, #725).

Plan-time validation for the ``nat_rules`` resource type. The validator is
deliberately split from the service-side ``nat_rule_configs_from_resources``
parser: the parser raises on hard schema violations (wrong kind, missing
required fields), while the validator surfaces softer cross-resource
reference issues (unknown alias, unknown interface, identity-prefix
collision in operator-set ``description``) as ``ValidationReport`` entries.

Cross-reference targets:

- ``interface``: managed ``interface_assignments`` names plus live
  ``interfacesInfo`` keys.
- ``source_net`` / ``destination_net`` / ``target``: managed alias names plus
  literal IP/CIDR plus a small set of OPNsense built-in keywords.

Identity-tag collision:

- ``description`` values that contain ``[infrafoundry:<name>]`` anywhere
  are rejected. The tag is reserved for InfraFoundry's identity suffix,
  which is added automatically at apply time. The service parser also
  catches this; the validator surfaces it as a friendlier plan-time error.

Per-kind dispatch:

- The third kind (``port_forward``, #725) shares ``interface`` /
  ``description`` / ``lock`` / ``sequence`` checks with outbound and 1:1.
  Port-forward-specific fields (``pass_action``, ``poolopts``,
  ``natreflection`` with the DNat value set, plus a required ``target``)
  go through ``_validate_port_forward_required`` and the closed-set
  helpers below.
"""

from __future__ import annotations

import ipaddress
import re
from typing import Any

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport

# OPNsense built-in net/target keywords commonly accepted in NAT rules. The
# set is intentionally conservative — unknown values surface as warnings
# (not errors) so a new keyword in a future minor version doesn't block a
# plan.
_NET_KEYWORDS: frozenset[str] = frozenset(
    {
        "any",
        "lan",
        "wan",
        "wanip",
        "lanip",
        "(self)",
        "lan_subnets",
        "wan_subnets",
    }
)

_IDENTITY_PROBE = re.compile(r"\[infrafoundry:[^\]]*\]")


class NATRuleValidator:
    """Validates OPNsense NAT-rule resources against managed + live state."""

    def __init__(self, report: ValidationReport) -> None:
        """Initialize validator.

        Args:
            report: ValidationReport to add results to.
        """
        self.report = report

    def validate(
        self,
        nat_rules: list[ResourceConfig],
        alias_names: set[str],
        interface_assignment_names: set[str],
        existing_interfaces: dict[str, Any],
        existing_aliases: dict[str, Any],
    ) -> None:
        """Validate NAT-rule resources.

        Args:
            nat_rules: ``nat_rules`` ``ResourceConfig`` entries.
            alias_names: Set of managed alias names declared in YAML.
            interface_assignment_names: Set of managed interface-assignment
                names declared in YAML.
            existing_interfaces: Live interface map from
                ``OPNsenseValidator._get_existing_interfaces``.
            existing_aliases: Live alias map from
                ``OPNsenseValidator._get_existing_aliases``.
        """
        for rule in nat_rules:
            self._validate_one(
                rule,
                alias_names=alias_names,
                interface_assignment_names=interface_assignment_names,
                existing_interfaces=existing_interfaces,
                existing_aliases=existing_aliases,
            )

    def _validate_one(
        self,
        rule: ResourceConfig,
        *,
        alias_names: set[str],
        interface_assignment_names: set[str],
        existing_interfaces: dict[str, Any],
        existing_aliases: dict[str, Any],
    ) -> None:
        """Run all checks for a single NAT-rule entry."""
        kind = self._validate_kind(rule)
        self._validate_description_prefix(rule)
        self._validate_lock(rule)
        self._validate_log(rule)
        self._validate_enabled(rule)
        self._validate_sequence(rule)
        self._validate_interface(
            rule,
            interface_assignment_names=interface_assignment_names,
            existing_interfaces=existing_interfaces,
        )
        if kind == "outbound":
            self._validate_outbound_required(rule)
            self._validate_net_field(
                rule,
                "source_net",
                alias_names=alias_names,
                existing_aliases=existing_aliases,
            )
            self._validate_net_field(
                rule,
                "destination_net",
                alias_names=alias_names,
                existing_aliases=existing_aliases,
            )
            self._validate_net_field(
                rule,
                "target",
                alias_names=alias_names,
                existing_aliases=existing_aliases,
            )
        elif kind == "one_to_one":
            self._validate_one_to_one_required(rule)
            self._validate_net_field(
                rule,
                "source_net",
                alias_names=alias_names,
                existing_aliases=existing_aliases,
            )
            self._validate_net_field(
                rule,
                "destination_net",
                alias_names=alias_names,
                existing_aliases=existing_aliases,
            )
            self._validate_one_to_one_type(rule)
            self._validate_natreflection(rule, kind="one_to_one")
        elif kind == "port_forward":
            self._validate_port_forward_required(rule)
            self._validate_net_field(
                rule,
                "source_net",
                alias_names=alias_names,
                existing_aliases=existing_aliases,
            )
            self._validate_net_field(
                rule,
                "destination_net",
                alias_names=alias_names,
                existing_aliases=existing_aliases,
            )
            self._validate_net_field(
                rule,
                "target",
                alias_names=alias_names,
                existing_aliases=existing_aliases,
            )
            self._validate_pass_action(rule)
            self._validate_poolopts(rule)
            self._validate_natreflection(rule, kind="port_forward")

    # ------------------------------------------------------------------
    # kind / description / lock / sequence
    # ------------------------------------------------------------------

    def _validate_kind(self, rule: ResourceConfig) -> str | None:
        """Validate the ``kind`` discriminator. Returns the kind or None."""
        kind = rule.config.get("kind")
        if kind not in ("outbound", "one_to_one", "port_forward"):
            self.report.add_check(
                check_name=f"nat_rule_{rule.name}_kind",
                passed=False,
                message=(
                    f"nat_rule '{rule.name}' kind must be 'outbound', 'one_to_one', "
                    f"or 'port_forward', got {kind!r}"
                ),
                level=ValidationLevel.ERROR,
            )
            return None
        return str(kind)

    def _validate_description_prefix(self, rule: ResourceConfig) -> None:
        """Reject operator-set descriptions that forge the InfraFoundry prefix."""
        if "description" not in rule.config:
            return
        description = rule.config["description"]
        if not isinstance(description, str):
            self.report.add_check(
                check_name=f"nat_rule_{rule.name}_description",
                passed=False,
                message=(
                    f"nat_rule '{rule.name}' description must be a string, "
                    f"got {type(description).__name__}"
                ),
                level=ValidationLevel.ERROR,
            )
            return
        if _IDENTITY_PROBE.search(description):
            self.report.add_check(
                check_name=f"nat_rule_{rule.name}_description",
                passed=False,
                message=(
                    f"nat_rule '{rule.name}' description must not contain "
                    f"'[infrafoundry:<name>]' — that tag is reserved for InfraFoundry's "
                    f"identity suffix, added automatically at apply time"
                ),
                level=ValidationLevel.ERROR,
            )

    def _validate_lock(self, rule: ResourceConfig) -> None:
        if "lock" not in rule.config:
            return
        lock = rule.config["lock"]
        if not isinstance(lock, bool):
            self.report.add_check(
                check_name=f"nat_rule_{rule.name}_lock",
                passed=False,
                message=(
                    f"nat_rule '{rule.name}' lock must be a boolean (true/false), "
                    f"got {type(lock).__name__}"
                ),
                level=ValidationLevel.ERROR,
            )

    def _validate_log(self, rule: ResourceConfig) -> None:
        if "log" not in rule.config:
            return
        log = rule.config["log"]
        if not isinstance(log, bool):
            self.report.add_check(
                check_name=f"nat_rule_{rule.name}_log",
                passed=False,
                message=(
                    f"nat_rule '{rule.name}' log must be a boolean (true/false), "
                    f"got {type(log).__name__}"
                ),
                level=ValidationLevel.ERROR,
            )

    def _validate_enabled(self, rule: ResourceConfig) -> None:
        if "enabled" not in rule.config:
            return
        enabled = rule.config["enabled"]
        if not isinstance(enabled, bool):
            self.report.add_check(
                check_name=f"nat_rule_{rule.name}_enabled",
                passed=False,
                message=(
                    f"nat_rule '{rule.name}' enabled must be a boolean (true/false), "
                    f"got {type(enabled).__name__}"
                ),
                level=ValidationLevel.ERROR,
            )

    def _validate_sequence(self, rule: ResourceConfig) -> None:
        if "sequence" not in rule.config:
            return
        sequence_raw = rule.config["sequence"]
        try:
            int(sequence_raw)
        except (TypeError, ValueError):
            self.report.add_check(
                check_name=f"nat_rule_{rule.name}_sequence",
                passed=False,
                message=(
                    f"nat_rule '{rule.name}' sequence must be an integer (got {sequence_raw!r})"
                ),
                level=ValidationLevel.ERROR,
            )

    # ------------------------------------------------------------------
    # interface
    # ------------------------------------------------------------------

    def _validate_interface(
        self,
        rule: ResourceConfig,
        *,
        interface_assignment_names: set[str],
        existing_interfaces: dict[str, Any],
    ) -> None:
        interface = rule.config.get("interface")
        if interface is None:
            # Per-kind required-field check below will catch this.
            return
        if not isinstance(interface, str) or not interface:
            self.report.add_check(
                check_name=f"nat_rule_{rule.name}_interface",
                passed=False,
                message=(f"nat_rule '{rule.name}' interface must be a non-empty string"),
                level=ValidationLevel.ERROR,
            )
            return
        if interface in interface_assignment_names or interface in existing_interfaces:
            self.report.add_check(
                check_name=f"nat_rule_{rule.name}_interface",
                passed=True,
                message=(f"Interface '{interface}' resolved for nat_rule '{rule.name}'"),
                level=ValidationLevel.INFO,
            )
            return
        self.report.add_check(
            check_name=f"nat_rule_{rule.name}_interface",
            passed=False,
            message=(
                f"nat_rule '{rule.name}' references unknown interface '{interface}'; "
                f"expected a managed interface_assignment name or a live OPNsense interface"
            ),
            level=ValidationLevel.ERROR,
        )

    # ------------------------------------------------------------------
    # net fields (source_net / destination_net / target)
    # ------------------------------------------------------------------

    def _validate_net_field(
        self,
        rule: ResourceConfig,
        field_name: str,
        *,
        alias_names: set[str],
        existing_aliases: dict[str, Any],
    ) -> None:
        if field_name not in rule.config:
            return
        value = rule.config[field_name]
        if not isinstance(value, str):
            self.report.add_check(
                check_name=f"nat_rule_{rule.name}_{field_name}",
                passed=False,
                message=(
                    f"nat_rule '{rule.name}' {field_name} must be a string, "
                    f"got {type(value).__name__}"
                ),
                level=ValidationLevel.ERROR,
            )
            return
        if value == "":
            # Empty is allowed for optional fields; the per-kind required
            # check elsewhere catches mandatory fields with no value.
            return
        if value in _NET_KEYWORDS or value in alias_names or value in existing_aliases:
            return
        if _looks_like_ip_or_cidr(value):
            return
        # Soft warning — new OPNsense versions may add keywords; don't
        # block a plan on an unknown one.
        self.report.add_check(
            check_name=f"nat_rule_{rule.name}_{field_name}",
            passed=False,
            message=(
                f"nat_rule '{rule.name}' {field_name} '{value}' did not resolve to a "
                f"managed alias, live alias, IP/CIDR, or known keyword "
                f"({sorted(_NET_KEYWORDS)})"
            ),
            level=ValidationLevel.WARNING,
        )

    # ------------------------------------------------------------------
    # Per-kind required-field checks
    # ------------------------------------------------------------------

    def _validate_outbound_required(self, rule: ResourceConfig) -> None:
        """Outbound rules require ``interface`` and ``target`` (non-empty)."""
        for field_name in ("interface", "target"):
            value = rule.config.get(field_name)
            if not isinstance(value, str) or not value:
                self.report.add_check(
                    check_name=f"nat_rule_{rule.name}_{field_name}",
                    passed=False,
                    message=(
                        f"nat_rule '{rule.name}' (outbound) requires non-empty "
                        f"string '{field_name}'"
                    ),
                    level=ValidationLevel.ERROR,
                )

    def _validate_one_to_one_required(self, rule: ResourceConfig) -> None:
        """1:1 rules require ``interface`` and ``external``."""
        for field_name in ("interface", "external"):
            value = rule.config.get(field_name)
            if not isinstance(value, str) or not value:
                self.report.add_check(
                    check_name=f"nat_rule_{rule.name}_{field_name}",
                    passed=False,
                    message=(
                        f"nat_rule '{rule.name}' (one_to_one) requires non-empty "
                        f"string '{field_name}'"
                    ),
                    level=ValidationLevel.ERROR,
                )

    def _validate_one_to_one_type(self, rule: ResourceConfig) -> None:
        if "type" not in rule.config:
            return
        type_value = rule.config["type"]
        if type_value not in ("binat", "nat"):
            self.report.add_check(
                check_name=f"nat_rule_{rule.name}_type",
                passed=False,
                message=(
                    f"nat_rule '{rule.name}' (one_to_one) type must be "
                    f"'binat' or 'nat', got {type_value!r}"
                ),
                level=ValidationLevel.ERROR,
            )

    def _validate_natreflection(self, rule: ResourceConfig, *, kind: str) -> None:
        """Validate ``natreflection`` for the given kind.

        The 1:1 model (``OneToOne.xml``) accepts ``""`` / ``"enable"`` /
        ``"disable"``; the DNat model (port_forward) accepts ``""`` /
        ``"purenat"`` / ``"disable"``. Different keyword sets, dispatched
        by ``kind``.
        """
        if "natreflection" not in rule.config:
            return
        nat_reflect = rule.config["natreflection"]
        if kind == "port_forward":
            allowed: tuple[str, ...] = ("", "purenat", "disable")
            label = "'', 'purenat', or 'disable' (port_forward / DNat)"
        else:
            allowed = ("", "enable", "disable")
            label = "'', 'enable', or 'disable'"
        if nat_reflect not in allowed:
            self.report.add_check(
                check_name=f"nat_rule_{rule.name}_natreflection",
                passed=False,
                message=(
                    f"nat_rule '{rule.name}' natreflection must be {label}, got {nat_reflect!r}"
                ),
                level=ValidationLevel.ERROR,
            )

    # ------------------------------------------------------------------
    # Port-forward-specific validation (#725)
    # ------------------------------------------------------------------

    def _validate_port_forward_required(self, rule: ResourceConfig) -> None:
        """Port-forward rules require ``interface`` and ``target`` (non-empty).

        ``target`` here is the redirect destination (IP / alias / ``"wanip"``);
        same wire field as outbound's source-NAT translation target but
        different operator-facing semantics. See the ``NATRuleConfig``
        docstring for the dual-semantic note.
        """
        for field_name in ("interface", "target"):
            value = rule.config.get(field_name)
            if not isinstance(value, str) or not value:
                self.report.add_check(
                    check_name=f"nat_rule_{rule.name}_{field_name}",
                    passed=False,
                    message=(
                        f"nat_rule '{rule.name}' (port_forward) requires non-empty "
                        f"string '{field_name}'"
                    ),
                    level=ValidationLevel.ERROR,
                )

    def _validate_pass_action(self, rule: ResourceConfig) -> None:
        """Closed set ``"" / "pass" / "rule"``.

        **Operator caveat:** ``pass_action: "pass"`` injects an implicit
        OPNsense filter rule that bypasses any companion ``firewall_rules``
        declaration. The default is ``""`` (manual — operator declares
        the companion firewall rule themselves).
        """
        if "pass_action" not in rule.config:
            return
        value = rule.config["pass_action"]
        if value not in ("", "pass", "rule"):
            self.report.add_check(
                check_name=f"nat_rule_{rule.name}_pass_action",
                passed=False,
                message=(
                    f"nat_rule '{rule.name}' (port_forward) pass_action must be "
                    f"'', 'pass', or 'rule', got {value!r}"
                ),
                level=ValidationLevel.ERROR,
            )

    def _validate_poolopts(self, rule: ResourceConfig) -> None:
        """Closed set including blank — pool-selection algorithm.

        Mirrors the DNat XML model's ``poolopts`` enumerator.
        """
        if "poolopts" not in rule.config:
            return
        value = rule.config["poolopts"]
        allowed = (
            "",
            "round-robin",
            "round-robin sticky-address",
            "random",
            "random sticky-address",
            "source-hash",
            "bitmask",
        )
        if value not in allowed:
            self.report.add_check(
                check_name=f"nat_rule_{rule.name}_poolopts",
                passed=False,
                message=(
                    f"nat_rule '{rule.name}' (port_forward) poolopts must be one of "
                    f"{allowed!r}, got {value!r}"
                ),
                level=ValidationLevel.ERROR,
            )


def _looks_like_ip_or_cidr(value: str) -> bool:
    """Return True if ``value`` parses as an IP address or CIDR network.

    Handles both v4 and v6, both single-address and CIDR forms. ``strict=False``
    on ``ip_network`` accepts host bits being set in the address portion of a
    CIDR (e.g., ``10.0.0.5/24``), matching what operators commonly write.
    """
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        pass
    try:
        ipaddress.ip_network(value, strict=False)
        return True
    except ValueError:
        return False
