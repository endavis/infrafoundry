"""Unit tests for ``UnboundForwardValidator``.

Coverage:
    - ``type`` enum: ``forward`` / ``dot`` accepted; default; invalid value
      and non-string rejected.
    - ``domain`` field: empty allowed (global forwarder); non-string rejected.
    - ``server`` field: required; valid IPv4 / IPv6 accepted; missing /
      empty / non-string / malformed-IP rejected.
    - ``port`` field: optional; defaults to 53; range 1-65535 enforced;
      bool / non-int-or-string rejected.
    - ``verify`` field: optional string.
    - Bool type checks: ``forward_tcp_upstream``, ``forward_first``,
      ``enabled``, ``lock``.
    - ``description`` type check.
    - Uniqueness of ``(type, domain, server, port)`` tuples within YAML.
"""

from __future__ import annotations

from typing import Any

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationReport
from infrafoundry.providers.opnsense.validators.unbound_forward_validator import (
    UnboundForwardValidator,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _forward(name: str, **overrides: Any) -> ResourceConfig:
    config: dict[str, Any] = {
        "server": "10.0.0.53",
    }
    config.update(overrides)
    return ResourceConfig(name=name, type="unbound.forwards", provider="opnsense", config=config)


@pytest.fixture
def report() -> ValidationReport:
    return ValidationReport()


@pytest.fixture
def validator(report: ValidationReport) -> UnboundForwardValidator:
    return UnboundForwardValidator(report)


def _failures(report: ValidationReport, check_name: str) -> list[Any]:
    return [c for c in report.results if c.check_name == check_name and not c.passed]


# ---------------------------------------------------------------------------
# type
# ---------------------------------------------------------------------------


class TestType:
    def test_default_passes(
        self, validator: UnboundForwardValidator, report: ValidationReport
    ) -> None:
        validator.validate([_forward("ok")])
        assert not _failures(report, "unbound_forward_ok_type")

    def test_forward_accepted(
        self, validator: UnboundForwardValidator, report: ValidationReport
    ) -> None:
        validator.validate([_forward("ok", type="forward")])
        assert not _failures(report, "unbound_forward_ok_type")

    def test_dot_accepted(
        self, validator: UnboundForwardValidator, report: ValidationReport
    ) -> None:
        validator.validate([_forward("ok", type="dot")])
        assert not _failures(report, "unbound_forward_ok_type")

    def test_invalid_type_rejected(
        self, validator: UnboundForwardValidator, report: ValidationReport
    ) -> None:
        validator.validate([_forward("bad", type="bogus")])
        assert _failures(report, "unbound_forward_bad_type")

    def test_non_string_type_rejected(
        self, validator: UnboundForwardValidator, report: ValidationReport
    ) -> None:
        validator.validate([_forward("bad", type=12345)])
        assert _failures(report, "unbound_forward_bad_type")


# ---------------------------------------------------------------------------
# domain
# ---------------------------------------------------------------------------


class TestDomain:
    def test_empty_allowed_global(
        self, validator: UnboundForwardValidator, report: ValidationReport
    ) -> None:
        validator.validate([_forward("ok", domain="")])
        assert not _failures(report, "unbound_forward_ok_domain")

    def test_missing_allowed(
        self, validator: UnboundForwardValidator, report: ValidationReport
    ) -> None:
        # ``domain`` is optional — missing is fine (defaults to empty).
        r = ResourceConfig(
            name="ok",
            type="unbound.forwards",
            provider="opnsense",
            config={"server": "10.0.0.53"},
        )
        validator.validate([r])
        assert not _failures(report, "unbound_forward_ok_domain")

    def test_string_passes(
        self, validator: UnboundForwardValidator, report: ValidationReport
    ) -> None:
        validator.validate([_forward("ok", domain="corp.example")])
        assert not _failures(report, "unbound_forward_ok_domain")

    def test_non_string_rejected(
        self, validator: UnboundForwardValidator, report: ValidationReport
    ) -> None:
        validator.validate([_forward("bad", domain=12345)])
        assert _failures(report, "unbound_forward_bad_domain")


# ---------------------------------------------------------------------------
# server (IP)
# ---------------------------------------------------------------------------


class TestServer:
    def test_v4_passes(self, validator: UnboundForwardValidator, report: ValidationReport) -> None:
        validator.validate([_forward("ok", server="10.0.0.53")])
        assert not _failures(report, "unbound_forward_ok_server")

    def test_v6_passes(self, validator: UnboundForwardValidator, report: ValidationReport) -> None:
        validator.validate([_forward("ok", server="2001:db8::53")])
        assert not _failures(report, "unbound_forward_ok_server")

    def test_missing_rejected(
        self, validator: UnboundForwardValidator, report: ValidationReport
    ) -> None:
        r = ResourceConfig(
            name="bad",
            type="unbound.forwards",
            provider="opnsense",
            config={"domain": "x"},
        )
        validator.validate([r])
        assert _failures(report, "unbound_forward_bad_server")

    def test_empty_rejected(
        self, validator: UnboundForwardValidator, report: ValidationReport
    ) -> None:
        validator.validate([_forward("bad", server="")])
        assert _failures(report, "unbound_forward_bad_server")

    def test_non_string_rejected(
        self, validator: UnboundForwardValidator, report: ValidationReport
    ) -> None:
        validator.validate([_forward("bad", server=12345)])
        assert _failures(report, "unbound_forward_bad_server")

    def test_malformed_ip_rejected(
        self, validator: UnboundForwardValidator, report: ValidationReport
    ) -> None:
        validator.validate([_forward("bad", server="not-an-ip")])
        assert _failures(report, "unbound_forward_bad_server")

    def test_hostname_rejected(
        self, validator: UnboundForwardValidator, report: ValidationReport
    ) -> None:
        # OPNsense's wire shape is an IP address; hostnames are not accepted.
        validator.validate([_forward("bad", server="dns.example.com")])
        assert _failures(report, "unbound_forward_bad_server")


# ---------------------------------------------------------------------------
# port
# ---------------------------------------------------------------------------


class TestPort:
    def test_default_passes(
        self, validator: UnboundForwardValidator, report: ValidationReport
    ) -> None:
        validator.validate([_forward("ok")])
        assert not _failures(report, "unbound_forward_ok_port")

    def test_int_passes(self, validator: UnboundForwardValidator, report: ValidationReport) -> None:
        validator.validate([_forward("ok", port=853)])
        assert not _failures(report, "unbound_forward_ok_port")

    def test_string_of_int_passes(
        self, validator: UnboundForwardValidator, report: ValidationReport
    ) -> None:
        validator.validate([_forward("ok", port="853")])
        assert not _failures(report, "unbound_forward_ok_port")

    def test_zero_rejected(
        self, validator: UnboundForwardValidator, report: ValidationReport
    ) -> None:
        validator.validate([_forward("bad", port=0)])
        assert _failures(report, "unbound_forward_bad_port")

    def test_too_high_rejected(
        self, validator: UnboundForwardValidator, report: ValidationReport
    ) -> None:
        validator.validate([_forward("bad", port=70000)])
        assert _failures(report, "unbound_forward_bad_port")

    def test_negative_rejected(
        self, validator: UnboundForwardValidator, report: ValidationReport
    ) -> None:
        validator.validate([_forward("bad", port=-1)])
        assert _failures(report, "unbound_forward_bad_port")

    def test_non_numeric_string_rejected(
        self, validator: UnboundForwardValidator, report: ValidationReport
    ) -> None:
        validator.validate([_forward("bad", port="abc")])
        assert _failures(report, "unbound_forward_bad_port")

    def test_bool_rejected(
        self, validator: UnboundForwardValidator, report: ValidationReport
    ) -> None:
        # ``True`` / ``False`` are technically ints in Python; the validator
        # rejects bool to avoid silent default-port failures.
        validator.validate([_forward("bad", port=True)])
        assert _failures(report, "unbound_forward_bad_port")

    def test_other_type_rejected(
        self, validator: UnboundForwardValidator, report: ValidationReport
    ) -> None:
        validator.validate([_forward("bad", port=[53])])
        assert _failures(report, "unbound_forward_bad_port")


# ---------------------------------------------------------------------------
# verify
# ---------------------------------------------------------------------------


class TestVerify:
    def test_string_passes(
        self, validator: UnboundForwardValidator, report: ValidationReport
    ) -> None:
        validator.validate([_forward("ok", verify="dns.quad9.net")])
        assert not _failures(report, "unbound_forward_ok_verify")

    def test_empty_string_passes(
        self, validator: UnboundForwardValidator, report: ValidationReport
    ) -> None:
        validator.validate([_forward("ok", verify="")])
        assert not _failures(report, "unbound_forward_ok_verify")

    def test_non_string_rejected(
        self, validator: UnboundForwardValidator, report: ValidationReport
    ) -> None:
        validator.validate([_forward("bad", verify=12345)])
        assert _failures(report, "unbound_forward_bad_verify")


# ---------------------------------------------------------------------------
# bool type checks
# ---------------------------------------------------------------------------


class TestBoolFields:
    def test_forward_tcp_upstream_must_be_bool(
        self, validator: UnboundForwardValidator, report: ValidationReport
    ) -> None:
        validator.validate([_forward("bad", forward_tcp_upstream="yes")])
        assert _failures(report, "unbound_forward_bad_forward_tcp_upstream")

    def test_forward_first_must_be_bool(
        self, validator: UnboundForwardValidator, report: ValidationReport
    ) -> None:
        validator.validate([_forward("bad", forward_first="yes")])
        assert _failures(report, "unbound_forward_bad_forward_first")

    def test_enabled_must_be_bool(
        self, validator: UnboundForwardValidator, report: ValidationReport
    ) -> None:
        validator.validate([_forward("bad", enabled="yes")])
        assert _failures(report, "unbound_forward_bad_enabled")

    def test_lock_must_be_bool(
        self, validator: UnboundForwardValidator, report: ValidationReport
    ) -> None:
        validator.validate([_forward("bad", lock="yes")])
        assert _failures(report, "unbound_forward_bad_lock")

    def test_enabled_true_passes(
        self, validator: UnboundForwardValidator, report: ValidationReport
    ) -> None:
        validator.validate([_forward("ok", enabled=True)])
        assert not _failures(report, "unbound_forward_ok_enabled")

    def test_lock_true_passes(
        self, validator: UnboundForwardValidator, report: ValidationReport
    ) -> None:
        validator.validate([_forward("ok", lock=True)])
        assert not _failures(report, "unbound_forward_ok_lock")


# ---------------------------------------------------------------------------
# description
# ---------------------------------------------------------------------------


class TestDescription:
    def test_string_passes(
        self, validator: UnboundForwardValidator, report: ValidationReport
    ) -> None:
        validator.validate([_forward("ok", description="my description")])
        assert not _failures(report, "unbound_forward_ok_description")

    def test_non_string_fails(
        self, validator: UnboundForwardValidator, report: ValidationReport
    ) -> None:
        validator.validate([_forward("bad", description=12345)])
        assert _failures(report, "unbound_forward_bad_description")


# ---------------------------------------------------------------------------
# uniqueness
# ---------------------------------------------------------------------------


class TestUniqueness:
    def test_distinct_tuples_pass(
        self, validator: UnboundForwardValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [
                _forward("a", server="10.0.0.53"),
                _forward("b", server="10.0.0.54"),
            ]
        )
        assert not _failures(report, "unbound_forward_a_uniqueness")
        assert not _failures(report, "unbound_forward_b_uniqueness")

    def test_duplicate_tuple_rejected(
        self, validator: UnboundForwardValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [
                _forward("first", server="10.0.0.53"),
                _forward("dup", server="10.0.0.53"),
            ]
        )
        assert _failures(report, "unbound_forward_dup_uniqueness")

    def test_same_server_different_type_passes(
        self, validator: UnboundForwardValidator, report: ValidationReport
    ) -> None:
        # Type is part of the identity tuple — same domain/server/port with
        # different type is a distinct record (DoT + plain coexistence).
        validator.validate(
            [
                _forward("a", type="forward", server="9.9.9.9"),
                _forward("b", type="dot", server="9.9.9.9"),
            ]
        )
        assert not _failures(report, "unbound_forward_b_uniqueness")

    def test_same_server_different_port_passes(
        self, validator: UnboundForwardValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [
                _forward("a", server="9.9.9.9", port=53),
                _forward("b", server="9.9.9.9", port=853),
            ]
        )
        assert not _failures(report, "unbound_forward_b_uniqueness")


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_list_no_failures(
        self, validator: UnboundForwardValidator, report: ValidationReport
    ) -> None:
        validator.validate([])
        assert report.results == []

    def test_multiple_forwards_all_validated(
        self, validator: UnboundForwardValidator, report: ValidationReport
    ) -> None:
        # All three entries have bad IPs — confirms the validator iterates
        # every entry rather than short-circuiting on the first failure.
        validator.validate(
            [
                _forward("a", server="not-an-ip-1"),
                _forward("b", server="not-an-ip-2"),
                _forward("c", server="not-an-ip-3"),
            ]
        )
        names = {c.check_name for c in report.results if c.check_name.endswith("_server")}
        assert "unbound_forward_a_server" in names
        assert "unbound_forward_b_server" in names
        assert "unbound_forward_c_server" in names
