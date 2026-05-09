"""Unit tests for ``KeaReservationValidator`` (#802).

Coverage:
    - ``subnet_ref`` resolves to a managed v4 / v6 subnet (bare-name and
      dotted-path forms).
    - Unknown ``subnet_ref`` for v4 / v6 surfaces a clear error.
    - Wrong-version cross (v4 reservation referencing v6 subnet, and the
      reverse) surfaces a wrong-version error rather than a vague
      "unknown" one.
    - Legacy ``subnet:`` literal-only form continues to pass.
    - Both fields absent surfaces an error.
    - Both fields present and agreeing on the resolved CIDR pass.
    - Both fields present and disagreeing surface an error.
    - Malformed CIDR literal surfaces an error.
    - Wrong-family CIDR literal (IPv6 written into a v4 reservation)
      surfaces an error.
"""

from __future__ import annotations

from typing import Any

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.opnsense.validators._xref import build_xref_index
from infrafoundry.providers.opnsense.validators.kea_reservation_validator import (
    KeaReservationValidator,
)

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _v4_reservation(name: str, **overrides: Any) -> ResourceConfig:
    """Build a ``kea.dhcp4.reservations`` resource with sensible defaults."""
    config: dict[str, Any] = {
        "hw_address": "aa:bb:cc:dd:ee:01",
        "ip_address": "10.0.10.50",
        "hostname": name,
    }
    config.update(overrides)
    return ResourceConfig(
        name=name,
        type="kea.dhcp4.reservations",
        provider="opnsense",
        config=config,
    )


def _v6_reservation(name: str, **overrides: Any) -> ResourceConfig:
    """Build a ``kea.dhcp6.reservations`` resource with sensible defaults."""
    config: dict[str, Any] = {
        "duid": "00:01:00:01:2c:3d:00:01",
        "ip_address": "fd00:1::10",
        "hostname": name,
    }
    config.update(overrides)
    return ResourceConfig(
        name=name,
        type="kea.dhcp6.reservations",
        provider="opnsense",
        config=config,
    )


def _v4_subnet(name: str, *, subnet: str = "10.0.10.0/24") -> ResourceConfig:
    return ResourceConfig(
        name=name,
        type="kea.dhcp4.subnets",
        provider="opnsense",
        config={"subnet": subnet},
    )


def _v6_subnet(name: str, *, subnet: str = "fd00:1::/64") -> ResourceConfig:
    return ResourceConfig(
        name=name,
        type="kea.dhcp6.subnets",
        provider="opnsense",
        config={"subnet": subnet},
    )


@pytest.fixture
def report() -> ValidationReport:
    return ValidationReport()


@pytest.fixture
def validator(report: ValidationReport) -> KeaReservationValidator:
    return KeaReservationValidator(report)


def _failures(report: ValidationReport, check_name: str) -> list[Any]:
    return [
        c
        for c in report.results
        if c.check_name == check_name and not c.passed and c.level == ValidationLevel.ERROR
    ]


def _passes(report: ValidationReport, check_name: str) -> list[Any]:
    return [c for c in report.results if c.check_name == check_name and c.passed]


# ---------------------------------------------------------------------------
# subnet_ref resolution — v4
# ---------------------------------------------------------------------------


class TestSubnetRefV4:
    def test_subnet_ref_resolves_to_managed_v4_subnet(
        self, validator: KeaReservationValidator, report: ValidationReport
    ) -> None:
        v4_subnet = _v4_subnet("lan-dhcp", subnet="10.0.10.0/24")
        reservation = _v4_reservation("server1", subnet_ref="lan-dhcp")
        index = build_xref_index([v4_subnet, reservation])
        validator.validate(
            dhcp4_reservations=[reservation],
            dhcp6_reservations=[],
            dhcp4_subnet_names={"lan-dhcp"},
            dhcp6_subnet_names=set(),
            index=index,
        )
        assert not _failures(report, "kea_reservation_server1_subnet")
        assert _passes(report, "kea_reservation_server1_subnet")

    def test_subnet_ref_unknown_v4_emits_error(
        self, validator: KeaReservationValidator, report: ValidationReport
    ) -> None:
        v4_subnet = _v4_subnet("lan-dhcp", subnet="10.0.10.0/24")
        reservation = _v4_reservation("server1", subnet_ref="missing-subnet")
        index = build_xref_index([v4_subnet, reservation])
        validator.validate(
            dhcp4_reservations=[reservation],
            dhcp6_reservations=[],
            dhcp4_subnet_names={"lan-dhcp"},
            dhcp6_subnet_names=set(),
            index=index,
        )
        failures = _failures(report, "kea_reservation_server1_subnet")
        assert failures, "Expected ERROR for unknown subnet_ref"
        assert "missing-subnet" in failures[0].message
        assert "unknown" in failures[0].message.lower()


# ---------------------------------------------------------------------------
# subnet_ref resolution — v6
# ---------------------------------------------------------------------------


class TestSubnetRefV6:
    def test_subnet_ref_resolves_to_managed_v6_subnet(
        self, validator: KeaReservationValidator, report: ValidationReport
    ) -> None:
        v6_subnet = _v6_subnet("lan-dhcp6", subnet="fd00:1::/64")
        reservation = _v6_reservation("server1-v6", subnet_ref="lan-dhcp6")
        index = build_xref_index([v6_subnet, reservation])
        validator.validate(
            dhcp4_reservations=[],
            dhcp6_reservations=[reservation],
            dhcp4_subnet_names=set(),
            dhcp6_subnet_names={"lan-dhcp6"},
            index=index,
        )
        assert not _failures(report, "kea_reservation_server1-v6_subnet")
        assert _passes(report, "kea_reservation_server1-v6_subnet")

    def test_subnet_ref_unknown_v6_emits_error(
        self, validator: KeaReservationValidator, report: ValidationReport
    ) -> None:
        v6_subnet = _v6_subnet("lan-dhcp6", subnet="fd00:1::/64")
        reservation = _v6_reservation("server1-v6", subnet_ref="not-a-subnet")
        index = build_xref_index([v6_subnet, reservation])
        validator.validate(
            dhcp4_reservations=[],
            dhcp6_reservations=[reservation],
            dhcp4_subnet_names=set(),
            dhcp6_subnet_names={"lan-dhcp6"},
            index=index,
        )
        failures = _failures(report, "kea_reservation_server1-v6_subnet")
        assert failures, "Expected ERROR for unknown subnet_ref"
        assert "not-a-subnet" in failures[0].message


# ---------------------------------------------------------------------------
# Wrong-version cross-references
# ---------------------------------------------------------------------------


class TestWrongVersionCross:
    def test_v4_reservation_subnet_ref_pointing_at_v6_subnet_errors(
        self, validator: KeaReservationValidator, report: ValidationReport
    ) -> None:
        v6_subnet = _v6_subnet("guest", subnet="fd00:1::/64")
        reservation = _v4_reservation("server1", subnet_ref="guest")
        index = build_xref_index([v6_subnet, reservation])
        validator.validate(
            dhcp4_reservations=[reservation],
            dhcp6_reservations=[],
            dhcp4_subnet_names=set(),
            dhcp6_subnet_names={"guest"},
            index=index,
        )
        failures = _failures(report, "kea_reservation_server1_subnet")
        assert failures, "Expected ERROR for wrong-version cross"
        msg = failures[0].message
        assert "kea.dhcp6.subnets" in msg
        assert "kea.dhcp4.subnets" in msg

    def test_v6_reservation_subnet_ref_pointing_at_v4_subnet_errors(
        self, validator: KeaReservationValidator, report: ValidationReport
    ) -> None:
        v4_subnet = _v4_subnet("lan-dhcp", subnet="10.0.10.0/24")
        reservation = _v6_reservation("server1-v6", subnet_ref="lan-dhcp")
        index = build_xref_index([v4_subnet, reservation])
        validator.validate(
            dhcp4_reservations=[],
            dhcp6_reservations=[reservation],
            dhcp4_subnet_names={"lan-dhcp"},
            dhcp6_subnet_names=set(),
            index=index,
        )
        failures = _failures(report, "kea_reservation_server1-v6_subnet")
        assert failures, "Expected ERROR for wrong-version cross"
        msg = failures[0].message
        assert "kea.dhcp4.subnets" in msg
        assert "kea.dhcp6.subnets" in msg


# ---------------------------------------------------------------------------
# subnet literal (legacy form)
# ---------------------------------------------------------------------------


class TestSubnetLiteral:
    def test_subnet_literal_only_legacy_form_passes(
        self, validator: KeaReservationValidator, report: ValidationReport
    ) -> None:
        # Operator wrote no subnet_ref; just the literal CIDR. This is the
        # legacy form the existing v6 fixtures still use; must continue
        # to pass.
        reservation = _v6_reservation("legacy-v6", subnet="fd00:1::/64")
        index = build_xref_index([reservation])
        validator.validate(
            dhcp4_reservations=[],
            dhcp6_reservations=[reservation],
            dhcp4_subnet_names=set(),
            dhcp6_subnet_names=set(),
            index=index,
        )
        assert not _failures(report, "kea_reservation_legacy-v6_subnet")
        assert _passes(report, "kea_reservation_legacy-v6_subnet")

    def test_subnet_literal_malformed_cidr_errors(
        self, validator: KeaReservationValidator, report: ValidationReport
    ) -> None:
        reservation = _v4_reservation("bad", subnet="not-a-cidr")
        index = build_xref_index([reservation])
        validator.validate(
            dhcp4_reservations=[reservation],
            dhcp6_reservations=[],
            dhcp4_subnet_names=set(),
            dhcp6_subnet_names=set(),
            index=index,
        )
        failures = _failures(report, "kea_reservation_bad_subnet")
        assert failures
        assert "valid CIDR" in failures[0].message or "not-a-cidr" in failures[0].message

    def test_subnet_literal_wrong_family_for_v4_errors(
        self, validator: KeaReservationValidator, report: ValidationReport
    ) -> None:
        # IPv6 CIDR jammed into a v4 reservation must fail.
        reservation = _v4_reservation("wrong-fam", subnet="fd00:1::/64")
        index = build_xref_index([reservation])
        validator.validate(
            dhcp4_reservations=[reservation],
            dhcp6_reservations=[],
            dhcp4_subnet_names=set(),
            dhcp6_subnet_names=set(),
            index=index,
        )
        failures = _failures(report, "kea_reservation_wrong-fam_subnet")
        assert failures
        msg = failures[0].message
        assert "IPv4" in msg or "IPv6" in msg


# ---------------------------------------------------------------------------
# Both / neither field
# ---------------------------------------------------------------------------


class TestFieldPresence:
    def test_neither_subnet_nor_subnet_ref_errors(
        self, validator: KeaReservationValidator, report: ValidationReport
    ) -> None:
        # Build a reservation with neither field — must fail.
        reservation = ResourceConfig(
            name="naked",
            type="kea.dhcp4.reservations",
            provider="opnsense",
            config={
                "hw_address": "aa:bb:cc:dd:ee:01",
                "ip_address": "10.0.10.50",
            },
        )
        index = build_xref_index([reservation])
        validator.validate(
            dhcp4_reservations=[reservation],
            dhcp6_reservations=[],
            dhcp4_subnet_names=set(),
            dhcp6_subnet_names=set(),
            index=index,
        )
        failures = _failures(report, "kea_reservation_naked_subnet")
        assert failures
        msg = failures[0].message
        assert "missing required field" in msg or "expected one of" in msg

    def test_both_present_and_agree_passes(
        self, validator: KeaReservationValidator, report: ValidationReport
    ) -> None:
        # subnet_ref resolves to "10.0.10.0/24"; subnet literal matches.
        v4_subnet = _v4_subnet("lan", subnet="10.0.10.0/24")
        reservation = _v4_reservation("server1", subnet_ref="lan", subnet="10.0.10.0/24")
        index = build_xref_index([v4_subnet, reservation])
        validator.validate(
            dhcp4_reservations=[reservation],
            dhcp6_reservations=[],
            dhcp4_subnet_names={"lan"},
            dhcp6_subnet_names=set(),
            index=index,
        )
        assert not _failures(report, "kea_reservation_server1_subnet")
        assert _passes(report, "kea_reservation_server1_subnet")

    def test_both_present_and_disagree_errors(
        self, validator: KeaReservationValidator, report: ValidationReport
    ) -> None:
        v4_subnet = _v4_subnet("lan", subnet="10.0.10.0/24")
        reservation = _v4_reservation("server1", subnet_ref="lan", subnet="10.0.20.0/24")
        index = build_xref_index([v4_subnet, reservation])
        validator.validate(
            dhcp4_reservations=[reservation],
            dhcp6_reservations=[],
            dhcp4_subnet_names={"lan"},
            dhcp6_subnet_names=set(),
            index=index,
        )
        failures = _failures(report, "kea_reservation_server1_subnet")
        assert failures
        msg = failures[0].message
        assert "conflicting" in msg


# ---------------------------------------------------------------------------
# Dotted-path subnet_ref resolution
# ---------------------------------------------------------------------------


class TestDottedPath:
    def test_subnet_ref_dotted_path_resolves(
        self, validator: KeaReservationValidator, report: ValidationReport
    ) -> None:
        # Cross-plugin absolute form: "kea.dhcp4.subnets.web".
        v4_subnet = _v4_subnet("web", subnet="10.0.10.0/24")
        reservation = _v4_reservation("server1", subnet_ref="kea.dhcp4.subnets.web")
        index = build_xref_index([v4_subnet, reservation])
        validator.validate(
            dhcp4_reservations=[reservation],
            dhcp6_reservations=[],
            dhcp4_subnet_names={"web"},
            dhcp6_subnet_names=set(),
            index=index,
        )
        assert not _failures(report, "kea_reservation_server1_subnet")
        assert _passes(report, "kea_reservation_server1_subnet")
