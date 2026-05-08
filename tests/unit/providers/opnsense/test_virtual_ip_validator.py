"""Unit tests for ``VirtualIPValidator``.

Coverage:
    - ``mode`` discriminator: each value (``ipalias``, ``carp``, ``proxyarp``)
      accepted; missing is treated as default; invalid rejected.
    - Required fields per mode: CARP requires ``vhid`` and ``password``;
      ipalias / proxyarp do not.
    - ``secret://`` URI accepted in ``password`` field at validate time
      without resolution; plaintext password warns.
    - ipalias-only fields: ``gateway`` (string), ``noexpand`` / ``nobind``
      (bool); CARP-only fields warn when ``mode`` is not CARP.
    - CARP-only field types: ``vhid`` (1-255 string/int), ``advbase`` /
      ``advskew`` strings, ``peer`` / ``peer6`` valid IPs of the right
      family if set, ``nosync`` bool.
    - Cross-resource ref: ``interface`` validates against managed
      ``interface_assignments`` names plus live overview interfaces.
    - IP / CIDR: ``address`` is a valid IPv4 or IPv6; ``network`` is a
      numeric string in 1-32 (IPv4) or 1-128 (IPv6) range.
    - Uniqueness: ``(interface, mode, address, vhid)`` tuple within YAML.
    - Type checks: ``description`` string; ``enabled`` / ``lock`` bool.
    - Edge cases: empty resource list emits no failures; multiple
      resources all validated (no short-circuit).
"""

from __future__ import annotations

from typing import Any

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.opnsense.validators.virtual_ip_validator import (
    VirtualIPValidator,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ipalias(name: str, **overrides: Any) -> ResourceConfig:
    config: dict[str, Any] = {
        "mode": "ipalias",
        "interface": "lan",
        "address": "10.0.0.10",
        "network": "24",
    }
    config.update(overrides)
    return ResourceConfig(
        name=name, type="interfaces.virtual_ips", provider="opnsense", config=config
    )


def _carp(name: str, **overrides: Any) -> ResourceConfig:
    config: dict[str, Any] = {
        "mode": "carp",
        "interface": "lan",
        "address": "10.0.0.1",
        "network": "24",
        "vhid": "1",
        "password": "secret://env_secrets/opnsense/carp_passwords/lan_carp_1",
    }
    config.update(overrides)
    return ResourceConfig(
        name=name, type="interfaces.virtual_ips", provider="opnsense", config=config
    )


def _proxyarp(name: str, **overrides: Any) -> ResourceConfig:
    config: dict[str, Any] = {
        "mode": "proxyarp",
        "interface": "lan",
        "address": "10.0.0.20",
        "network": "32",
    }
    config.update(overrides)
    return ResourceConfig(
        name=name, type="interfaces.virtual_ips", provider="opnsense", config=config
    )


@pytest.fixture
def report() -> ValidationReport:
    return ValidationReport()


@pytest.fixture
def validator(report: ValidationReport) -> VirtualIPValidator:
    return VirtualIPValidator(report)


def _failures(report: ValidationReport, check_name: str) -> list[Any]:
    return [c for c in report.results if c.check_name == check_name and not c.passed]


def _warnings(report: ValidationReport, check_name: str) -> list[Any]:
    return [
        c
        for c in report.results
        if c.check_name == check_name and not c.passed and c.level == ValidationLevel.WARNING
    ]


def _errors(report: ValidationReport, check_name: str) -> list[Any]:
    return [
        c
        for c in report.results
        if c.check_name == check_name and not c.passed and c.level == ValidationLevel.ERROR
    ]


# ---------------------------------------------------------------------------
# mode discriminator
# ---------------------------------------------------------------------------


class TestMode:
    def test_ipalias_passes(self, validator: VirtualIPValidator, report: ValidationReport) -> None:
        validator.validate(
            [_ipalias("ok")],
            managed_interface_names={"lan"},
            existing_interfaces={},
        )
        assert not _failures(report, "virtual_ip_ok_mode")

    def test_carp_passes(self, validator: VirtualIPValidator, report: ValidationReport) -> None:
        validator.validate(
            [_carp("ok")],
            managed_interface_names={"lan"},
            existing_interfaces={},
        )
        assert not _failures(report, "virtual_ip_ok_mode")

    def test_proxyarp_passes(self, validator: VirtualIPValidator, report: ValidationReport) -> None:
        validator.validate(
            [_proxyarp("ok")],
            managed_interface_names={"lan"},
            existing_interfaces={},
        )
        assert not _failures(report, "virtual_ip_ok_mode")

    def test_missing_mode_defaults_ipalias(
        self, validator: VirtualIPValidator, report: ValidationReport
    ) -> None:
        # Missing mode coerces to default (ipalias) — should not fail.
        r = ResourceConfig(
            name="ok",
            type="interfaces.virtual_ips",
            provider="opnsense",
            config={
                "interface": "lan",
                "address": "10.0.0.10",
                "network": "24",
            },
        )
        validator.validate(
            [r],
            managed_interface_names={"lan"},
            existing_interfaces={},
        )
        assert not _failures(report, "virtual_ip_ok_mode")

    def test_invalid_mode_alias_fails(
        self, validator: VirtualIPValidator, report: ValidationReport
    ) -> None:
        # Issue body's draft used "alias" — probe is authoritative; only
        # "ipalias" is accepted.
        validator.validate(
            [_ipalias("bad", mode="alias")],
            managed_interface_names={"lan"},
            existing_interfaces={},
        )
        assert _failures(report, "virtual_ip_bad_mode")

    def test_invalid_mode_other_fails(
        self, validator: VirtualIPValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_ipalias("bad", mode="other")],
            managed_interface_names={"lan"},
            existing_interfaces={},
        )
        assert _failures(report, "virtual_ip_bad_mode")

    def test_non_string_mode_fails(
        self, validator: VirtualIPValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_ipalias("bad", mode=123)],
            managed_interface_names={"lan"},
            existing_interfaces={},
        )
        assert _failures(report, "virtual_ip_bad_mode")


# ---------------------------------------------------------------------------
# interface (cross-ref into managed + live)
# ---------------------------------------------------------------------------


class TestInterface:
    def test_managed_interface_name_resolves(
        self, validator: VirtualIPValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_ipalias("ok", interface="lan")],
            managed_interface_names={"lan"},
            existing_interfaces={},
        )
        assert not _failures(report, "virtual_ip_ok_interface")

    def test_live_interface_resolves(
        self, validator: VirtualIPValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_ipalias("ok", interface="wan")],
            managed_interface_names=set(),
            existing_interfaces={"wan": object()},
        )
        assert not _failures(report, "virtual_ip_ok_interface")

    def test_unknown_interface_fails(
        self, validator: VirtualIPValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_ipalias("bad", interface="bogus")],
            managed_interface_names={"lan"},
            existing_interfaces={"wan": object()},
        )
        assert _failures(report, "virtual_ip_bad_interface")

    def test_missing_interface_fails(
        self, validator: VirtualIPValidator, report: ValidationReport
    ) -> None:
        r = ResourceConfig(
            name="bad",
            type="interfaces.virtual_ips",
            provider="opnsense",
            config={
                "mode": "ipalias",
                "address": "10.0.0.10",
                "network": "24",
            },
        )
        validator.validate(
            [r],
            managed_interface_names=set(),
            existing_interfaces={},
        )
        assert _failures(report, "virtual_ip_bad_interface")

    def test_empty_interface_fails(
        self, validator: VirtualIPValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_ipalias("bad", interface="")],
            managed_interface_names=set(),
            existing_interfaces={},
        )
        assert _failures(report, "virtual_ip_bad_interface")

    def test_non_string_interface_fails(
        self, validator: VirtualIPValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_ipalias("bad", interface=123)],
            managed_interface_names=set(),
            existing_interfaces={},
        )
        assert _failures(report, "virtual_ip_bad_interface")


# ---------------------------------------------------------------------------
# address + network
# ---------------------------------------------------------------------------


class TestAddress:
    def test_ipv4_passes(self, validator: VirtualIPValidator, report: ValidationReport) -> None:
        validator.validate(
            [_ipalias("ok", address="10.1.2.3")],
            managed_interface_names={"lan"},
            existing_interfaces={},
        )
        assert not _failures(report, "virtual_ip_ok_address")

    def test_ipv6_passes(self, validator: VirtualIPValidator, report: ValidationReport) -> None:
        validator.validate(
            [_ipalias("ok", address="2001:db8::1", network="64")],
            managed_interface_names={"lan"},
            existing_interfaces={},
        )
        assert not _failures(report, "virtual_ip_ok_address")

    def test_missing_address_fails(
        self, validator: VirtualIPValidator, report: ValidationReport
    ) -> None:
        r = ResourceConfig(
            name="bad",
            type="interfaces.virtual_ips",
            provider="opnsense",
            config={
                "mode": "ipalias",
                "interface": "lan",
                "network": "24",
            },
        )
        validator.validate(
            [r],
            managed_interface_names={"lan"},
            existing_interfaces={},
        )
        assert _failures(report, "virtual_ip_bad_address")

    def test_empty_address_fails(
        self, validator: VirtualIPValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_ipalias("bad", address="")],
            managed_interface_names={"lan"},
            existing_interfaces={},
        )
        assert _failures(report, "virtual_ip_bad_address")

    def test_non_string_address_fails(
        self, validator: VirtualIPValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_ipalias("bad", address=12345)],
            managed_interface_names={"lan"},
            existing_interfaces={},
        )
        assert _failures(report, "virtual_ip_bad_address")

    def test_malformed_ip_fails(
        self, validator: VirtualIPValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_ipalias("bad", address="not-an-ip")],
            managed_interface_names={"lan"},
            existing_interfaces={},
        )
        assert _failures(report, "virtual_ip_bad_address")


class TestNetwork:
    def test_v4_mask_passes(self, validator: VirtualIPValidator, report: ValidationReport) -> None:
        validator.validate(
            [_ipalias("ok", address="10.0.0.10", network="24")],
            managed_interface_names={"lan"},
            existing_interfaces={},
        )
        assert not _failures(report, "virtual_ip_ok_network")

    def test_v6_mask_passes(self, validator: VirtualIPValidator, report: ValidationReport) -> None:
        validator.validate(
            [_ipalias("ok", address="2001:db8::1", network="64")],
            managed_interface_names={"lan"},
            existing_interfaces={},
        )
        assert not _failures(report, "virtual_ip_ok_network")

    def test_v6_mask_above_v4_max_passes(
        self, validator: VirtualIPValidator, report: ValidationReport
    ) -> None:
        # 96 is fine for IPv6 (1-128) but rejected for IPv4 (1-32).
        validator.validate(
            [_ipalias("ok", address="2001:db8::1", network="96")],
            managed_interface_names={"lan"},
            existing_interfaces={},
        )
        assert not _failures(report, "virtual_ip_ok_network")

    def test_int_mask_accepted(
        self, validator: VirtualIPValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_ipalias("ok", network=24)],
            managed_interface_names={"lan"},
            existing_interfaces={},
        )
        assert not _failures(report, "virtual_ip_ok_network")

    def test_missing_network_fails(
        self, validator: VirtualIPValidator, report: ValidationReport
    ) -> None:
        r = ResourceConfig(
            name="bad",
            type="interfaces.virtual_ips",
            provider="opnsense",
            config={
                "mode": "ipalias",
                "interface": "lan",
                "address": "10.0.0.10",
            },
        )
        validator.validate(
            [r],
            managed_interface_names={"lan"},
            existing_interfaces={},
        )
        assert _failures(report, "virtual_ip_bad_network")

    def test_empty_network_fails(
        self, validator: VirtualIPValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_ipalias("bad", network="")],
            managed_interface_names={"lan"},
            existing_interfaces={},
        )
        assert _failures(report, "virtual_ip_bad_network")

    def test_non_numeric_network_fails(
        self, validator: VirtualIPValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_ipalias("bad", network="not-a-number")],
            managed_interface_names={"lan"},
            existing_interfaces={},
        )
        assert _failures(report, "virtual_ip_bad_network")

    def test_bool_network_fails(
        self, validator: VirtualIPValidator, report: ValidationReport
    ) -> None:
        # Booleans are subclass of int but explicitly rejected.
        validator.validate(
            [_ipalias("bad", network=True)],
            managed_interface_names={"lan"},
            existing_interfaces={},
        )
        assert _failures(report, "virtual_ip_bad_network")

    def test_v4_mask_above_32_fails(
        self, validator: VirtualIPValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_ipalias("bad", address="10.0.0.10", network="33")],
            managed_interface_names={"lan"},
            existing_interfaces={},
        )
        assert _failures(report, "virtual_ip_bad_network")

    def test_mask_zero_fails(self, validator: VirtualIPValidator, report: ValidationReport) -> None:
        validator.validate(
            [_ipalias("bad", network="0")],
            managed_interface_names={"lan"},
            existing_interfaces={},
        )
        assert _failures(report, "virtual_ip_bad_network")

    def test_v6_mask_above_128_fails(
        self, validator: VirtualIPValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_ipalias("bad", address="2001:db8::1", network="129")],
            managed_interface_names={"lan"},
            existing_interfaces={},
        )
        assert _failures(report, "virtual_ip_bad_network")


# ---------------------------------------------------------------------------
# CARP-required fields: vhid + password
# ---------------------------------------------------------------------------


class TestCarpVhid:
    def test_vhid_passes(self, validator: VirtualIPValidator, report: ValidationReport) -> None:
        validator.validate(
            [_carp("ok", vhid="42")],
            managed_interface_names={"lan"},
            existing_interfaces={},
        )
        assert not _failures(report, "virtual_ip_ok_vhid")

    def test_vhid_int_accepted(
        self, validator: VirtualIPValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_carp("ok", vhid=7)],
            managed_interface_names={"lan"},
            existing_interfaces={},
        )
        assert not _failures(report, "virtual_ip_ok_vhid")

    def test_missing_vhid_fails(
        self, validator: VirtualIPValidator, report: ValidationReport
    ) -> None:
        r = ResourceConfig(
            name="bad",
            type="interfaces.virtual_ips",
            provider="opnsense",
            config={
                "mode": "carp",
                "interface": "lan",
                "address": "10.0.0.1",
                "network": "24",
                "password": "secret://env_secrets/x/y",
            },
        )
        validator.validate(
            [r],
            managed_interface_names={"lan"},
            existing_interfaces={},
        )
        assert _failures(report, "virtual_ip_bad_vhid")

    def test_empty_vhid_fails(
        self, validator: VirtualIPValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_carp("bad", vhid="")],
            managed_interface_names={"lan"},
            existing_interfaces={},
        )
        assert _failures(report, "virtual_ip_bad_vhid")

    def test_non_numeric_vhid_fails(
        self, validator: VirtualIPValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_carp("bad", vhid="abc")],
            managed_interface_names={"lan"},
            existing_interfaces={},
        )
        assert _failures(report, "virtual_ip_bad_vhid")

    def test_vhid_below_min_fails(
        self, validator: VirtualIPValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_carp("bad", vhid="0")],
            managed_interface_names={"lan"},
            existing_interfaces={},
        )
        assert _failures(report, "virtual_ip_bad_vhid")

    def test_vhid_above_max_fails(
        self, validator: VirtualIPValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_carp("bad", vhid="256")],
            managed_interface_names={"lan"},
            existing_interfaces={},
        )
        assert _failures(report, "virtual_ip_bad_vhid")

    def test_bool_vhid_fails(self, validator: VirtualIPValidator, report: ValidationReport) -> None:
        validator.validate(
            [_carp("bad", vhid=True)],
            managed_interface_names={"lan"},
            existing_interfaces={},
        )
        assert _failures(report, "virtual_ip_bad_vhid")


class TestCarpPassword:
    def test_secret_uri_accepted_silently(
        self, validator: VirtualIPValidator, report: ValidationReport
    ) -> None:
        # Validator must not resolve the secret — that's apply-time.
        validator.validate(
            [_carp("ok", password="secret://env_secrets/opnsense/carp/lan_1")],
            managed_interface_names={"lan"},
            existing_interfaces={},
        )
        assert not _failures(report, "virtual_ip_ok_password")

    def test_plaintext_password_warns(
        self, validator: VirtualIPValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_carp("ok", password="hunter2")],
            managed_interface_names={"lan"},
            existing_interfaces={},
        )
        # Plaintext password is a soft warning, not an error.
        assert _warnings(report, "virtual_ip_ok_password")
        assert not _errors(report, "virtual_ip_ok_password")

    def test_missing_password_fails(
        self, validator: VirtualIPValidator, report: ValidationReport
    ) -> None:
        r = ResourceConfig(
            name="bad",
            type="interfaces.virtual_ips",
            provider="opnsense",
            config={
                "mode": "carp",
                "interface": "lan",
                "address": "10.0.0.1",
                "network": "24",
                "vhid": "1",
            },
        )
        validator.validate(
            [r],
            managed_interface_names={"lan"},
            existing_interfaces={},
        )
        assert _errors(report, "virtual_ip_bad_password")

    def test_empty_password_fails(
        self, validator: VirtualIPValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_carp("bad", password="")],
            managed_interface_names={"lan"},
            existing_interfaces={},
        )
        assert _errors(report, "virtual_ip_bad_password")

    def test_non_string_password_fails(
        self, validator: VirtualIPValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_carp("bad", password=123)],
            managed_interface_names={"lan"},
            existing_interfaces={},
        )
        assert _errors(report, "virtual_ip_bad_password")


# ---------------------------------------------------------------------------
# CARP optional fields: advbase / advskew / peer / peer6 / nosync
# ---------------------------------------------------------------------------


class TestCarpOptionalFields:
    def test_advbase_string_passes(
        self, validator: VirtualIPValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_carp("ok", advbase="2")],
            managed_interface_names={"lan"},
            existing_interfaces={},
        )
        assert not _failures(report, "virtual_ip_ok_advbase")

    def test_advbase_non_string_fails(
        self, validator: VirtualIPValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_carp("bad", advbase=2)],
            managed_interface_names={"lan"},
            existing_interfaces={},
        )
        assert _failures(report, "virtual_ip_bad_advbase")

    def test_advskew_non_string_fails(
        self, validator: VirtualIPValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_carp("bad", advskew=100)],
            managed_interface_names={"lan"},
            existing_interfaces={},
        )
        assert _failures(report, "virtual_ip_bad_advskew")

    def test_peer_v4_passes(self, validator: VirtualIPValidator, report: ValidationReport) -> None:
        validator.validate(
            [_carp("ok", peer="192.0.2.5")],
            managed_interface_names={"lan"},
            existing_interfaces={},
        )
        assert not _failures(report, "virtual_ip_ok_peer")

    def test_peer_empty_string_passes(
        self, validator: VirtualIPValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_carp("ok", peer="")],
            managed_interface_names={"lan"},
            existing_interfaces={},
        )
        assert not _failures(report, "virtual_ip_ok_peer")

    def test_peer_invalid_ip_fails(
        self, validator: VirtualIPValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_carp("bad", peer="not-an-ip")],
            managed_interface_names={"lan"},
            existing_interfaces={},
        )
        assert _failures(report, "virtual_ip_bad_peer")

    def test_peer_v6_in_v4_field_fails(
        self, validator: VirtualIPValidator, report: ValidationReport
    ) -> None:
        # peer is the IPv4 unicast peer; an IPv6 address there is wrong.
        validator.validate(
            [_carp("bad", peer="2001:db8::1")],
            managed_interface_names={"lan"},
            existing_interfaces={},
        )
        assert _failures(report, "virtual_ip_bad_peer")

    def test_peer_non_string_fails(
        self, validator: VirtualIPValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_carp("bad", peer=123)],
            managed_interface_names={"lan"},
            existing_interfaces={},
        )
        assert _failures(report, "virtual_ip_bad_peer")

    def test_peer6_v6_passes(self, validator: VirtualIPValidator, report: ValidationReport) -> None:
        validator.validate(
            [_carp("ok", peer6="2001:db8::5")],
            managed_interface_names={"lan"},
            existing_interfaces={},
        )
        assert not _failures(report, "virtual_ip_ok_peer6")

    def test_peer6_v4_in_v6_field_fails(
        self, validator: VirtualIPValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_carp("bad", peer6="192.0.2.5")],
            managed_interface_names={"lan"},
            existing_interfaces={},
        )
        assert _failures(report, "virtual_ip_bad_peer6")

    def test_nosync_bool_passes(
        self, validator: VirtualIPValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_carp("ok", nosync=True)],
            managed_interface_names={"lan"},
            existing_interfaces={},
        )
        assert not _failures(report, "virtual_ip_ok_nosync")

    def test_nosync_non_bool_fails(
        self, validator: VirtualIPValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_carp("bad", nosync="yes")],
            managed_interface_names={"lan"},
            existing_interfaces={},
        )
        assert _failures(report, "virtual_ip_bad_nosync")


# ---------------------------------------------------------------------------
# ipalias-only fields: gateway / noexpand / nobind
# ---------------------------------------------------------------------------


class TestIpaliasFields:
    def test_gateway_string_passes(
        self, validator: VirtualIPValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_ipalias("ok", gateway="WAN_DHCP")],
            managed_interface_names={"lan"},
            existing_interfaces={},
        )
        assert not _failures(report, "virtual_ip_ok_gateway")

    def test_gateway_empty_passes(
        self, validator: VirtualIPValidator, report: ValidationReport
    ) -> None:
        # Empty string is fine (default no-gateway).
        validator.validate(
            [_ipalias("ok", gateway="")],
            managed_interface_names={"lan"},
            existing_interfaces={},
        )
        assert not _failures(report, "virtual_ip_ok_gateway")

    def test_gateway_non_string_fails(
        self, validator: VirtualIPValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_ipalias("bad", gateway=123)],
            managed_interface_names={"lan"},
            existing_interfaces={},
        )
        assert _failures(report, "virtual_ip_bad_gateway")

    def test_noexpand_bool_passes(
        self, validator: VirtualIPValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_ipalias("ok", noexpand=True)],
            managed_interface_names={"lan"},
            existing_interfaces={},
        )
        assert not _failures(report, "virtual_ip_ok_noexpand")

    def test_noexpand_non_bool_fails(
        self, validator: VirtualIPValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_ipalias("bad", noexpand="yes")],
            managed_interface_names={"lan"},
            existing_interfaces={},
        )
        assert _failures(report, "virtual_ip_bad_noexpand")

    def test_nobind_non_bool_fails(
        self, validator: VirtualIPValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_ipalias("bad", nobind="0")],
            managed_interface_names={"lan"},
            existing_interfaces={},
        )
        assert _failures(report, "virtual_ip_bad_nobind")


# ---------------------------------------------------------------------------
# Mode-mismatched fields warn (not error)
# ---------------------------------------------------------------------------


class TestModeMismatchWarnings:
    def test_carp_only_field_on_ipalias_warns(
        self, validator: VirtualIPValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_ipalias("ok", vhid="5")],
            managed_interface_names={"lan"},
            existing_interfaces={},
        )
        warnings = _warnings(report, "virtual_ip_ok_vhid_mode_mismatch")
        assert warnings

    def test_carp_only_field_on_proxyarp_warns(
        self, validator: VirtualIPValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_proxyarp("ok", password="hunter2")],
            managed_interface_names={"lan"},
            existing_interfaces={},
        )
        # password warning fires whether mode is ipalias or proxyarp.
        warnings = _warnings(report, "virtual_ip_ok_password_mode_mismatch")
        assert warnings

    def test_ipalias_only_field_on_carp_warns(
        self, validator: VirtualIPValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_carp("ok", gateway="WAN_DHCP")],
            managed_interface_names={"lan"},
            existing_interfaces={},
        )
        warnings = _warnings(report, "virtual_ip_ok_gateway_mode_mismatch")
        assert warnings

    def test_ipalias_only_field_on_proxyarp_warns(
        self, validator: VirtualIPValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_proxyarp("ok", noexpand=True)],
            managed_interface_names={"lan"},
            existing_interfaces={},
        )
        warnings = _warnings(report, "virtual_ip_ok_noexpand_mode_mismatch")
        assert warnings

    def test_empty_mismatch_field_silent(
        self, validator: VirtualIPValidator, report: ValidationReport
    ) -> None:
        # Empty/false defaults shouldn't trigger a mismatch warning.
        validator.validate(
            [_ipalias("ok", vhid="", password="")],
            managed_interface_names={"lan"},
            existing_interfaces={},
        )
        assert not _warnings(report, "virtual_ip_ok_vhid_mode_mismatch")
        assert not _warnings(report, "virtual_ip_ok_password_mode_mismatch")


# ---------------------------------------------------------------------------
# Type checks: description / enabled / lock
# ---------------------------------------------------------------------------


class TestTypeChecks:
    def test_description_string_passes(
        self, validator: VirtualIPValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_ipalias("ok", description="LAN VIP")],
            managed_interface_names={"lan"},
            existing_interfaces={},
        )
        assert not _failures(report, "virtual_ip_ok_description")

    def test_description_non_string_fails(
        self, validator: VirtualIPValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_ipalias("bad", description=123)],
            managed_interface_names={"lan"},
            existing_interfaces={},
        )
        assert _failures(report, "virtual_ip_bad_description")

    def test_enabled_must_be_bool(
        self, validator: VirtualIPValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_ipalias("bad", enabled="yes")],
            managed_interface_names={"lan"},
            existing_interfaces={},
        )
        assert _failures(report, "virtual_ip_bad_enabled")

    def test_lock_must_be_bool(
        self, validator: VirtualIPValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_ipalias("bad", lock="yes")],
            managed_interface_names={"lan"},
            existing_interfaces={},
        )
        assert _failures(report, "virtual_ip_bad_lock")

    def test_enabled_true_passes(
        self, validator: VirtualIPValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_ipalias("ok", enabled=True)],
            managed_interface_names={"lan"},
            existing_interfaces={},
        )
        assert not _failures(report, "virtual_ip_ok_enabled")

    def test_lock_true_passes(
        self, validator: VirtualIPValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_ipalias("ok", lock=True)],
            managed_interface_names={"lan"},
            existing_interfaces={},
        )
        assert not _failures(report, "virtual_ip_ok_lock")


# ---------------------------------------------------------------------------
# Uniqueness: (interface, mode, address, vhid)
# ---------------------------------------------------------------------------


class TestUniqueness:
    def test_duplicate_full_tuple_fails(
        self, validator: VirtualIPValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [
                _carp("a", interface="lan", address="10.0.0.1", vhid="1"),
                _carp("b", interface="lan", address="10.0.0.1", vhid="1"),
            ],
            managed_interface_names={"lan"},
            existing_interfaces={},
        )
        assert _failures(report, "virtual_ip_b_uniqueness")

    def test_same_address_different_vhid_passes(
        self, validator: VirtualIPValidator, report: ValidationReport
    ) -> None:
        # Two CARP VIPs at the same interface+address with different
        # vhids is a valid dual-CARP setup.
        validator.validate(
            [
                _carp("a", interface="lan", address="10.0.0.1", vhid="1"),
                _carp("b", interface="lan", address="10.0.0.1", vhid="2"),
            ],
            managed_interface_names={"lan"},
            existing_interfaces={},
        )
        assert not _failures(report, "virtual_ip_b_uniqueness")
        assert not _failures(report, "virtual_ip_a_uniqueness")

    def test_same_address_different_interface_passes(
        self, validator: VirtualIPValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [
                _ipalias("a", interface="lan", address="10.0.0.10"),
                _ipalias("b", interface="opt1", address="10.0.0.10"),
            ],
            managed_interface_names={"lan", "opt1"},
            existing_interfaces={},
        )
        assert not _failures(report, "virtual_ip_b_uniqueness")

    def test_same_address_different_mode_passes(
        self, validator: VirtualIPValidator, report: ValidationReport
    ) -> None:
        # An ipalias and a CARP at the same address are distinct — the
        # natural-key tuple includes mode.
        validator.validate(
            [
                _ipalias("a", interface="lan", address="10.0.0.1"),
                _carp("b", interface="lan", address="10.0.0.1", vhid="1"),
            ],
            managed_interface_names={"lan"},
            existing_interfaces={},
        )
        assert not _failures(report, "virtual_ip_b_uniqueness")

    def test_different_addresses_pass(
        self, validator: VirtualIPValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [
                _ipalias("a", address="10.0.0.10"),
                _ipalias("b", address="10.0.0.11"),
            ],
            managed_interface_names={"lan"},
            existing_interfaces={},
        )
        assert not _failures(report, "virtual_ip_b_uniqueness")

    def test_duplicate_ipalias_fails(
        self, validator: VirtualIPValidator, report: ValidationReport
    ) -> None:
        # ipalias has empty vhid, so the tuple is
        # ("lan", "ipalias", "10.0.0.10", "") for both entries.
        validator.validate(
            [
                _ipalias("a", address="10.0.0.10"),
                _ipalias("b", address="10.0.0.10"),
            ],
            managed_interface_names={"lan"},
            existing_interfaces={},
        )
        assert _failures(report, "virtual_ip_b_uniqueness")


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_list_no_failures(
        self, validator: VirtualIPValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [],
            managed_interface_names=set(),
            existing_interfaces={},
        )
        assert report.results == []

    def test_multiple_resources_all_validated(
        self, validator: VirtualIPValidator, report: ValidationReport
    ) -> None:
        # Three resources of different modes — every one should produce
        # at least an interface check (no short-circuit on first failure).
        validator.validate(
            [
                _ipalias("a"),
                _carp("b", address="10.0.0.2", vhid="2"),
                _proxyarp("c"),
            ],
            managed_interface_names={"lan"},
            existing_interfaces={},
        )
        names = {c.check_name for c in report.results if c.check_name.endswith("_interface")}
        assert "virtual_ip_a_interface" in names
        assert "virtual_ip_b_interface" in names
        assert "virtual_ip_c_interface" in names

    def test_invalid_mode_skips_per_mode_branch(
        self, validator: VirtualIPValidator, report: ValidationReport
    ) -> None:
        # When mode is invalid, per-mode required-field branches are
        # skipped — the operator first needs to fix the mode.
        validator.validate(
            [_ipalias("bad", mode="bogus")],
            managed_interface_names={"lan"},
            existing_interfaces={},
        )
        # password / vhid / gateway / noexpand checks must NOT have run.
        assert not _failures(report, "virtual_ip_bad_password")
        assert not _failures(report, "virtual_ip_bad_vhid")

    def test_invalid_mode_still_validates_address(
        self, validator: VirtualIPValidator, report: ValidationReport
    ) -> None:
        # Address validation runs regardless of mode validity.
        validator.validate(
            [_ipalias("bad", mode="bogus", address="not-an-ip")],
            managed_interface_names={"lan"},
            existing_interfaces={},
        )
        assert _failures(report, "virtual_ip_bad_address")
