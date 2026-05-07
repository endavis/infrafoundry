"""Unit tests for ``UnboundHostOverrideValidator`` (#776).

Coverage:
    - ``hostname`` / ``domain`` required, non-empty string checks.
    - ``rr`` field: optional with default A; one of A/AAAA/MX.
    - ``server`` field-shape:
        - empty string allowed across rr types.
        - rr=A requires IPv4 when non-empty.
        - rr=AAAA requires IPv6 when non-empty.
        - rr=MX server is optional.
        - non-string rejected.
        - malformed IP rejected.
    - ``mxprio`` for MX records: required, numeric string, range 0-65535.
    - ``mx`` for MX records: required.
    - Bool type checks: ``enabled``, ``lock``.
    - ``description`` type check.
    - Uniqueness of ``(hostname, domain, rr)`` tuples within YAML —
      A and AAAA on the same hostname/domain are NOT duplicates.
"""

from __future__ import annotations

from typing import Any

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationReport
from infrafoundry.providers.opnsense.validators.unbound_host_override_validator import (
    UnboundHostOverrideValidator,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _override(name: str, **overrides: Any) -> ResourceConfig:
    config: dict[str, Any] = {
        "hostname": "web",
        "domain": "example.com",
        "server": "192.168.1.10",
    }
    config.update(overrides)
    return ResourceConfig(
        name=name, type="unbound_host_override", provider="opnsense", config=config
    )


@pytest.fixture
def report() -> ValidationReport:
    return ValidationReport()


@pytest.fixture
def validator(report: ValidationReport) -> UnboundHostOverrideValidator:
    return UnboundHostOverrideValidator(report)


def _failures(report: ValidationReport, check_name: str) -> list[Any]:
    return [c for c in report.results if c.check_name == check_name and not c.passed]


# ---------------------------------------------------------------------------
# hostname / domain (required)
# ---------------------------------------------------------------------------


class TestHostnameDomain:
    def test_valid_a_record_accepted(
        self, validator: UnboundHostOverrideValidator, report: ValidationReport
    ) -> None:
        validator.validate([_override("ok")])
        assert not _failures(report, "unbound_host_override_ok_hostname")
        assert not _failures(report, "unbound_host_override_ok_domain")

    def test_missing_hostname_rejected(
        self, validator: UnboundHostOverrideValidator, report: ValidationReport
    ) -> None:
        r = ResourceConfig(
            name="bad",
            type="unbound_host_override",
            provider="opnsense",
            config={"domain": "example.com"},
        )
        validator.validate([r])
        assert _failures(report, "unbound_host_override_bad_hostname")

    def test_empty_hostname_rejected(
        self, validator: UnboundHostOverrideValidator, report: ValidationReport
    ) -> None:
        validator.validate([_override("bad", hostname="")])
        assert _failures(report, "unbound_host_override_bad_hostname")

    def test_non_string_hostname_rejected(
        self, validator: UnboundHostOverrideValidator, report: ValidationReport
    ) -> None:
        validator.validate([_override("bad", hostname=12345)])
        assert _failures(report, "unbound_host_override_bad_hostname")

    def test_missing_domain_rejected(
        self, validator: UnboundHostOverrideValidator, report: ValidationReport
    ) -> None:
        r = ResourceConfig(
            name="bad",
            type="unbound_host_override",
            provider="opnsense",
            config={"hostname": "web"},
        )
        validator.validate([r])
        assert _failures(report, "unbound_host_override_bad_domain")

    def test_empty_domain_rejected(
        self, validator: UnboundHostOverrideValidator, report: ValidationReport
    ) -> None:
        validator.validate([_override("bad", domain="")])
        assert _failures(report, "unbound_host_override_bad_domain")


# ---------------------------------------------------------------------------
# rr
# ---------------------------------------------------------------------------


class TestRR:
    def test_default_rr_a_accepted(
        self, validator: UnboundHostOverrideValidator, report: ValidationReport
    ) -> None:
        validator.validate([_override("ok")])
        assert not _failures(report, "unbound_host_override_ok_rr")

    def test_explicit_rr_a_accepted(
        self, validator: UnboundHostOverrideValidator, report: ValidationReport
    ) -> None:
        validator.validate([_override("ok", rr="A")])
        assert not _failures(report, "unbound_host_override_ok_rr")

    def test_rr_aaaa_accepted(
        self, validator: UnboundHostOverrideValidator, report: ValidationReport
    ) -> None:
        validator.validate([_override("ok", rr="AAAA", server="2001:db8::10")])
        assert not _failures(report, "unbound_host_override_ok_rr")

    def test_rr_mx_accepted(
        self, validator: UnboundHostOverrideValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [
                _override(
                    "ok",
                    rr="MX",
                    server="",
                    mxprio="10",
                    mx="mail.example.com",
                )
            ]
        )
        assert not _failures(report, "unbound_host_override_ok_rr")

    def test_invalid_rr_rejected(
        self, validator: UnboundHostOverrideValidator, report: ValidationReport
    ) -> None:
        validator.validate([_override("bad", rr="CNAME")])
        assert _failures(report, "unbound_host_override_bad_rr")

    def test_non_string_rr_rejected(
        self, validator: UnboundHostOverrideValidator, report: ValidationReport
    ) -> None:
        validator.validate([_override("bad", rr=123)])
        assert _failures(report, "unbound_host_override_bad_rr")


# ---------------------------------------------------------------------------
# server (rr-specific)
# ---------------------------------------------------------------------------


class TestServer:
    def test_a_record_with_ipv4_accepted(
        self, validator: UnboundHostOverrideValidator, report: ValidationReport
    ) -> None:
        validator.validate([_override("ok", rr="A", server="192.168.1.10")])
        assert not _failures(report, "unbound_host_override_ok_server")

    def test_a_record_with_ipv6_rejected(
        self, validator: UnboundHostOverrideValidator, report: ValidationReport
    ) -> None:
        validator.validate([_override("bad", rr="A", server="2001:db8::10")])
        assert _failures(report, "unbound_host_override_bad_server")

    def test_aaaa_record_with_ipv6_accepted(
        self, validator: UnboundHostOverrideValidator, report: ValidationReport
    ) -> None:
        validator.validate([_override("ok", rr="AAAA", server="2001:db8::10")])
        assert not _failures(report, "unbound_host_override_ok_server")

    def test_aaaa_record_with_ipv4_rejected(
        self, validator: UnboundHostOverrideValidator, report: ValidationReport
    ) -> None:
        validator.validate([_override("bad", rr="AAAA", server="192.168.1.10")])
        assert _failures(report, "unbound_host_override_bad_server")

    def test_mx_record_with_no_server_accepted(
        self, validator: UnboundHostOverrideValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [
                _override(
                    "ok",
                    rr="MX",
                    server="",
                    mxprio="10",
                    mx="mail.example.com",
                )
            ]
        )
        assert not _failures(report, "unbound_host_override_ok_server")

    def test_empty_server_accepted_for_a(
        self, validator: UnboundHostOverrideValidator, report: ValidationReport
    ) -> None:
        validator.validate([_override("ok", server="")])
        assert not _failures(report, "unbound_host_override_ok_server")

    def test_malformed_ip_rejected(
        self, validator: UnboundHostOverrideValidator, report: ValidationReport
    ) -> None:
        validator.validate([_override("bad", server="not-an-ip")])
        assert _failures(report, "unbound_host_override_bad_server")

    def test_non_string_server_rejected(
        self, validator: UnboundHostOverrideValidator, report: ValidationReport
    ) -> None:
        validator.validate([_override("bad", server=12345)])
        assert _failures(report, "unbound_host_override_bad_server")


# ---------------------------------------------------------------------------
# mxprio / mx (MX-only)
# ---------------------------------------------------------------------------


class TestMXFields:
    def test_mx_record_with_valid_mxprio_and_mx_accepted(
        self, validator: UnboundHostOverrideValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [
                _override(
                    "ok",
                    rr="MX",
                    server="",
                    mxprio="10",
                    mx="mail.example.com",
                )
            ]
        )
        assert not _failures(report, "unbound_host_override_ok_mxprio")
        assert not _failures(report, "unbound_host_override_ok_mx")

    def test_mx_record_missing_mxprio_rejected(
        self, validator: UnboundHostOverrideValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [
                _override(
                    "bad",
                    rr="MX",
                    server="",
                    mx="mail.example.com",
                )
            ]
        )
        assert _failures(report, "unbound_host_override_bad_mxprio")

    def test_mx_record_empty_mxprio_rejected(
        self, validator: UnboundHostOverrideValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [
                _override(
                    "bad",
                    rr="MX",
                    server="",
                    mxprio="",
                    mx="mail.example.com",
                )
            ]
        )
        assert _failures(report, "unbound_host_override_bad_mxprio")

    def test_mx_record_non_numeric_mxprio_rejected(
        self, validator: UnboundHostOverrideValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [
                _override(
                    "bad",
                    rr="MX",
                    server="",
                    mxprio="ten",
                    mx="mail.example.com",
                )
            ]
        )
        assert _failures(report, "unbound_host_override_bad_mxprio")

    def test_mx_record_non_string_mxprio_rejected(
        self, validator: UnboundHostOverrideValidator, report: ValidationReport
    ) -> None:
        # mxprio is preserved as string for numeric precision; integers
        # are explicitly rejected.
        validator.validate(
            [
                _override(
                    "bad",
                    rr="MX",
                    server="",
                    mxprio=10,
                    mx="mail.example.com",
                )
            ]
        )
        assert _failures(report, "unbound_host_override_bad_mxprio")

    def test_mx_record_out_of_range_mxprio_rejected(
        self, validator: UnboundHostOverrideValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [
                _override(
                    "bad",
                    rr="MX",
                    server="",
                    mxprio="99999",
                    mx="mail.example.com",
                )
            ]
        )
        assert _failures(report, "unbound_host_override_bad_mxprio")

    def test_mx_record_missing_mx_rejected(
        self, validator: UnboundHostOverrideValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [
                _override(
                    "bad",
                    rr="MX",
                    server="",
                    mxprio="10",
                )
            ]
        )
        assert _failures(report, "unbound_host_override_bad_mx")

    def test_mx_record_empty_mx_rejected(
        self, validator: UnboundHostOverrideValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [
                _override(
                    "bad",
                    rr="MX",
                    server="",
                    mxprio="10",
                    mx="",
                )
            ]
        )
        assert _failures(report, "unbound_host_override_bad_mx")

    def test_a_record_with_mxprio_no_validation(
        self, validator: UnboundHostOverrideValidator, report: ValidationReport
    ) -> None:
        # mxprio on an A record is silently ignored by the validator
        # (the parser preserves it but the wire payload sets ``mxprio: ""``
        # for non-MX records).
        validator.validate([_override("ok", rr="A", mxprio="10", mx="mail.example.com")])
        assert not _failures(report, "unbound_host_override_ok_mxprio")


# ---------------------------------------------------------------------------
# uniqueness
# ---------------------------------------------------------------------------


class TestUniqueness:
    def test_two_records_with_same_tuple_rejected(
        self, validator: UnboundHostOverrideValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [
                _override("first"),
                _override("second"),  # same hostname/domain/rr default
            ]
        )
        assert _failures(report, "unbound_host_override_second_uniqueness")

    def test_a_and_aaaa_same_hostname_no_collision(
        self, validator: UnboundHostOverrideValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [
                _override("v4", rr="A", server="192.168.1.10"),
                _override("v6", rr="AAAA", server="2001:db8::10"),
            ]
        )
        # Different rr type → different tuples → no uniqueness collision.
        assert not _failures(report, "unbound_host_override_v6_uniqueness")

    def test_different_hostname_no_collision(
        self, validator: UnboundHostOverrideValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [
                _override("first", hostname="web"),
                _override("second", hostname="db"),
            ]
        )
        assert not _failures(report, "unbound_host_override_second_uniqueness")

    def test_different_domain_no_collision(
        self, validator: UnboundHostOverrideValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [
                _override("first", domain="example.com"),
                _override("second", domain="other.com"),
            ]
        )
        assert not _failures(report, "unbound_host_override_second_uniqueness")


# ---------------------------------------------------------------------------
# bool fields
# ---------------------------------------------------------------------------


class TestBoolFields:
    def test_enabled_bool_accepted(
        self, validator: UnboundHostOverrideValidator, report: ValidationReport
    ) -> None:
        validator.validate([_override("ok", enabled=False)])
        assert not _failures(report, "unbound_host_override_ok_enabled")

    def test_enabled_non_bool_rejected(
        self, validator: UnboundHostOverrideValidator, report: ValidationReport
    ) -> None:
        validator.validate([_override("bad", enabled="yes")])
        assert _failures(report, "unbound_host_override_bad_enabled")

    def test_lock_bool_accepted(
        self, validator: UnboundHostOverrideValidator, report: ValidationReport
    ) -> None:
        validator.validate([_override("ok", lock=True)])
        assert not _failures(report, "unbound_host_override_ok_lock")

    def test_lock_non_bool_rejected(
        self, validator: UnboundHostOverrideValidator, report: ValidationReport
    ) -> None:
        validator.validate([_override("bad", lock="yes")])
        assert _failures(report, "unbound_host_override_bad_lock")


# ---------------------------------------------------------------------------
# description
# ---------------------------------------------------------------------------


class TestDescription:
    def test_description_string_accepted(
        self, validator: UnboundHostOverrideValidator, report: ValidationReport
    ) -> None:
        validator.validate([_override("ok", description="primary web")])
        assert not _failures(report, "unbound_host_override_ok_description")

    def test_description_non_string_rejected(
        self, validator: UnboundHostOverrideValidator, report: ValidationReport
    ) -> None:
        validator.validate([_override("bad", description=12345)])
        assert _failures(report, "unbound_host_override_bad_description")
