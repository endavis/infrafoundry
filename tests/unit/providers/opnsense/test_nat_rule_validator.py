"""Unit tests for ``NATRuleValidator``.

Coverage:
    - ``kind`` required and limited to ``outbound`` / ``one_to_one``.
    - Per-kind required fields (outbound: ``interface``+``target``;
      1:1: ``interface``+``external``).
    - Cross-resource references: ``interface`` against managed
      ``interface_assignments`` plus live overview; ``source_net``/
      ``destination_net``/``target`` against managed alias names plus
      keywords plus live aliases plus literal IP/CIDR.
    - Operator-set ``description`` containing ``[infrafoundry:<name>]`` rejected.
    - ``lock``, ``log``, ``enabled``, ``sequence`` type checks.
    - 1:1 ``type`` and ``natreflection`` enum constraints.
"""

from __future__ import annotations

from typing import Any

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.opnsense.validators.nat_rule_validator import (
    NATRuleValidator,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _outbound(name: str, **overrides: Any) -> ResourceConfig:
    config: dict[str, Any] = {
        "kind": "outbound",
        "interface": "wan",
        "target": "wanip",
    }
    config.update(overrides)
    return ResourceConfig(name=name, type="nat_rules", provider="opnsense", config=config)


def _one_to_one(name: str, **overrides: Any) -> ResourceConfig:
    config: dict[str, Any] = {
        "kind": "one_to_one",
        "interface": "wan",
        "external": "198.51.100.10",
    }
    config.update(overrides)
    return ResourceConfig(name=name, type="nat_rules", provider="opnsense", config=config)


@pytest.fixture
def report() -> ValidationReport:
    return ValidationReport()


@pytest.fixture
def validator(report: ValidationReport) -> NATRuleValidator:
    return NATRuleValidator(report)


def _failures(report: ValidationReport, check_name: str) -> list[Any]:
    return [c for c in report.results if c.check_name == check_name and not c.passed]


# ---------------------------------------------------------------------------
# kind
# ---------------------------------------------------------------------------


class TestKind:
    def test_missing_kind_fails(
        self, validator: NATRuleValidator, report: ValidationReport
    ) -> None:
        r = ResourceConfig(
            name="bad",
            type="nat_rules",
            provider="opnsense",
            config={"interface": "wan", "target": "wanip"},
        )
        validator.validate(
            [r],
            alias_names=set(),
            interface_assignment_names=set(),
            existing_interfaces={"wan": {}},
            existing_aliases={},
        )
        assert _failures(report, "nat_rule_bad_kind")

    def test_invalid_kind_port_forward_fails(
        self, validator: NATRuleValidator, report: ValidationReport
    ) -> None:
        # Port forwards are out of scope; kind: port_forward is rejected.
        r = ResourceConfig(
            name="pf",
            type="nat_rules",
            provider="opnsense",
            config={"kind": "port_forward", "interface": "wan"},
        )
        validator.validate(
            [r],
            alias_names=set(),
            interface_assignment_names=set(),
            existing_interfaces={"wan": {}},
            existing_aliases={},
        )
        assert _failures(report, "nat_rule_pf_kind")

    def test_outbound_passes(self, validator: NATRuleValidator, report: ValidationReport) -> None:
        validator.validate(
            [_outbound("ok")],
            alias_names=set(),
            interface_assignment_names=set(),
            existing_interfaces={"wan": {}},
            existing_aliases={},
        )
        assert not _failures(report, "nat_rule_ok_kind")


# ---------------------------------------------------------------------------
# Description identity-tag collision
# ---------------------------------------------------------------------------


class TestDescriptionIdentityTag:
    def test_operator_set_identity_tag_rejected(
        self, validator: NATRuleValidator, report: ValidationReport
    ) -> None:
        # Probe is position-agnostic; suffix-style forging is also rejected.
        validator.validate(
            [_outbound("evil", description="forged [infrafoundry:other]")],
            alias_names=set(),
            interface_assignment_names=set(),
            existing_interfaces={"wan": {}},
            existing_aliases={},
        )
        assert _failures(report, "nat_rule_evil_description")

    def test_normal_description_passes(
        self, validator: NATRuleValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_outbound("ok", description="LAN egress NAT")],
            alias_names=set(),
            interface_assignment_names=set(),
            existing_interfaces={"wan": {}},
            existing_aliases={},
        )
        assert not _failures(report, "nat_rule_ok_description")

    def test_non_string_description_rejected(
        self, validator: NATRuleValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_outbound("bad", description=123)],
            alias_names=set(),
            interface_assignment_names=set(),
            existing_interfaces={"wan": {}},
            existing_aliases={},
        )
        assert _failures(report, "nat_rule_bad_description")


# ---------------------------------------------------------------------------
# interface
# ---------------------------------------------------------------------------


class TestInterface:
    def test_managed_interface_assignment_resolves(
        self, validator: NATRuleValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_outbound("ok", interface="lan")],
            alias_names=set(),
            interface_assignment_names={"lan"},
            existing_interfaces={},
            existing_aliases={},
        )
        assert not _failures(report, "nat_rule_ok_interface")

    def test_live_interface_resolves(
        self, validator: NATRuleValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_outbound("ok", interface="wan")],
            alias_names=set(),
            interface_assignment_names=set(),
            existing_interfaces={"wan": {}},
            existing_aliases={},
        )
        assert not _failures(report, "nat_rule_ok_interface")

    def test_unknown_interface_fails(
        self, validator: NATRuleValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_outbound("bad", interface="bogus")],
            alias_names=set(),
            interface_assignment_names=set(),
            existing_interfaces={"wan": {}},
            existing_aliases={},
        )
        assert _failures(report, "nat_rule_bad_interface")

    def test_empty_interface_fails(
        self, validator: NATRuleValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_outbound("bad", interface="")],
            alias_names=set(),
            interface_assignment_names=set(),
            existing_interfaces={"wan": {}},
            existing_aliases={},
        )
        assert _failures(report, "nat_rule_bad_interface")


# ---------------------------------------------------------------------------
# Per-kind required fields
# ---------------------------------------------------------------------------


class TestOutboundRequiredFields:
    def test_missing_target_fails(
        self, validator: NATRuleValidator, report: ValidationReport
    ) -> None:
        r = ResourceConfig(
            name="bad",
            type="nat_rules",
            provider="opnsense",
            config={"kind": "outbound", "interface": "wan"},
        )
        validator.validate(
            [r],
            alias_names=set(),
            interface_assignment_names=set(),
            existing_interfaces={"wan": {}},
            existing_aliases={},
        )
        assert _failures(report, "nat_rule_bad_target")


class TestOneToOneRequiredFields:
    def test_missing_external_fails(
        self, validator: NATRuleValidator, report: ValidationReport
    ) -> None:
        r = ResourceConfig(
            name="bad",
            type="nat_rules",
            provider="opnsense",
            config={"kind": "one_to_one", "interface": "wan"},
        )
        validator.validate(
            [r],
            alias_names=set(),
            interface_assignment_names=set(),
            existing_interfaces={"wan": {}},
            existing_aliases={},
        )
        assert _failures(report, "nat_rule_bad_external")


# ---------------------------------------------------------------------------
# Net references (source_net / destination_net / target)
# ---------------------------------------------------------------------------


class TestNetReferences:
    def test_keyword_resolves_silently(
        self, validator: NATRuleValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_outbound("ok", source_net="any", destination_net="any")],
            alias_names=set(),
            interface_assignment_names=set(),
            existing_interfaces={"wan": {}},
            existing_aliases={},
        )
        assert not _failures(report, "nat_rule_ok_source_net")
        assert not _failures(report, "nat_rule_ok_destination_net")

    def test_managed_alias_resolves(
        self, validator: NATRuleValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_outbound("ok", source_net="lan_subnets")],
            alias_names={"lan_subnets"},
            interface_assignment_names=set(),
            existing_interfaces={"wan": {}},
            existing_aliases={},
        )
        assert not _failures(report, "nat_rule_ok_source_net")

    def test_live_alias_resolves(
        self, validator: NATRuleValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_outbound("ok", source_net="existing_alias")],
            alias_names=set(),
            interface_assignment_names=set(),
            existing_interfaces={"wan": {}},
            existing_aliases={"existing_alias": {"name": "existing_alias"}},
        )
        assert not _failures(report, "nat_rule_ok_source_net")

    def test_literal_ipv4_resolves(
        self, validator: NATRuleValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_outbound("ok", source_net="10.0.0.1")],
            alias_names=set(),
            interface_assignment_names=set(),
            existing_interfaces={"wan": {}},
            existing_aliases={},
        )
        assert not _failures(report, "nat_rule_ok_source_net")

    def test_literal_cidr_resolves(
        self, validator: NATRuleValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_outbound("ok", source_net="10.0.0.0/24")],
            alias_names=set(),
            interface_assignment_names=set(),
            existing_interfaces={"wan": {}},
            existing_aliases={},
        )
        assert not _failures(report, "nat_rule_ok_source_net")

    def test_literal_ipv6_resolves(
        self, validator: NATRuleValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_outbound("ok", source_net="fd00::1")],
            alias_names=set(),
            interface_assignment_names=set(),
            existing_interfaces={"wan": {}},
            existing_aliases={},
        )
        assert not _failures(report, "nat_rule_ok_source_net")

    def test_unknown_net_value_warns(
        self, validator: NATRuleValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_outbound("ok", source_net="bogus_value")],
            alias_names=set(),
            interface_assignment_names=set(),
            existing_interfaces={"wan": {}},
            existing_aliases={},
        )
        # Soft warning — not an ERROR.
        warnings = [
            c
            for c in report.results
            if c.check_name == "nat_rule_ok_source_net" and c.level == ValidationLevel.WARNING
        ]
        assert warnings

    def test_target_resolves_against_alias(
        self, validator: NATRuleValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_outbound("ok", target="vip_pool")],
            alias_names={"vip_pool"},
            interface_assignment_names=set(),
            existing_interfaces={"wan": {}},
            existing_aliases={},
        )
        assert not _failures(report, "nat_rule_ok_target")


# ---------------------------------------------------------------------------
# Booleans / sequence
# ---------------------------------------------------------------------------


class TestTypeChecks:
    def test_lock_must_be_bool(self, validator: NATRuleValidator, report: ValidationReport) -> None:
        validator.validate(
            [_outbound("bad", lock="yes")],
            alias_names=set(),
            interface_assignment_names=set(),
            existing_interfaces={"wan": {}},
            existing_aliases={},
        )
        assert _failures(report, "nat_rule_bad_lock")

    def test_log_must_be_bool(self, validator: NATRuleValidator, report: ValidationReport) -> None:
        validator.validate(
            [_outbound("bad", log="yes")],
            alias_names=set(),
            interface_assignment_names=set(),
            existing_interfaces={"wan": {}},
            existing_aliases={},
        )
        assert _failures(report, "nat_rule_bad_log")

    def test_enabled_must_be_bool(
        self, validator: NATRuleValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_outbound("bad", enabled="yes")],
            alias_names=set(),
            interface_assignment_names=set(),
            existing_interfaces={"wan": {}},
            existing_aliases={},
        )
        assert _failures(report, "nat_rule_bad_enabled")

    def test_sequence_must_be_int(
        self, validator: NATRuleValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_outbound("bad", sequence="not-int")],
            alias_names=set(),
            interface_assignment_names=set(),
            existing_interfaces={"wan": {}},
            existing_aliases={},
        )
        assert _failures(report, "nat_rule_bad_sequence")


# ---------------------------------------------------------------------------
# 1:1-specific enum checks
# ---------------------------------------------------------------------------


class TestOneToOneEnums:
    def test_invalid_type_fails(
        self, validator: NATRuleValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_one_to_one("bad", type="bogus")],
            alias_names=set(),
            interface_assignment_names=set(),
            existing_interfaces={"wan": {}},
            existing_aliases={},
        )
        assert _failures(report, "nat_rule_bad_type")

    def test_invalid_natreflection_fails(
        self, validator: NATRuleValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_one_to_one("bad", natreflection="not-allowed")],
            alias_names=set(),
            interface_assignment_names=set(),
            existing_interfaces={"wan": {}},
            existing_aliases={},
        )
        assert _failures(report, "nat_rule_bad_natreflection")

    def test_valid_natreflection_passes(
        self, validator: NATRuleValidator, report: ValidationReport
    ) -> None:
        for value in ("", "enable", "disable"):
            sub_report = ValidationReport()
            sub_validator = NATRuleValidator(sub_report)
            sub_validator.validate(
                [_one_to_one("ok", natreflection=value)],
                alias_names=set(),
                interface_assignment_names=set(),
                existing_interfaces={"wan": {}},
                existing_aliases={},
            )
            assert not _failures(sub_report, "nat_rule_ok_natreflection")


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_list_no_failures(
        self, validator: NATRuleValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [],
            alias_names=set(),
            interface_assignment_names=set(),
            existing_interfaces={},
            existing_aliases={},
        )
        assert report.results == []

    def test_multiple_rules_all_validated(
        self, validator: NATRuleValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [
                _outbound("a"),
                _outbound("b"),
                _one_to_one("c"),
            ],
            alias_names=set(),
            interface_assignment_names=set(),
            existing_interfaces={"wan": {}},
            existing_aliases={},
        )
        # Each gets at least an interface check.
        names = {c.check_name for c in report.results if c.check_name.endswith("_interface")}
        assert "nat_rule_a_interface" in names
        assert "nat_rule_b_interface" in names
        assert "nat_rule_c_interface" in names
