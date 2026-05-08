"""Unit tests for ``FirewallRuleValidator``.

Coverage:
    - ``interface``: managed interface-assignments + live overview keys;
      empty allowed when ``state_policy=floating``.
    - ``gateway``: managed ``gateways`` + live system gateways;
      protocol-family heuristic (warning for v4 rule + v6 gateway).
    - ``source_net`` / ``destination_net``: keywords, alias names
      (managed + live), literal IP/CIDR, interface sentinels, unknown
      values warn.
    - Closed-set enums: ``action``, ``direction``, ``ipprotocol``,
      ``state_policy``, ``statetype``.
    - Bool typing on the documented bool fields.
    - Int typing on ``sequence``, ``max``, ``max_src_*``, etc.
    - Description identity-tag forging rejected.
    - Mutex: ``tcpflags_any=true`` + non-empty ``tcpflags1`` /
      ``tcpflags2`` rejected.
"""

from __future__ import annotations

from typing import Any

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.opnsense.validators.firewall_rule_validator import (
    FirewallRuleValidator,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _rule(name: str, **overrides: Any) -> ResourceConfig:
    config: dict[str, Any] = {
        "interface": "lan",
    }
    config.update(overrides)
    return ResourceConfig(name=name, type="firewall.rules", provider="opnsense", config=config)


def _gw(name: str, *, protocol: str = "inet") -> ResourceConfig:
    return ResourceConfig(
        name=name,
        type="routing.gateways",
        provider="opnsense",
        config={"interface": "wan", "protocol": protocol, "gateway": "192.0.2.1"},
    )


@pytest.fixture
def report() -> ValidationReport:
    return ValidationReport()


@pytest.fixture
def validator(report: ValidationReport) -> FirewallRuleValidator:
    return FirewallRuleValidator(report)


def _failures(report: ValidationReport, check_name: str) -> list[Any]:
    return [c for c in report.results if c.check_name == check_name and not c.passed]


def _warnings(report: ValidationReport, check_name: str) -> list[Any]:
    return [
        c
        for c in report.results
        if c.check_name == check_name and c.level == ValidationLevel.WARNING
    ]


# ---------------------------------------------------------------------------
# interface
# ---------------------------------------------------------------------------


class TestInterface:
    def test_managed_interface_assignment_resolves(
        self, validator: FirewallRuleValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_rule("ok", interface="lan")],
            alias_names=set(),
            interface_assignment_names={"lan"},
            gateway_names=set(),
            existing_interfaces={},
            existing_aliases={},
            existing_gateways=set(),
        )
        assert not _failures(report, "firewall_rule_ok_interface")

    def test_live_interface_resolves(
        self, validator: FirewallRuleValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_rule("ok", interface="wan")],
            alias_names=set(),
            interface_assignment_names=set(),
            gateway_names=set(),
            existing_interfaces={"wan": {}},
            existing_aliases={},
            existing_gateways=set(),
        )
        assert not _failures(report, "firewall_rule_ok_interface")

    def test_unknown_interface_fails(
        self, validator: FirewallRuleValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_rule("bad", interface="bogus")],
            alias_names=set(),
            interface_assignment_names=set(),
            gateway_names=set(),
            existing_interfaces={"wan": {}},
            existing_aliases={},
            existing_gateways=set(),
        )
        assert _failures(report, "firewall_rule_bad_interface")

    def test_empty_interface_fails_without_floating(
        self, validator: FirewallRuleValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_rule("bad", interface="")],
            alias_names=set(),
            interface_assignment_names=set(),
            gateway_names=set(),
            existing_interfaces={"wan": {}},
            existing_aliases={},
            existing_gateways=set(),
        )
        assert _failures(report, "firewall_rule_bad_interface")

    def test_empty_interface_allowed_with_floating(
        self, validator: FirewallRuleValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_rule("ok", interface="", state_policy="floating")],
            alias_names=set(),
            interface_assignment_names=set(),
            gateway_names=set(),
            existing_interfaces={"wan": {}},
            existing_aliases={},
            existing_gateways=set(),
        )
        assert not _failures(report, "firewall_rule_ok_interface")

    def test_non_string_interface_fails(
        self, validator: FirewallRuleValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_rule("bad", interface=42)],
            alias_names=set(),
            interface_assignment_names=set(),
            gateway_names=set(),
            existing_interfaces={"wan": {}},
            existing_aliases={},
            existing_gateways=set(),
        )
        assert _failures(report, "firewall_rule_bad_interface")


# ---------------------------------------------------------------------------
# gateway (cross-ref + protocol heuristic)
# ---------------------------------------------------------------------------


class TestGateway:
    def test_empty_gateway_passes_silently(
        self, validator: FirewallRuleValidator, report: ValidationReport
    ) -> None:
        # Empty gateway is the default (no policy-based routing) and
        # must not trigger any check at all.
        validator.validate(
            [_rule("ok")],
            alias_names=set(),
            interface_assignment_names=set(),
            gateway_names=set(),
            existing_interfaces={"lan": {}},
            existing_aliases={},
            existing_gateways=set(),
        )
        assert not _failures(report, "firewall_rule_ok_gateway")

    def test_managed_gateway_ref_accepted(
        self, validator: FirewallRuleValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_rule("ok", gateway="my-wan")],
            alias_names=set(),
            interface_assignment_names=set(),
            gateway_names={"my-wan"},
            existing_interfaces={"lan": {}},
            existing_aliases={},
            existing_gateways=set(),
        )
        assert not _failures(report, "firewall_rule_ok_gateway")

    def test_live_system_gateway_accepted(
        self, validator: FirewallRuleValidator, report: ValidationReport
    ) -> None:
        # ``WAN_DHCP`` exists live but isn't declared as a managed gateway.
        validator.validate(
            [_rule("ok", gateway="WAN_DHCP")],
            alias_names=set(),
            interface_assignment_names=set(),
            gateway_names=set(),
            existing_interfaces={"lan": {}},
            existing_aliases={},
            existing_gateways={"WAN_DHCP"},
        )
        assert not _failures(report, "firewall_rule_ok_gateway")

    def test_unknown_gateway_fails(
        self, validator: FirewallRuleValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_rule("bad", gateway="bogus-gw")],
            alias_names=set(),
            interface_assignment_names=set(),
            gateway_names={"my-wan"},
            existing_interfaces={"lan": {}},
            existing_aliases={},
            existing_gateways={"WAN_DHCP"},
        )
        assert _failures(report, "firewall_rule_bad_gateway")

    def test_non_string_gateway_fails(
        self, validator: FirewallRuleValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_rule("bad", gateway=42)],
            alias_names=set(),
            interface_assignment_names=set(),
            gateway_names=set(),
            existing_interfaces={"lan": {}},
            existing_aliases={},
            existing_gateways=set(),
        )
        assert _failures(report, "firewall_rule_bad_gateway")

    def test_protocol_mismatch_v4_rule_v6_managed_gateway_warns(
        self, validator: FirewallRuleValidator, report: ValidationReport
    ) -> None:
        # ipprotocol=inet (default) + managed gateway with protocol=inet6
        # is a soft warning, not an error.
        validator.validate(
            [_rule("ok", gateway="my-wan6")],
            alias_names=set(),
            interface_assignment_names=set(),
            gateway_names={"my-wan6"},
            existing_interfaces={"lan": {}},
            existing_aliases={},
            existing_gateways=set(),
            managed_gateways=[_gw("my-wan6", protocol="inet6")],
        )
        assert _warnings(report, "firewall_rule_ok_gateway_protocol")

    def test_protocol_match_v4_rule_v4_managed_gateway_no_warning(
        self, validator: FirewallRuleValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_rule("ok", gateway="my-wan", ipprotocol="inet")],
            alias_names=set(),
            interface_assignment_names=set(),
            gateway_names={"my-wan"},
            existing_interfaces={"lan": {}},
            existing_aliases={},
            existing_gateways=set(),
            managed_gateways=[_gw("my-wan", protocol="inet")],
        )
        assert not _warnings(report, "firewall_rule_ok_gateway_protocol")

    def test_protocol_inet46_disables_heuristic(
        self, validator: FirewallRuleValidator, report: ValidationReport
    ) -> None:
        # ``inet46`` must short-circuit the protocol-match heuristic
        # (rule applies to both families, so v6 gateway is fine).
        validator.validate(
            [_rule("ok", gateway="my-wan6", ipprotocol="inet46")],
            alias_names=set(),
            interface_assignment_names=set(),
            gateway_names={"my-wan6"},
            existing_interfaces={"lan": {}},
            existing_aliases={},
            existing_gateways=set(),
            managed_gateways=[_gw("my-wan6", protocol="inet6")],
        )
        assert not _warnings(report, "firewall_rule_ok_gateway_protocol")

    def test_protocol_heuristic_uses_trailing_6_for_live_gateway(
        self, validator: FirewallRuleValidator, report: ValidationReport
    ) -> None:
        # For live-only gateways, the heuristic falls back to ``endswith("6")``.
        # ipprotocol=inet + ``WAN_DHCP6`` should warn.
        validator.validate(
            [_rule("ok", gateway="WAN_DHCP6", ipprotocol="inet")],
            alias_names=set(),
            interface_assignment_names=set(),
            gateway_names=set(),
            existing_interfaces={"lan": {}},
            existing_aliases={},
            existing_gateways={"WAN_DHCP6"},
        )
        assert _warnings(report, "firewall_rule_ok_gateway_protocol")


# ---------------------------------------------------------------------------
# Description identity-tag collision
# ---------------------------------------------------------------------------


class TestDescriptionIdentityTag:
    def test_operator_set_identity_tag_rejected(
        self, validator: FirewallRuleValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_rule("evil", description="forged [infrafoundry:other]")],
            alias_names=set(),
            interface_assignment_names=set(),
            gateway_names=set(),
            existing_interfaces={"lan": {}},
            existing_aliases={},
            existing_gateways=set(),
        )
        assert _failures(report, "firewall_rule_evil_description")

    def test_normal_description_passes(
        self, validator: FirewallRuleValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_rule("ok", description="LAN allow rule")],
            alias_names=set(),
            interface_assignment_names=set(),
            gateway_names=set(),
            existing_interfaces={"lan": {}},
            existing_aliases={},
            existing_gateways=set(),
        )
        assert not _failures(report, "firewall_rule_ok_description")

    def test_non_string_description_rejected(
        self, validator: FirewallRuleValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_rule("bad", description=123)],
            alias_names=set(),
            interface_assignment_names=set(),
            gateway_names=set(),
            existing_interfaces={"lan": {}},
            existing_aliases={},
            existing_gateways=set(),
        )
        assert _failures(report, "firewall_rule_bad_description")


# ---------------------------------------------------------------------------
# net references
# ---------------------------------------------------------------------------


class TestNetReferences:
    def test_keyword_resolves_silently(
        self, validator: FirewallRuleValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_rule("ok", source_net="any", destination_net="any")],
            alias_names=set(),
            interface_assignment_names=set(),
            gateway_names=set(),
            existing_interfaces={"lan": {}},
            existing_aliases={},
            existing_gateways=set(),
        )
        assert not _failures(report, "firewall_rule_ok_source_net")
        assert not _failures(report, "firewall_rule_ok_destination_net")

    def test_managed_alias_resolves(
        self, validator: FirewallRuleValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_rule("ok", source_net="lan_subnets")],
            alias_names={"lan_subnets"},
            interface_assignment_names=set(),
            gateway_names=set(),
            existing_interfaces={"lan": {}},
            existing_aliases={},
            existing_gateways=set(),
        )
        assert not _failures(report, "firewall_rule_ok_source_net")

    def test_live_alias_resolves(
        self, validator: FirewallRuleValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_rule("ok", source_net="existing_alias")],
            alias_names=set(),
            interface_assignment_names=set(),
            gateway_names=set(),
            existing_interfaces={"lan": {}},
            existing_aliases={"existing_alias": {"name": "existing_alias"}},
            existing_gateways=set(),
        )
        assert not _failures(report, "firewall_rule_ok_source_net")

    def test_literal_ipv4_resolves(
        self, validator: FirewallRuleValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_rule("ok", source_net="10.0.0.1")],
            alias_names=set(),
            interface_assignment_names=set(),
            gateway_names=set(),
            existing_interfaces={"lan": {}},
            existing_aliases={},
            existing_gateways=set(),
        )
        assert not _failures(report, "firewall_rule_ok_source_net")

    def test_literal_cidr_resolves(
        self, validator: FirewallRuleValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_rule("ok", destination_net="10.0.0.0/24")],
            alias_names=set(),
            interface_assignment_names=set(),
            gateway_names=set(),
            existing_interfaces={"lan": {}},
            existing_aliases={},
            existing_gateways=set(),
        )
        assert not _failures(report, "firewall_rule_ok_destination_net")

    def test_literal_ipv6_resolves(
        self, validator: FirewallRuleValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_rule("ok", source_net="fd00::1")],
            alias_names=set(),
            interface_assignment_names=set(),
            gateway_names=set(),
            existing_interfaces={"lan": {}},
            existing_aliases={},
            existing_gateways=set(),
        )
        assert not _failures(report, "firewall_rule_ok_source_net")

    def test_iface_sentinel_resolves(
        self, validator: FirewallRuleValidator, report: ValidationReport
    ) -> None:
        # ``lannet`` / ``wanip`` / ``(self)`` are accepted as interface
        # sentinels via shape check.
        for value in ("lannet", "opt1net", "(self)"):
            sub_report = ValidationReport()
            sub_validator = FirewallRuleValidator(sub_report)
            sub_validator.validate(
                [_rule("ok", source_net=value)],
                alias_names=set(),
                interface_assignment_names=set(),
                gateway_names=set(),
                existing_interfaces={"lan": {}},
                existing_aliases={},
                existing_gateways=set(),
            )
            assert not _failures(sub_report, "firewall_rule_ok_source_net")

    def test_unknown_net_value_warns(
        self, validator: FirewallRuleValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_rule("ok", source_net="bogus_value")],
            alias_names=set(),
            interface_assignment_names=set(),
            gateway_names=set(),
            existing_interfaces={"lan": {}},
            existing_aliases={},
            existing_gateways=set(),
        )
        # Soft warning — not an ERROR.
        assert _warnings(report, "firewall_rule_ok_source_net")

    def test_empty_net_passes_silently(
        self, validator: FirewallRuleValidator, report: ValidationReport
    ) -> None:
        # Empty string defaults to ``"any"`` in the parser; the validator
        # must not flag it as an error.
        validator.validate(
            [_rule("ok", source_net="")],
            alias_names=set(),
            interface_assignment_names=set(),
            gateway_names=set(),
            existing_interfaces={"lan": {}},
            existing_aliases={},
            existing_gateways=set(),
        )
        assert not _failures(report, "firewall_rule_ok_source_net")

    def test_non_string_net_fails(
        self, validator: FirewallRuleValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_rule("bad", source_net=42)],
            alias_names=set(),
            interface_assignment_names=set(),
            gateway_names=set(),
            existing_interfaces={"lan": {}},
            existing_aliases={},
            existing_gateways=set(),
        )
        assert _failures(report, "firewall_rule_bad_source_net")


# ---------------------------------------------------------------------------
# Closed-set enums
# ---------------------------------------------------------------------------


class TestEnumChecks:
    def test_invalid_action_fails(
        self, validator: FirewallRuleValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_rule("bad", action="drop")],
            alias_names=set(),
            interface_assignment_names=set(),
            gateway_names=set(),
            existing_interfaces={"lan": {}},
            existing_aliases={},
            existing_gateways=set(),
        )
        assert _failures(report, "firewall_rule_bad_action")

    def test_valid_actions_pass(
        self, validator: FirewallRuleValidator, report: ValidationReport
    ) -> None:
        for value in ("pass", "block", "reject"):
            sub_report = ValidationReport()
            sub_validator = FirewallRuleValidator(sub_report)
            sub_validator.validate(
                [_rule("ok", action=value)],
                alias_names=set(),
                interface_assignment_names=set(),
                gateway_names=set(),
                existing_interfaces={"lan": {}},
                existing_aliases={},
                existing_gateways=set(),
            )
            assert not _failures(sub_report, "firewall_rule_ok_action")

    def test_invalid_direction_fails(
        self, validator: FirewallRuleValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_rule("bad", direction="diagonal")],
            alias_names=set(),
            interface_assignment_names=set(),
            gateway_names=set(),
            existing_interfaces={"lan": {}},
            existing_aliases={},
            existing_gateways=set(),
        )
        assert _failures(report, "firewall_rule_bad_direction")

    def test_valid_directions_pass(
        self, validator: FirewallRuleValidator, report: ValidationReport
    ) -> None:
        for value in ("in", "out", "any"):
            sub_report = ValidationReport()
            sub_validator = FirewallRuleValidator(sub_report)
            sub_validator.validate(
                [_rule("ok", direction=value)],
                alias_names=set(),
                interface_assignment_names=set(),
                gateway_names=set(),
                existing_interfaces={"lan": {}},
                existing_aliases={},
                existing_gateways=set(),
            )
            assert not _failures(sub_report, "firewall_rule_ok_direction")

    def test_invalid_ipprotocol_fails(
        self, validator: FirewallRuleValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_rule("bad", ipprotocol="ipv7")],
            alias_names=set(),
            interface_assignment_names=set(),
            gateway_names=set(),
            existing_interfaces={"lan": {}},
            existing_aliases={},
            existing_gateways=set(),
        )
        assert _failures(report, "firewall_rule_bad_ipprotocol")

    def test_valid_ipprotocols_pass(
        self, validator: FirewallRuleValidator, report: ValidationReport
    ) -> None:
        for value in ("inet", "inet6", "inet46"):
            sub_report = ValidationReport()
            sub_validator = FirewallRuleValidator(sub_report)
            sub_validator.validate(
                [_rule("ok", ipprotocol=value)],
                alias_names=set(),
                interface_assignment_names=set(),
                gateway_names=set(),
                existing_interfaces={"lan": {}},
                existing_aliases={},
                existing_gateways=set(),
            )
            assert not _failures(sub_report, "firewall_rule_ok_ipprotocol")

    def test_invalid_state_policy_fails(
        self, validator: FirewallRuleValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_rule("bad", state_policy="freestyle")],
            alias_names=set(),
            interface_assignment_names=set(),
            gateway_names=set(),
            existing_interfaces={"lan": {}},
            existing_aliases={},
            existing_gateways=set(),
        )
        assert _failures(report, "firewall_rule_bad_state_policy")

    def test_valid_state_policies_pass(
        self, validator: FirewallRuleValidator, report: ValidationReport
    ) -> None:
        for value in ("", "default", "if-bound", "floating"):
            sub_report = ValidationReport()
            sub_validator = FirewallRuleValidator(sub_report)
            sub_validator.validate(
                [_rule("ok", state_policy=value)],
                alias_names=set(),
                interface_assignment_names=set(),
                gateway_names=set(),
                existing_interfaces={"lan": {}},
                existing_aliases={},
                existing_gateways=set(),
            )
            assert not _failures(sub_report, "firewall_rule_ok_state_policy")

    def test_invalid_statetype_fails(
        self, validator: FirewallRuleValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_rule("bad", statetype="frozen")],
            alias_names=set(),
            interface_assignment_names=set(),
            gateway_names=set(),
            existing_interfaces={"lan": {}},
            existing_aliases={},
            existing_gateways=set(),
        )
        assert _failures(report, "firewall_rule_bad_statetype")

    def test_valid_statetypes_pass(
        self, validator: FirewallRuleValidator, report: ValidationReport
    ) -> None:
        for value in ("", "keep state", "sloppy state", "modulate state", "synproxy state", "none"):
            sub_report = ValidationReport()
            sub_validator = FirewallRuleValidator(sub_report)
            sub_validator.validate(
                [_rule("ok", statetype=value)],
                alias_names=set(),
                interface_assignment_names=set(),
                gateway_names=set(),
                existing_interfaces={"lan": {}},
                existing_aliases={},
                existing_gateways=set(),
            )
            assert not _failures(sub_report, "firewall_rule_ok_statetype")


# ---------------------------------------------------------------------------
# Bool typing
# ---------------------------------------------------------------------------


class TestBoolTypeChecks:
    @pytest.mark.parametrize(
        "field_name",
        [
            "lock",
            "log",
            "enabled",
            "quick",
            "interfacenot",
            "source_not",
            "destination_not",
            "disablereplyto",
            "tcpflags_any",
            "nopfsync",
            "nosync",
            "allowopts",
        ],
    )
    def test_field_must_be_bool(self, field_name: str) -> None:
        local_report = ValidationReport()
        local_validator = FirewallRuleValidator(local_report)
        local_validator.validate(
            [_rule("bad", **{field_name: "yes"})],
            alias_names=set(),
            interface_assignment_names=set(),
            gateway_names=set(),
            existing_interfaces={"lan": {}},
            existing_aliases={},
            existing_gateways=set(),
        )
        assert _failures(local_report, f"firewall_rule_bad_{field_name}")


# ---------------------------------------------------------------------------
# Int typing (sequence + max_*)
# ---------------------------------------------------------------------------


class TestIntTypeChecks:
    def test_sequence_must_be_int(
        self, validator: FirewallRuleValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_rule("bad", sequence="not-int")],
            alias_names=set(),
            interface_assignment_names=set(),
            gateway_names=set(),
            existing_interfaces={"lan": {}},
            existing_aliases={},
            existing_gateways=set(),
        )
        assert _failures(report, "firewall_rule_bad_sequence")

    def test_sequence_int_passes(
        self, validator: FirewallRuleValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_rule("ok", sequence=200)],
            alias_names=set(),
            interface_assignment_names=set(),
            gateway_names=set(),
            existing_interfaces={"lan": {}},
            existing_aliases={},
            existing_gateways=set(),
        )
        assert not _failures(report, "firewall_rule_ok_sequence")

    @pytest.mark.parametrize(
        "field_name",
        [
            "max",
            "max_src_conn",
            "max_src_conn_rate",
            "max_src_conn_rates",
            "max_src_nodes",
            "max_src_states",
            "statetimeout",
            "adaptivestart",
            "adaptiveend",
        ],
    )
    def test_int_field_must_be_int_or_empty(self, field_name: str) -> None:
        local_report = ValidationReport()
        local_validator = FirewallRuleValidator(local_report)
        local_validator.validate(
            [_rule("bad", **{field_name: "not-an-int"})],
            alias_names=set(),
            interface_assignment_names=set(),
            gateway_names=set(),
            existing_interfaces={"lan": {}},
            existing_aliases={},
            existing_gateways=set(),
        )
        assert _failures(local_report, f"firewall_rule_bad_{field_name}")

    def test_int_field_empty_string_passes(
        self, validator: FirewallRuleValidator, report: ValidationReport
    ) -> None:
        # Empty is the operator's way to say "omit"; must not error.
        validator.validate(
            [_rule("ok", max="", max_src_conn="")],
            alias_names=set(),
            interface_assignment_names=set(),
            gateway_names=set(),
            existing_interfaces={"lan": {}},
            existing_aliases={},
            existing_gateways=set(),
        )
        assert not _failures(report, "firewall_rule_ok_max")
        assert not _failures(report, "firewall_rule_ok_max_src_conn")

    def test_int_field_bool_rejected(
        self, validator: FirewallRuleValidator, report: ValidationReport
    ) -> None:
        # ``bool`` is a subclass of ``int`` in Python — the validator
        # must explicitly reject it.
        validator.validate(
            [_rule("bad", max_src_conn=True)],
            alias_names=set(),
            interface_assignment_names=set(),
            gateway_names=set(),
            existing_interfaces={"lan": {}},
            existing_aliases={},
            existing_gateways=set(),
        )
        assert _failures(report, "firewall_rule_bad_max_src_conn")

    def test_int_field_string_int_passes(
        self, validator: FirewallRuleValidator, report: ValidationReport
    ) -> None:
        # OPNsense accepts decimal strings; the validator does too.
        validator.validate(
            [_rule("ok", max_src_conn="100")],
            alias_names=set(),
            interface_assignment_names=set(),
            gateway_names=set(),
            existing_interfaces={"lan": {}},
            existing_aliases={},
            existing_gateways=set(),
        )
        assert not _failures(report, "firewall_rule_ok_max_src_conn")


# ---------------------------------------------------------------------------
# tcpflags mutex
# ---------------------------------------------------------------------------


class TestTcpFlagsMutex:
    def test_tcpflags_any_with_tcpflags1_fails(
        self, validator: FirewallRuleValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_rule("bad", tcpflags_any=True, tcpflags1="syn")],
            alias_names=set(),
            interface_assignment_names=set(),
            gateway_names=set(),
            existing_interfaces={"lan": {}},
            existing_aliases={},
            existing_gateways=set(),
        )
        assert _failures(report, "firewall_rule_bad_tcpflags_mutex")

    def test_tcpflags_any_with_tcpflags2_fails(
        self, validator: FirewallRuleValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_rule("bad", tcpflags_any=True, tcpflags2="ack")],
            alias_names=set(),
            interface_assignment_names=set(),
            gateway_names=set(),
            existing_interfaces={"lan": {}},
            existing_aliases={},
            existing_gateways=set(),
        )
        assert _failures(report, "firewall_rule_bad_tcpflags_mutex")

    def test_tcpflags_any_alone_passes(
        self, validator: FirewallRuleValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_rule("ok", tcpflags_any=True)],
            alias_names=set(),
            interface_assignment_names=set(),
            gateway_names=set(),
            existing_interfaces={"lan": {}},
            existing_aliases={},
            existing_gateways=set(),
        )
        assert not _failures(report, "firewall_rule_ok_tcpflags_mutex")

    def test_tcpflags1_without_tcpflags_any_passes(
        self, validator: FirewallRuleValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_rule("ok", tcpflags1="syn,ack")],
            alias_names=set(),
            interface_assignment_names=set(),
            gateway_names=set(),
            existing_interfaces={"lan": {}},
            existing_aliases={},
            existing_gateways=set(),
        )
        assert not _failures(report, "firewall_rule_ok_tcpflags_mutex")


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_list_no_failures(
        self, validator: FirewallRuleValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [],
            alias_names=set(),
            interface_assignment_names=set(),
            gateway_names=set(),
            existing_interfaces={},
            existing_aliases={},
            existing_gateways=set(),
        )
        assert report.results == []

    def test_multiple_rules_all_validated(
        self, validator: FirewallRuleValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [
                _rule("a"),
                _rule("b"),
                _rule("c"),
            ],
            alias_names=set(),
            interface_assignment_names=set(),
            gateway_names=set(),
            existing_interfaces={"lan": {}},
            existing_aliases={},
            existing_gateways=set(),
        )
        # Each rule produces an ``_interface`` check (passing or failing).
        names = {c.check_name for c in report.results if c.check_name.endswith("_interface")}
        assert "firewall_rule_a_interface" in names
        assert "firewall_rule_b_interface" in names
        assert "firewall_rule_c_interface" in names

    def test_managed_gateways_default_none_does_not_crash(
        self, validator: FirewallRuleValidator, report: ValidationReport
    ) -> None:
        # ``managed_gateways`` is keyword-optional. Omitting it must not
        # crash the validator.
        validator.validate(
            [_rule("ok", gateway="WAN_DHCP")],
            alias_names=set(),
            interface_assignment_names=set(),
            gateway_names=set(),
            existing_interfaces={"lan": {}},
            existing_aliases={},
            existing_gateways={"WAN_DHCP"},
        )
        assert not _failures(report, "firewall_rule_ok_gateway")
