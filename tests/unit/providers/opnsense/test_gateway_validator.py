"""Unit tests for ``GatewayValidator``.

Coverage:
    - ``protocol`` discriminator: ``inet`` / ``inet6`` accepted; missing /
      bogus values rejected.
    - ``interface`` cross-reference: managed assignments + live overview;
      unknown interface fails.
    - ``ipaddr`` field: literal ``dynamic`` allowed; IP literal must match
      ``protocol``; non-string rejected.
    - ``gateway`` field: IP literal must match ``protocol``; non-string
      rejected; empty string ignored at validator level (parser handles
      the dynamic-vs-static contract).
    - ``monitor`` field: optional; IP literal or hostname accepted; non-string
      and bogus values rejected.
    - ``priority`` integer in 1-255.
    - ``weight`` integer >= 1.
    - Bool type checks: ``defaultgw``, ``enabled``, ``lock``,
      ``monitor_disable``, ``monitor_noroute``, ``force_down``, ``fargw``.
    - ``description`` type check.
"""

from __future__ import annotations

from typing import Any

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationReport
from infrafoundry.providers.opnsense.validators.gateway_validator import (
    GatewayValidator,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _gw(name: str, **overrides: Any) -> ResourceConfig:
    config: dict[str, Any] = {
        "interface": "wan",
        "protocol": "inet",
        "gateway": "192.0.2.1",
    }
    config.update(overrides)
    return ResourceConfig(name=name, type="routing.gateways", provider="opnsense", config=config)


@pytest.fixture
def report() -> ValidationReport:
    return ValidationReport()


@pytest.fixture
def validator(report: ValidationReport) -> GatewayValidator:
    return GatewayValidator(report)


def _failures(report: ValidationReport, check_name: str) -> list[Any]:
    return [c for c in report.results if c.check_name == check_name and not c.passed]


# ---------------------------------------------------------------------------
# protocol
# ---------------------------------------------------------------------------


class TestProtocol:
    def test_inet_passes(self, validator: GatewayValidator, report: ValidationReport) -> None:
        validator.validate(
            [_gw("ok", protocol="inet")],
            interface_assignment_names=set(),
            existing_interfaces={"wan": {}},
        )
        assert not _failures(report, "gateway_ok_protocol")

    def test_inet6_passes(self, validator: GatewayValidator, report: ValidationReport) -> None:
        validator.validate(
            [_gw("ok", protocol="inet6", gateway="fe80::1")],
            interface_assignment_names=set(),
            existing_interfaces={"wan": {}},
        )
        assert not _failures(report, "gateway_ok_protocol")

    def test_missing_protocol_fails(
        self, validator: GatewayValidator, report: ValidationReport
    ) -> None:
        r = ResourceConfig(
            name="bad",
            type="routing.gateways",
            provider="opnsense",
            config={"interface": "wan", "gateway": "192.0.2.1"},
        )
        validator.validate(
            [r],
            interface_assignment_names=set(),
            existing_interfaces={"wan": {}},
        )
        assert _failures(report, "gateway_bad_protocol")

    def test_invalid_protocol_fails(
        self, validator: GatewayValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_gw("bad", protocol="ipv7")],
            interface_assignment_names=set(),
            existing_interfaces={"wan": {}},
        )
        assert _failures(report, "gateway_bad_protocol")


# ---------------------------------------------------------------------------
# interface
# ---------------------------------------------------------------------------


class TestInterface:
    def test_managed_interface_assignment_resolves(
        self, validator: GatewayValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_gw("ok", interface="lan")],
            interface_assignment_names={"lan"},
            existing_interfaces={},
        )
        assert not _failures(report, "gateway_ok_interface")

    def test_live_interface_resolves(
        self, validator: GatewayValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_gw("ok", interface="wan")],
            interface_assignment_names=set(),
            existing_interfaces={"wan": {}},
        )
        assert not _failures(report, "gateway_ok_interface")

    def test_unknown_interface_fails(
        self, validator: GatewayValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_gw("bad", interface="bogus")],
            interface_assignment_names=set(),
            existing_interfaces={"wan": {}},
        )
        assert _failures(report, "gateway_bad_interface")

    def test_empty_interface_fails(
        self, validator: GatewayValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_gw("bad", interface="")],
            interface_assignment_names=set(),
            existing_interfaces={"wan": {}},
        )
        assert _failures(report, "gateway_bad_interface")

    def test_missing_interface_fails(
        self, validator: GatewayValidator, report: ValidationReport
    ) -> None:
        r = ResourceConfig(
            name="bad",
            type="routing.gateways",
            provider="opnsense",
            config={"protocol": "inet", "gateway": "192.0.2.1"},
        )
        validator.validate(
            [r],
            interface_assignment_names=set(),
            existing_interfaces={"wan": {}},
        )
        assert _failures(report, "gateway_bad_interface")


# ---------------------------------------------------------------------------
# ipaddr
# ---------------------------------------------------------------------------


class TestIpaddr:
    def test_dynamic_keyword_accepted(
        self, validator: GatewayValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_gw("ok", ipaddr="dynamic")],
            interface_assignment_names=set(),
            existing_interfaces={"wan": {}},
        )
        assert not _failures(report, "gateway_ok_ipaddr")

    def test_inet_ip_literal_passes(
        self, validator: GatewayValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_gw("ok", ipaddr="192.0.2.5")],
            interface_assignment_names=set(),
            existing_interfaces={"wan": {}},
        )
        assert not _failures(report, "gateway_ok_ipaddr")

    def test_inet_protocol_with_v6_ipaddr_fails(
        self, validator: GatewayValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_gw("bad", ipaddr="fe80::1", protocol="inet")],
            interface_assignment_names=set(),
            existing_interfaces={"wan": {}},
        )
        assert _failures(report, "gateway_bad_ipaddr")

    def test_non_string_ipaddr_fails(
        self, validator: GatewayValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_gw("bad", ipaddr=12345)],
            interface_assignment_names=set(),
            existing_interfaces={"wan": {}},
        )
        assert _failures(report, "gateway_bad_ipaddr")


# ---------------------------------------------------------------------------
# gateway field
# ---------------------------------------------------------------------------


class TestGatewayField:
    def test_inet_ip_passes(self, validator: GatewayValidator, report: ValidationReport) -> None:
        validator.validate(
            [_gw("ok", gateway="192.0.2.1")],
            interface_assignment_names=set(),
            existing_interfaces={"wan": {}},
        )
        assert not _failures(report, "gateway_ok_gateway")

    def test_inet6_ip_passes(self, validator: GatewayValidator, report: ValidationReport) -> None:
        validator.validate(
            [_gw("ok", gateway="fe80::1", protocol="inet6")],
            interface_assignment_names=set(),
            existing_interfaces={"wan": {}},
        )
        assert not _failures(report, "gateway_ok_gateway")

    def test_protocol_mismatch_fails(
        self, validator: GatewayValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_gw("bad", gateway="fe80::1", protocol="inet")],
            interface_assignment_names=set(),
            existing_interfaces={"wan": {}},
        )
        assert _failures(report, "gateway_bad_gateway")

    def test_non_string_fails(self, validator: GatewayValidator, report: ValidationReport) -> None:
        validator.validate(
            [_gw("bad", gateway=12345)],
            interface_assignment_names=set(),
            existing_interfaces={"wan": {}},
        )
        assert _failures(report, "gateway_bad_gateway")

    def test_empty_string_ignored_at_validator(
        self, validator: GatewayValidator, report: ValidationReport
    ) -> None:
        # The validator treats "" as benign and lets the parser enforce the
        # dynamic-vs-static contract.
        validator.validate(
            [_gw("ok", gateway="", ipaddr="dynamic")],
            interface_assignment_names=set(),
            existing_interfaces={"wan": {}},
        )
        assert not _failures(report, "gateway_ok_gateway")


# ---------------------------------------------------------------------------
# monitor
# ---------------------------------------------------------------------------


class TestMonitor:
    def test_ip_literal_passes(self, validator: GatewayValidator, report: ValidationReport) -> None:
        validator.validate(
            [_gw("ok", monitor="1.1.1.1")],
            interface_assignment_names=set(),
            existing_interfaces={"wan": {}},
        )
        assert not _failures(report, "gateway_ok_monitor")

    def test_hostname_passes(self, validator: GatewayValidator, report: ValidationReport) -> None:
        validator.validate(
            [_gw("ok", monitor="dns.example.com")],
            interface_assignment_names=set(),
            existing_interfaces={"wan": {}},
        )
        assert not _failures(report, "gateway_ok_monitor")

    def test_bogus_value_fails(self, validator: GatewayValidator, report: ValidationReport) -> None:
        validator.validate(
            [_gw("bad", monitor="not a valid host or ip")],
            interface_assignment_names=set(),
            existing_interfaces={"wan": {}},
        )
        assert _failures(report, "gateway_bad_monitor")

    def test_empty_passes(self, validator: GatewayValidator, report: ValidationReport) -> None:
        validator.validate(
            [_gw("ok", monitor="")],
            interface_assignment_names=set(),
            existing_interfaces={"wan": {}},
        )
        assert not _failures(report, "gateway_ok_monitor")

    def test_non_string_fails(self, validator: GatewayValidator, report: ValidationReport) -> None:
        validator.validate(
            [_gw("bad", monitor=12345)],
            interface_assignment_names=set(),
            existing_interfaces={"wan": {}},
        )
        assert _failures(report, "gateway_bad_monitor")


# ---------------------------------------------------------------------------
# priority / weight
# ---------------------------------------------------------------------------


class TestPriority:
    def test_in_range_passes(self, validator: GatewayValidator, report: ValidationReport) -> None:
        validator.validate(
            [_gw("ok", priority=128)],
            interface_assignment_names=set(),
            existing_interfaces={"wan": {}},
        )
        assert not _failures(report, "gateway_ok_priority")

    def test_below_min_fails(self, validator: GatewayValidator, report: ValidationReport) -> None:
        validator.validate(
            [_gw("bad", priority=0)],
            interface_assignment_names=set(),
            existing_interfaces={"wan": {}},
        )
        assert _failures(report, "gateway_bad_priority")

    def test_above_max_fails(self, validator: GatewayValidator, report: ValidationReport) -> None:
        validator.validate(
            [_gw("bad", priority=999)],
            interface_assignment_names=set(),
            existing_interfaces={"wan": {}},
        )
        assert _failures(report, "gateway_bad_priority")

    def test_non_int_fails(self, validator: GatewayValidator, report: ValidationReport) -> None:
        validator.validate(
            [_gw("bad", priority="high")],
            interface_assignment_names=set(),
            existing_interfaces={"wan": {}},
        )
        assert _failures(report, "gateway_bad_priority")


class TestWeight:
    def test_one_passes(self, validator: GatewayValidator, report: ValidationReport) -> None:
        validator.validate(
            [_gw("ok", weight=1)],
            interface_assignment_names=set(),
            existing_interfaces={"wan": {}},
        )
        assert not _failures(report, "gateway_ok_weight")

    def test_zero_fails(self, validator: GatewayValidator, report: ValidationReport) -> None:
        validator.validate(
            [_gw("bad", weight=0)],
            interface_assignment_names=set(),
            existing_interfaces={"wan": {}},
        )
        assert _failures(report, "gateway_bad_weight")

    def test_negative_fails(self, validator: GatewayValidator, report: ValidationReport) -> None:
        validator.validate(
            [_gw("bad", weight=-1)],
            interface_assignment_names=set(),
            existing_interfaces={"wan": {}},
        )
        assert _failures(report, "gateway_bad_weight")

    def test_non_int_fails(self, validator: GatewayValidator, report: ValidationReport) -> None:
        validator.validate(
            [_gw("bad", weight="heavy")],
            interface_assignment_names=set(),
            existing_interfaces={"wan": {}},
        )
        assert _failures(report, "gateway_bad_weight")


# ---------------------------------------------------------------------------
# bool type checks
# ---------------------------------------------------------------------------


class TestBoolFields:
    def test_defaultgw_must_be_bool(
        self, validator: GatewayValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_gw("bad", defaultgw="yes")],
            interface_assignment_names=set(),
            existing_interfaces={"wan": {}},
        )
        assert _failures(report, "gateway_bad_defaultgw")

    def test_enabled_must_be_bool(
        self, validator: GatewayValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_gw("bad", enabled="yes")],
            interface_assignment_names=set(),
            existing_interfaces={"wan": {}},
        )
        assert _failures(report, "gateway_bad_enabled")

    def test_lock_must_be_bool(self, validator: GatewayValidator, report: ValidationReport) -> None:
        validator.validate(
            [_gw("bad", lock="yes")],
            interface_assignment_names=set(),
            existing_interfaces={"wan": {}},
        )
        assert _failures(report, "gateway_bad_lock")

    def test_monitor_disable_must_be_bool(
        self, validator: GatewayValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_gw("bad", monitor_disable="yes")],
            interface_assignment_names=set(),
            existing_interfaces={"wan": {}},
        )
        assert _failures(report, "gateway_bad_monitor_disable")

    def test_monitor_noroute_must_be_bool(
        self, validator: GatewayValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_gw("bad", monitor_noroute="yes")],
            interface_assignment_names=set(),
            existing_interfaces={"wan": {}},
        )
        assert _failures(report, "gateway_bad_monitor_noroute")

    def test_force_down_must_be_bool(
        self, validator: GatewayValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_gw("bad", force_down="yes")],
            interface_assignment_names=set(),
            existing_interfaces={"wan": {}},
        )
        assert _failures(report, "gateway_bad_force_down")

    def test_fargw_must_be_bool(
        self, validator: GatewayValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_gw("bad", fargw="yes")],
            interface_assignment_names=set(),
            existing_interfaces={"wan": {}},
        )
        assert _failures(report, "gateway_bad_fargw")


# ---------------------------------------------------------------------------
# description
# ---------------------------------------------------------------------------


class TestDescription:
    def test_string_passes(self, validator: GatewayValidator, report: ValidationReport) -> None:
        validator.validate(
            [_gw("ok", description="WAN default")],
            interface_assignment_names=set(),
            existing_interfaces={"wan": {}},
        )
        assert not _failures(report, "gateway_ok_description")

    def test_non_string_fails(self, validator: GatewayValidator, report: ValidationReport) -> None:
        validator.validate(
            [_gw("bad", description=12345)],
            interface_assignment_names=set(),
            existing_interfaces={"wan": {}},
        )
        assert _failures(report, "gateway_bad_description")


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_list_no_failures(
        self, validator: GatewayValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [],
            interface_assignment_names=set(),
            existing_interfaces={},
        )
        assert report.results == []

    def test_multiple_gateways_all_validated(
        self, validator: GatewayValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_gw("a"), _gw("b"), _gw("c")],
            interface_assignment_names=set(),
            existing_interfaces={"wan": {}},
        )
        names = {c.check_name for c in report.results if c.check_name.endswith("_interface")}
        assert "gateway_a_interface" in names
        assert "gateway_b_interface" in names
        assert "gateway_c_interface" in names
