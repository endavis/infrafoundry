"""Firewall-rule validation for OPNsense (ADR-0014, ADR-0015, #742).

Plan-time validation for the ``firewall_rules`` resource type. The
validator is deliberately split from the service-side
``firewall_rule_configs_from_resources`` parser: the parser raises on
hard schema violations (missing required fields, non-bool booleans,
invalid enum values), while the validator surfaces softer cross-resource
reference issues (unknown alias, unknown interface, unknown gateway,
identity-tag collision, mutex conflicts) as ``ValidationReport`` entries.

Cross-reference targets:

- ``interface``: managed ``interface_assignments`` names plus live
  ``interfacesInfo`` keys. Empty allowed when ``state_policy=floating``.
- ``gateway``: managed ``gateways`` names plus live system gateway
  names (e.g., ``WAN_DHCP``, ``WAN_DHCP6``). Mirrors the static-route
  validator's gateway-acceptance pattern. The protocol family of the
  gateway is checked against ``ipprotocol`` for compatibility.
- ``source_net`` / ``destination_net``: ``"any"``, alias name (managed
  or live), literal IP/CIDR, or ``<iface>net`` sentinel.

Identity-tag collision:

- ``description`` values that contain ``[infrafoundry:<name>]`` anywhere
  are rejected.
- A long-description warning fires when the encoded form (operator
  description + identity suffix) exceeds 200 characters; some live
  installs truncate at apply time without warning.

Mutex constraints:

- ``tcpflags_any: true`` together with non-empty ``tcpflags1`` /
  ``tcpflags2`` is an error — the OPNsense schema treats them as
  mutually exclusive at apply time.
"""

from __future__ import annotations

import ipaddress
import re
from typing import Any

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport

from ..services.firewall_rule import (
    ACTION_CHOICES,
    DIRECTION_CHOICES,
    IPPROTOCOL_CHOICES,
    STATE_POLICY_CHOICES,
    STATETYPE_CHOICES,
    encode_identity,
)

# OPNsense built-in net keywords commonly accepted in firewall rules.
# Conservative — unknown values surface as warnings (not errors) so a
# new keyword in a future minor version doesn't block a plan.
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

# Soft cap on the encoded description length (operator description +
# identity suffix tag). Some OPNsense versions silently truncate around
# this length on apply.
_DESCRIPTION_MAX_LENGTH = 200


class FirewallRuleValidator:
    """Validates OPNsense firewall-rule resources against managed + live state."""

    def __init__(self, report: ValidationReport) -> None:
        """Initialize validator.

        Args:
            report: ValidationReport to add results to.
        """
        self.report = report

    def validate(
        self,
        firewall_rules: list[ResourceConfig],
        alias_names: set[str],
        interface_assignment_names: set[str],
        gateway_names: set[str],
        existing_interfaces: dict[str, Any],
        existing_aliases: dict[str, Any],
        existing_gateways: set[str],
        managed_gateways: list[ResourceConfig] | None = None,
    ) -> None:
        """Validate firewall-rule resources.

        Args:
            firewall_rules: ``firewall_rules`` ``ResourceConfig`` entries.
            alias_names: Set of managed alias names declared in YAML.
            interface_assignment_names: Set of managed
                interface-assignment names declared in YAML.
            gateway_names: Set of managed gateway names declared in YAML.
            existing_interfaces: Live interface map.
            existing_aliases: Live alias map.
            existing_gateways: Set of live gateway names returned by
                ``searchGateway``.
            managed_gateways: ``gateways`` ``ResourceConfig`` entries —
                used to resolve the gateway's IP protocol for the
                protocol-match check.
        """
        gateway_protocols = _index_managed_gateway_protocols(managed_gateways or [])
        for rule in firewall_rules:
            self._validate_one(
                rule,
                alias_names=alias_names,
                interface_assignment_names=interface_assignment_names,
                gateway_names=gateway_names,
                existing_interfaces=existing_interfaces,
                existing_aliases=existing_aliases,
                existing_gateways=existing_gateways,
                gateway_protocols=gateway_protocols,
            )

    def _validate_one(
        self,
        rule: ResourceConfig,
        *,
        alias_names: set[str],
        interface_assignment_names: set[str],
        gateway_names: set[str],
        existing_interfaces: dict[str, Any],
        existing_aliases: dict[str, Any],
        existing_gateways: set[str],
        gateway_protocols: dict[str, str],
    ) -> None:
        """Run all checks for a single firewall-rule entry."""
        self._validate_description(rule)
        self._validate_lock(rule)
        self._validate_log(rule)
        self._validate_enabled(rule)
        self._validate_quick(rule)
        self._validate_interfacenot(rule)
        self._validate_source_not(rule)
        self._validate_destination_not(rule)
        self._validate_disablereplyto(rule)
        self._validate_tcpflags_any(rule)
        self._validate_nopfsync(rule)
        self._validate_nosync(rule)
        self._validate_allowopts(rule)
        self._validate_sequence(rule)
        self._validate_action(rule)
        self._validate_direction(rule)
        ipprotocol = self._validate_ipprotocol(rule)
        self._validate_state_policy(rule)
        self._validate_statetype(rule)
        self._validate_interface(
            rule,
            interface_assignment_names=interface_assignment_names,
            existing_interfaces=existing_interfaces,
        )
        self._validate_gateway(
            rule,
            gateway_names=gateway_names,
            existing_gateways=existing_gateways,
            gateway_protocols=gateway_protocols,
            ipprotocol=ipprotocol,
        )
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
        self._validate_tcpflags_mutex(rule)
        self._validate_int_field(rule, "max")
        self._validate_int_field(rule, "max_src_conn")
        self._validate_int_field(rule, "max_src_conn_rate")
        self._validate_int_field(rule, "max_src_conn_rates")
        self._validate_int_field(rule, "max_src_nodes")
        self._validate_int_field(rule, "max_src_states")
        self._validate_int_field(rule, "statetimeout")
        self._validate_int_field(rule, "adaptivestart")
        self._validate_int_field(rule, "adaptiveend")

    # ------------------------------------------------------------------
    # description / boolean / int helpers
    # ------------------------------------------------------------------

    def _validate_description(self, rule: ResourceConfig) -> None:
        """Reject operator-set descriptions that forge the InfraFoundry tag,
        and warn when the encoded form is too long."""
        if "description" not in rule.config:
            return
        description = rule.config["description"]
        if not isinstance(description, str):
            self.report.add_check(
                check_name=f"firewall_rule_{rule.name}_description",
                passed=False,
                message=(
                    f"firewall_rule '{rule.name}' description must be a string, "
                    f"got {type(description).__name__}"
                ),
                level=ValidationLevel.ERROR,
            )
            return
        if _IDENTITY_PROBE.search(description):
            self.report.add_check(
                check_name=f"firewall_rule_{rule.name}_description",
                passed=False,
                message=(
                    f"firewall_rule '{rule.name}' description must not contain "
                    f"'[infrafoundry:<name>]' — that tag is reserved for "
                    f"InfraFoundry's identity suffix, added automatically at apply time"
                ),
                level=ValidationLevel.ERROR,
            )
            return
        encoded = encode_identity(rule.name, description)
        if len(encoded) > _DESCRIPTION_MAX_LENGTH:
            self.report.add_check(
                check_name=f"firewall_rule_{rule.name}_description_length",
                passed=False,
                message=(
                    f"firewall_rule '{rule.name}' encoded description "
                    f"({len(encoded)} chars) exceeds the soft limit of "
                    f"{_DESCRIPTION_MAX_LENGTH}; some OPNsense versions truncate "
                    f"silently at apply time"
                ),
                level=ValidationLevel.WARNING,
            )

    def _validate_bool(self, rule: ResourceConfig, field_name: str) -> None:
        if field_name not in rule.config:
            return
        value = rule.config[field_name]
        if not isinstance(value, bool):
            self.report.add_check(
                check_name=f"firewall_rule_{rule.name}_{field_name}",
                passed=False,
                message=(
                    f"firewall_rule '{rule.name}' {field_name} must be a boolean "
                    f"(true/false), got {type(value).__name__}"
                ),
                level=ValidationLevel.ERROR,
            )

    def _validate_lock(self, rule: ResourceConfig) -> None:
        self._validate_bool(rule, "lock")

    def _validate_log(self, rule: ResourceConfig) -> None:
        self._validate_bool(rule, "log")

    def _validate_enabled(self, rule: ResourceConfig) -> None:
        self._validate_bool(rule, "enabled")

    def _validate_quick(self, rule: ResourceConfig) -> None:
        self._validate_bool(rule, "quick")

    def _validate_interfacenot(self, rule: ResourceConfig) -> None:
        self._validate_bool(rule, "interfacenot")

    def _validate_source_not(self, rule: ResourceConfig) -> None:
        self._validate_bool(rule, "source_not")

    def _validate_destination_not(self, rule: ResourceConfig) -> None:
        self._validate_bool(rule, "destination_not")

    def _validate_disablereplyto(self, rule: ResourceConfig) -> None:
        self._validate_bool(rule, "disablereplyto")

    def _validate_tcpflags_any(self, rule: ResourceConfig) -> None:
        self._validate_bool(rule, "tcpflags_any")

    def _validate_nopfsync(self, rule: ResourceConfig) -> None:
        self._validate_bool(rule, "nopfsync")

    def _validate_nosync(self, rule: ResourceConfig) -> None:
        self._validate_bool(rule, "nosync")

    def _validate_allowopts(self, rule: ResourceConfig) -> None:
        self._validate_bool(rule, "allowopts")

    def _validate_sequence(self, rule: ResourceConfig) -> None:
        if "sequence" not in rule.config:
            return
        sequence_raw = rule.config["sequence"]
        try:
            int(sequence_raw)
        except (TypeError, ValueError):
            self.report.add_check(
                check_name=f"firewall_rule_{rule.name}_sequence",
                passed=False,
                message=(
                    f"firewall_rule '{rule.name}' sequence must be an integer "
                    f"(got {sequence_raw!r})"
                ),
                level=ValidationLevel.ERROR,
            )

    def _validate_int_field(self, rule: ResourceConfig, field_name: str) -> None:
        """Validate an optional int-shaped string field.

        OPNsense accepts these as decimal strings or empty. We accept
        either an empty string (omit the field) or a value that parses
        as ``int``. Stored as strings on the dataclass for verbatim
        wire serialization, but operator YAML may use either form.
        """
        if field_name not in rule.config:
            return
        value = rule.config[field_name]
        if value in ("", None):
            return
        if isinstance(value, bool):
            # bool is a subclass of int — explicitly reject so
            # ``true``/``false`` doesn't sneak through.
            self.report.add_check(
                check_name=f"firewall_rule_{rule.name}_{field_name}",
                passed=False,
                message=(
                    f"firewall_rule '{rule.name}' {field_name} must be an integer "
                    f"or empty string, got bool"
                ),
                level=ValidationLevel.ERROR,
            )
            return
        try:
            int(value)
        except (TypeError, ValueError):
            self.report.add_check(
                check_name=f"firewall_rule_{rule.name}_{field_name}",
                passed=False,
                message=(
                    f"firewall_rule '{rule.name}' {field_name} must be an integer "
                    f"or empty string (got {value!r})"
                ),
                level=ValidationLevel.ERROR,
            )

    # ------------------------------------------------------------------
    # Enum closed-set checks
    # ------------------------------------------------------------------

    def _validate_action(self, rule: ResourceConfig) -> None:
        self._validate_enum(rule, "action", ACTION_CHOICES)

    def _validate_direction(self, rule: ResourceConfig) -> None:
        self._validate_enum(rule, "direction", DIRECTION_CHOICES)

    def _validate_ipprotocol(self, rule: ResourceConfig) -> str | None:
        """Validate ``ipprotocol`` and return the value (or None on default)."""
        if "ipprotocol" not in rule.config:
            return "inet"
        value = rule.config["ipprotocol"]
        if value not in IPPROTOCOL_CHOICES:
            self.report.add_check(
                check_name=f"firewall_rule_{rule.name}_ipprotocol",
                passed=False,
                message=(
                    f"firewall_rule '{rule.name}' ipprotocol must be one of "
                    f"{IPPROTOCOL_CHOICES}, got {value!r}"
                ),
                level=ValidationLevel.ERROR,
            )
            return None
        return str(value)

    def _validate_state_policy(self, rule: ResourceConfig) -> None:
        self._validate_enum(rule, "state_policy", STATE_POLICY_CHOICES)

    def _validate_statetype(self, rule: ResourceConfig) -> None:
        self._validate_enum(rule, "statetype", STATETYPE_CHOICES)

    def _validate_enum(
        self,
        rule: ResourceConfig,
        field_name: str,
        choices: tuple[str, ...],
    ) -> None:
        if field_name not in rule.config:
            return
        value = rule.config[field_name]
        if value not in choices:
            self.report.add_check(
                check_name=f"firewall_rule_{rule.name}_{field_name}",
                passed=False,
                message=(
                    f"firewall_rule '{rule.name}' {field_name} must be one of "
                    f"{choices}, got {value!r}"
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
        interface = rule.config.get("interface", "")
        state_policy = rule.config.get("state_policy", "")
        # Empty interface is allowed only when state_policy=floating.
        if not interface:
            if state_policy == "floating":
                return
            self.report.add_check(
                check_name=f"firewall_rule_{rule.name}_interface",
                passed=False,
                message=(
                    f"firewall_rule '{rule.name}' interface must be a non-empty string "
                    f"unless state_policy='floating'"
                ),
                level=ValidationLevel.ERROR,
            )
            return
        if not isinstance(interface, str):
            self.report.add_check(
                check_name=f"firewall_rule_{rule.name}_interface",
                passed=False,
                message=(
                    f"firewall_rule '{rule.name}' interface must be a string, "
                    f"got {type(interface).__name__}"
                ),
                level=ValidationLevel.ERROR,
            )
            return
        if interface in interface_assignment_names or interface in existing_interfaces:
            self.report.add_check(
                check_name=f"firewall_rule_{rule.name}_interface",
                passed=True,
                message=(f"Interface '{interface}' resolved for firewall_rule '{rule.name}'"),
                level=ValidationLevel.INFO,
            )
            return
        self.report.add_check(
            check_name=f"firewall_rule_{rule.name}_interface",
            passed=False,
            message=(
                f"firewall_rule '{rule.name}' references unknown interface "
                f"'{interface}'; expected a managed interface_assignment name or a "
                f"live OPNsense interface"
            ),
            level=ValidationLevel.ERROR,
        )

    # ------------------------------------------------------------------
    # gateway (with protocol-family heuristic)
    # ------------------------------------------------------------------

    def _validate_gateway(
        self,
        rule: ResourceConfig,
        *,
        gateway_names: set[str],
        existing_gateways: set[str],
        gateway_protocols: dict[str, str],
        ipprotocol: str | None,
    ) -> None:
        gateway = rule.config.get("gateway", "")
        if not gateway:
            return
        if not isinstance(gateway, str):
            self.report.add_check(
                check_name=f"firewall_rule_{rule.name}_gateway",
                passed=False,
                message=(
                    f"firewall_rule '{rule.name}' gateway must be a string, "
                    f"got {type(gateway).__name__}"
                ),
                level=ValidationLevel.ERROR,
            )
            return
        if gateway not in gateway_names and gateway not in existing_gateways:
            self.report.add_check(
                check_name=f"firewall_rule_{rule.name}_gateway",
                passed=False,
                message=(
                    f"firewall_rule '{rule.name}' references unknown gateway "
                    f"'{gateway}'; expected a managed 'gateways' resource name "
                    f"or a live OPNsense gateway"
                ),
                level=ValidationLevel.ERROR,
            )
            return
        # Protocol-family heuristic: only emit a warning (not an error)
        # — the live-gateway heuristic (trailing-6) is best-effort.
        if ipprotocol in (None, "inet46"):
            return
        gateway_protocol = gateway_protocols.get(gateway)
        if gateway_protocol is None:
            gateway_protocol = "inet6" if gateway.endswith("6") else "inet"
        if gateway_protocol != ipprotocol:
            self.report.add_check(
                check_name=f"firewall_rule_{rule.name}_gateway_protocol",
                passed=False,
                message=(
                    f"firewall_rule '{rule.name}' gateway '{gateway}' protocol "
                    f"({gateway_protocol!r}) does not match rule ipprotocol "
                    f"({ipprotocol!r})"
                ),
                level=ValidationLevel.WARNING,
            )

    # ------------------------------------------------------------------
    # net fields (source_net / destination_net)
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
                check_name=f"firewall_rule_{rule.name}_{field_name}",
                passed=False,
                message=(
                    f"firewall_rule '{rule.name}' {field_name} must be a string, "
                    f"got {type(value).__name__}"
                ),
                level=ValidationLevel.ERROR,
            )
            return
        if value == "":
            # Empty defaults to ``"any"`` in the parser; not a problem.
            return
        if value in _NET_KEYWORDS or value in alias_names or value in existing_aliases:
            return
        if _looks_like_iface_sentinel(value):
            return
        if _looks_like_ip_or_cidr(value):
            return
        self.report.add_check(
            check_name=f"firewall_rule_{rule.name}_{field_name}",
            passed=False,
            message=(
                f"firewall_rule '{rule.name}' {field_name} '{value}' did not resolve "
                f"to a managed alias, live alias, IP/CIDR, interface sentinel, or "
                f"known keyword ({sorted(_NET_KEYWORDS)})"
            ),
            level=ValidationLevel.WARNING,
        )

    # ------------------------------------------------------------------
    # tcpflags mutex
    # ------------------------------------------------------------------

    def _validate_tcpflags_mutex(self, rule: ResourceConfig) -> None:
        """``tcpflags_any: true`` is mutex with non-empty ``tcpflags1`` /
        ``tcpflags2``."""
        tcpflags_any = rule.config.get("tcpflags_any")
        if tcpflags_any is not True:
            return
        flags1 = rule.config.get("tcpflags1", "")
        flags2 = rule.config.get("tcpflags2", "")
        if flags1 or flags2:
            self.report.add_check(
                check_name=f"firewall_rule_{rule.name}_tcpflags_mutex",
                passed=False,
                message=(
                    f"firewall_rule '{rule.name}' tcpflags_any=true cannot coexist "
                    f"with non-empty tcpflags1 ({flags1!r}) / tcpflags2 ({flags2!r})"
                ),
                level=ValidationLevel.ERROR,
            )


def _looks_like_ip_or_cidr(value: str) -> bool:
    """Return True if ``value`` parses as an IP address or CIDR network."""
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


def _looks_like_iface_sentinel(value: str) -> bool:
    """Return True if ``value`` looks like ``<iface>net`` or ``<iface>ip``.

    OPNsense accepts ``lannet``, ``wannet``, ``opt1net``, etc. as
    sentinels referencing the interface's network or IP. The validator
    uses a permissive shape check rather than a closed enum so new
    interface names don't block planning.
    """
    return value.endswith("net") or value.endswith("ip") or value == "(self)"


def _index_managed_gateway_protocols(
    managed_gateways: list[ResourceConfig],
) -> dict[str, str]:
    """Build ``{gateway_name: protocol}`` from managed gateway resources."""
    result: dict[str, str] = {}
    for gateway in managed_gateways:
        if gateway.type != "routing.gateways":
            continue
        protocol = gateway.config.get("protocol")
        if isinstance(protocol, str) and protocol in ("inet", "inet6"):
            result[gateway.name] = protocol
    return result
