"""Unit tests for ``StaticRouteValidator``.

Coverage:
    - ``network`` field: IPv4 / IPv6 CIDRs accepted; missing / non-string /
      malformed / host-bits-set rejected.
    - ``gateway`` field: managed gateway ref accepted; live system gateway
      ref accepted (``WAN_DHCP`` / ``WAN_DHCP6``); unknown gateway rejected;
      missing / non-string rejected.
    - Protocol match: IPv4 network with IPv4 gateway passes; v4 network
      with v6 managed gateway fails; v4 network with ``WAN_DHCP6`` fails;
      v6 network with v4 gateway fails.
    - Bool type checks: ``enabled``, ``lock``.
    - ``description`` type check.
"""

from __future__ import annotations

from typing import Any

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationReport
from infrafoundry.providers.opnsense.validators.static_route_validator import (
    StaticRouteValidator,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _route(name: str, **overrides: Any) -> ResourceConfig:
    config: dict[str, Any] = {
        "network": "10.0.0.0/24",
        "gateway": "WAN_DHCP",
    }
    config.update(overrides)
    return ResourceConfig(name=name, type="routing.static", provider="opnsense", config=config)


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
def validator(report: ValidationReport) -> StaticRouteValidator:
    return StaticRouteValidator(report)


def _failures(report: ValidationReport, check_name: str) -> list[Any]:
    return [c for c in report.results if c.check_name == check_name and not c.passed]


# ---------------------------------------------------------------------------
# network
# ---------------------------------------------------------------------------


class TestNetwork:
    def test_v4_cidr_passes(
        self, validator: StaticRouteValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_route("ok", network="10.0.0.0/24")],
            managed_gateways=[],
            gateway_names=set(),
            existing_gateways={"WAN_DHCP"},
        )
        assert not _failures(report, "static_route_ok_network")

    def test_v6_cidr_passes(
        self, validator: StaticRouteValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_route("ok", network="2001:db8::/32", gateway="WAN_DHCP6")],
            managed_gateways=[],
            gateway_names=set(),
            existing_gateways={"WAN_DHCP6"},
        )
        assert not _failures(report, "static_route_ok_network")

    def test_missing_network_fails(
        self, validator: StaticRouteValidator, report: ValidationReport
    ) -> None:
        r = ResourceConfig(
            name="bad",
            type="routing.static",
            provider="opnsense",
            config={"gateway": "WAN_DHCP"},
        )
        validator.validate(
            [r],
            managed_gateways=[],
            gateway_names=set(),
            existing_gateways={"WAN_DHCP"},
        )
        assert _failures(report, "static_route_bad_network")

    def test_non_string_network_fails(
        self, validator: StaticRouteValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_route("bad", network=12345)],
            managed_gateways=[],
            gateway_names=set(),
            existing_gateways={"WAN_DHCP"},
        )
        assert _failures(report, "static_route_bad_network")

    def test_empty_network_fails(
        self, validator: StaticRouteValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_route("bad", network="")],
            managed_gateways=[],
            gateway_names=set(),
            existing_gateways={"WAN_DHCP"},
        )
        assert _failures(report, "static_route_bad_network")

    def test_malformed_cidr_fails(
        self, validator: StaticRouteValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_route("bad", network="not-a-cidr")],
            managed_gateways=[],
            gateway_names=set(),
            existing_gateways={"WAN_DHCP"},
        )
        assert _failures(report, "static_route_bad_network")

    def test_host_bits_set_v4_fails(
        self, validator: StaticRouteValidator, report: ValidationReport
    ) -> None:
        # ``10.0.0.1/24`` has host bits set; ``strict=True`` rejects it.
        validator.validate(
            [_route("bad", network="10.0.0.1/24")],
            managed_gateways=[],
            gateway_names=set(),
            existing_gateways={"WAN_DHCP"},
        )
        assert _failures(report, "static_route_bad_network")

    def test_host_bits_set_v6_fails(
        self, validator: StaticRouteValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_route("bad", network="2001:db8::1/32", gateway="WAN_DHCP6")],
            managed_gateways=[],
            gateway_names=set(),
            existing_gateways={"WAN_DHCP6"},
        )
        assert _failures(report, "static_route_bad_network")


# ---------------------------------------------------------------------------
# gateway (cross-ref)
# ---------------------------------------------------------------------------


class TestGateway:
    def test_managed_gateway_ref_accepted(
        self, validator: StaticRouteValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_route("ok", gateway="my-wan")],
            managed_gateways=[_gw("my-wan")],
            gateway_names={"my-wan"},
            existing_gateways=set(),
        )
        assert not _failures(report, "static_route_ok_gateway")

    def test_live_system_gateway_accepted(
        self, validator: StaticRouteValidator, report: ValidationReport
    ) -> None:
        # ``WAN_DHCP`` exists live on the box but isn't declared as managed.
        validator.validate(
            [_route("ok", gateway="WAN_DHCP")],
            managed_gateways=[],
            gateway_names=set(),
            existing_gateways={"WAN_DHCP"},
        )
        assert not _failures(report, "static_route_ok_gateway")

    def test_unknown_gateway_fails(
        self, validator: StaticRouteValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_route("bad", gateway="bogus-gw")],
            managed_gateways=[],
            gateway_names={"my-wan"},
            existing_gateways={"WAN_DHCP"},
        )
        assert _failures(report, "static_route_bad_gateway")

    def test_missing_gateway_fails(
        self, validator: StaticRouteValidator, report: ValidationReport
    ) -> None:
        r = ResourceConfig(
            name="bad",
            type="routing.static",
            provider="opnsense",
            config={"network": "10.0.0.0/24"},
        )
        validator.validate(
            [r],
            managed_gateways=[],
            gateway_names=set(),
            existing_gateways={"WAN_DHCP"},
        )
        assert _failures(report, "static_route_bad_gateway")

    def test_empty_gateway_fails(
        self, validator: StaticRouteValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_route("bad", gateway="")],
            managed_gateways=[],
            gateway_names=set(),
            existing_gateways={"WAN_DHCP"},
        )
        assert _failures(report, "static_route_bad_gateway")

    def test_non_string_gateway_fails(
        self, validator: StaticRouteValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_route("bad", gateway=12345)],
            managed_gateways=[],
            gateway_names=set(),
            existing_gateways=set(),
        )
        assert _failures(report, "static_route_bad_gateway")


# ---------------------------------------------------------------------------
# protocol match
# ---------------------------------------------------------------------------


class TestProtocolMatch:
    def test_v4_network_v4_managed_gateway_passes(
        self, validator: StaticRouteValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_route("ok", network="10.0.0.0/24", gateway="my-wan")],
            managed_gateways=[_gw("my-wan", protocol="inet")],
            gateway_names={"my-wan"},
            existing_gateways=set(),
        )
        assert not _failures(report, "static_route_ok_protocol_match")

    def test_v6_network_v6_managed_gateway_passes(
        self, validator: StaticRouteValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_route("ok", network="2001:db8::/32", gateway="my-wan6")],
            managed_gateways=[_gw("my-wan6", protocol="inet6")],
            gateway_names={"my-wan6"},
            existing_gateways=set(),
        )
        assert not _failures(report, "static_route_ok_protocol_match")

    def test_v4_network_v6_managed_gateway_fails(
        self, validator: StaticRouteValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_route("bad", network="10.0.0.0/24", gateway="my-wan6")],
            managed_gateways=[_gw("my-wan6", protocol="inet6")],
            gateway_names={"my-wan6"},
            existing_gateways=set(),
        )
        assert _failures(report, "static_route_bad_protocol_match")

    def test_v6_network_v4_managed_gateway_fails(
        self, validator: StaticRouteValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_route("bad", network="2001:db8::/32", gateway="my-wan")],
            managed_gateways=[_gw("my-wan", protocol="inet")],
            gateway_names={"my-wan"},
            existing_gateways=set(),
        )
        assert _failures(report, "static_route_bad_protocol_match")

    def test_v4_network_v6_dynamic_gateway_fails(
        self, validator: StaticRouteValidator, report: ValidationReport
    ) -> None:
        # ``WAN_DHCP6`` is heuristically v6 (trailing ``6``).
        validator.validate(
            [_route("bad", network="10.0.0.0/24", gateway="WAN_DHCP6")],
            managed_gateways=[],
            gateway_names=set(),
            existing_gateways={"WAN_DHCP6"},
        )
        assert _failures(report, "static_route_bad_protocol_match")

    def test_v6_network_v4_dynamic_gateway_fails(
        self, validator: StaticRouteValidator, report: ValidationReport
    ) -> None:
        # ``WAN_DHCP`` is heuristically v4 (no trailing ``6``).
        validator.validate(
            [_route("bad", network="2001:db8::/32", gateway="WAN_DHCP")],
            managed_gateways=[],
            gateway_names=set(),
            existing_gateways={"WAN_DHCP"},
        )
        assert _failures(report, "static_route_bad_protocol_match")

    def test_v4_network_v4_dynamic_gateway_passes(
        self, validator: StaticRouteValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_route("ok", network="10.0.0.0/24", gateway="WAN_DHCP")],
            managed_gateways=[],
            gateway_names=set(),
            existing_gateways={"WAN_DHCP"},
        )
        assert not _failures(report, "static_route_ok_protocol_match")


# ---------------------------------------------------------------------------
# bool type checks
# ---------------------------------------------------------------------------


class TestBoolFields:
    def test_enabled_must_be_bool(
        self, validator: StaticRouteValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_route("bad", enabled="yes")],
            managed_gateways=[],
            gateway_names=set(),
            existing_gateways={"WAN_DHCP"},
        )
        assert _failures(report, "static_route_bad_enabled")

    def test_lock_must_be_bool(
        self, validator: StaticRouteValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_route("bad", lock="yes")],
            managed_gateways=[],
            gateway_names=set(),
            existing_gateways={"WAN_DHCP"},
        )
        assert _failures(report, "static_route_bad_lock")

    def test_enabled_true_passes(
        self, validator: StaticRouteValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_route("ok", enabled=True)],
            managed_gateways=[],
            gateway_names=set(),
            existing_gateways={"WAN_DHCP"},
        )
        assert not _failures(report, "static_route_ok_enabled")

    def test_lock_true_passes(
        self, validator: StaticRouteValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_route("ok", lock=True)],
            managed_gateways=[],
            gateway_names=set(),
            existing_gateways={"WAN_DHCP"},
        )
        assert not _failures(report, "static_route_ok_lock")


# ---------------------------------------------------------------------------
# description
# ---------------------------------------------------------------------------


class TestDescription:
    def test_string_passes(self, validator: StaticRouteValidator, report: ValidationReport) -> None:
        validator.validate(
            [_route("ok", description="my description")],
            managed_gateways=[],
            gateway_names=set(),
            existing_gateways={"WAN_DHCP"},
        )
        assert not _failures(report, "static_route_ok_description")

    def test_non_string_fails(
        self, validator: StaticRouteValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_route("bad", description=12345)],
            managed_gateways=[],
            gateway_names=set(),
            existing_gateways={"WAN_DHCP"},
        )
        assert _failures(report, "static_route_bad_description")


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_list_no_failures(
        self, validator: StaticRouteValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [],
            managed_gateways=[],
            gateway_names=set(),
            existing_gateways=set(),
        )
        assert report.results == []

    def test_multiple_routes_all_validated(
        self, validator: StaticRouteValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [
                _route("a"),
                _route("b", network="172.16.0.0/24"),
                _route("c", network="192.168.0.0/24"),
            ],
            managed_gateways=[],
            gateway_names=set(),
            existing_gateways={"WAN_DHCP"},
        )
        names = {c.check_name for c in report.results if c.check_name.endswith("_gateway")}
        assert "static_route_a_gateway" in names
        assert "static_route_b_gateway" in names
        assert "static_route_c_gateway" in names

    def test_managed_gateway_with_invalid_protocol_skipped_in_protocol_index(
        self, validator: StaticRouteValidator, report: ValidationReport
    ) -> None:
        # A managed gateway with a bogus protocol value shouldn't crash
        # the protocol-match check — it has its own validator failures
        # from ``GatewayValidator`` and is skipped here.
        bad_gw = ResourceConfig(
            name="bad-gw",
            type="routing.gateways",
            provider="opnsense",
            config={"interface": "wan", "protocol": "ipv7", "gateway": "192.0.2.1"},
        )
        validator.validate(
            [_route("ok", gateway="bad-gw")],
            managed_gateways=[bad_gw],
            gateway_names={"bad-gw"},
            existing_gateways=set(),
        )
        # Gateway ref still resolves — the protocol-match check falls
        # through to the trailing-6 heuristic (no trailing 6 ⇒ v4),
        # and a v4 network + heuristic-v4 ⇒ pass.
        assert not _failures(report, "static_route_ok_protocol_match")


# ---------------------------------------------------------------------------
# Dotted-path cross-references (#793) — forward-compat
# ---------------------------------------------------------------------------


class TestDottedPathXRefs:
    """The static-route validator accepts dotted-path gateway refs when
    an ``index`` is supplied (Phase 3 of #793). Bare-name behaviour
    is unchanged when ``index`` is None — covered by the other test
    classes above. These tests confirm forward-compat for the new
    syntax."""

    def test_cross_plugin_absolute_gateway_ref_resolves(
        self, validator: StaticRouteValidator, report: ValidationReport
    ) -> None:
        from infrafoundry.providers.opnsense.validators._xref import build_xref_index

        gw = _gw("WAN_GW", protocol="inet")
        index = build_xref_index([gw])
        validator.validate(
            [_route("ok", gateway="routing.gateways.WAN_GW")],
            managed_gateways=[gw],
            gateway_names={"WAN_GW"},
            existing_gateways=set(),
            index=index,
        )
        assert not _failures(report, "static_route_ok_gateway")

    def test_in_plugin_relative_gateway_ref_resolves(
        self, validator: StaticRouteValidator, report: ValidationReport
    ) -> None:
        from infrafoundry.providers.opnsense.validators._xref import build_xref_index

        gw = _gw("WAN_GW", protocol="inet")
        index = build_xref_index([gw])
        validator.validate(
            [_route("ok", gateway="gateways.WAN_GW")],
            managed_gateways=[gw],
            gateway_names={"WAN_GW"},
            existing_gateways=set(),
            index=index,
        )
        assert not _failures(report, "static_route_ok_gateway")

    def test_dotted_miss_falls_back_to_bare_name(
        self, validator: StaticRouteValidator, report: ValidationReport
    ) -> None:
        from infrafoundry.providers.opnsense.validators._xref import build_xref_index

        # Empty index — the dotted lookup misses, but we don't dotted-
        # form the gateway value, so the bare-name path should still
        # validate against the live gateway set.
        index = build_xref_index([])
        validator.validate(
            [_route("ok", gateway="WAN_DHCP")],
            managed_gateways=[],
            gateway_names=set(),
            existing_gateways={"WAN_DHCP"},
            index=index,
        )
        assert not _failures(report, "static_route_ok_gateway")

    def test_index_none_preserves_legacy_behaviour(
        self, validator: StaticRouteValidator, report: ValidationReport
    ) -> None:
        # Calling without ``index`` is the pre-#793 contract: bare
        # names only, no dotted-form support.
        validator.validate(
            [_route("ok", gateway="WAN_DHCP")],
            managed_gateways=[],
            gateway_names=set(),
            existing_gateways={"WAN_DHCP"},
        )
        assert not _failures(report, "static_route_ok_gateway")

    def test_dotted_unknown_falls_back_then_fails(
        self, validator: StaticRouteValidator, report: ValidationReport
    ) -> None:
        from infrafoundry.providers.opnsense.validators._xref import build_xref_index

        # Dotted form misses index AND falls back to bare-name lookup
        # which also misses → final ERROR.
        index = build_xref_index([])
        validator.validate(
            [_route("ok", gateway="routing.gateways.GHOST")],
            managed_gateways=[],
            gateway_names=set(),
            existing_gateways=set(),
            index=index,
        )
        assert _failures(report, "static_route_ok_gateway")
