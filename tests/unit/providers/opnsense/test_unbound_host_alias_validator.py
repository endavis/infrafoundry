"""Unit tests for ``UnboundHostAliasValidator``.

Coverage:
    - ``host`` cross-reference: managed override name accepted, live
      override name (hostname or hostname.domain) accepted, unknown
      reference rejected, missing/non-string rejected.
    - ``hostname`` field: required, non-empty string.
    - ``domain`` field: required, non-empty string.
    - Bool type checks: ``enabled``, ``lock``.
    - ``description`` type check.
    - Uniqueness of ``(host, hostname)`` tuples within YAML.
"""

from __future__ import annotations

from typing import Any

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationReport
from infrafoundry.providers.opnsense.validators.unbound_host_alias_validator import (
    UnboundHostAliasValidator,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _alias(name: str, **overrides: Any) -> ResourceConfig:
    config: dict[str, Any] = {
        "host": "db-primary",
        "hostname": "db",
        "domain": "internal",
    }
    config.update(overrides)
    return ResourceConfig(
        name=name, type="unbound.host_aliases", provider="opnsense", config=config
    )


@pytest.fixture
def report() -> ValidationReport:
    return ValidationReport()


@pytest.fixture
def validator(report: ValidationReport) -> UnboundHostAliasValidator:
    return UnboundHostAliasValidator(report)


def _failures(report: ValidationReport, check_name: str) -> list[Any]:
    return [c for c in report.results if c.check_name == check_name and not c.passed]


# ---------------------------------------------------------------------------
# host cross-ref
# ---------------------------------------------------------------------------


class TestHostCrossRef:
    def test_managed_override_accepted(
        self, validator: UnboundHostAliasValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_alias("ok", host="db-primary")],
            managed_host_override_names={"db-primary"},
            existing_host_override_names=set(),
        )
        assert not _failures(report, "unbound_host_alias_ok_host")

    def test_live_override_short_name_accepted(
        self, validator: UnboundHostAliasValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_alias("ok", host="db-primary")],
            managed_host_override_names=set(),
            existing_host_override_names={"db-primary", "db-primary.internal"},
        )
        assert not _failures(report, "unbound_host_alias_ok_host")

    def test_live_override_fqdn_accepted(
        self, validator: UnboundHostAliasValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_alias("ok", host="db-primary.internal")],
            managed_host_override_names=set(),
            existing_host_override_names={"db-primary", "db-primary.internal"},
        )
        assert not _failures(report, "unbound_host_alias_ok_host")

    def test_unknown_host_rejected(
        self, validator: UnboundHostAliasValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_alias("bad", host="bogus")],
            managed_host_override_names={"db-primary"},
            existing_host_override_names={"db-primary"},
        )
        assert _failures(report, "unbound_host_alias_bad_host")

    def test_missing_host_rejected(
        self, validator: UnboundHostAliasValidator, report: ValidationReport
    ) -> None:
        r = ResourceConfig(
            name="bad",
            type="unbound.host_aliases",
            provider="opnsense",
            config={"hostname": "db", "domain": "internal"},
        )
        validator.validate(
            [r],
            managed_host_override_names=set(),
            existing_host_override_names=set(),
        )
        assert _failures(report, "unbound_host_alias_bad_host")

    def test_empty_host_rejected(
        self, validator: UnboundHostAliasValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_alias("bad", host="")],
            managed_host_override_names=set(),
            existing_host_override_names=set(),
        )
        assert _failures(report, "unbound_host_alias_bad_host")

    def test_non_string_host_rejected(
        self, validator: UnboundHostAliasValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_alias("bad", host=12345)],
            managed_host_override_names=set(),
            existing_host_override_names=set(),
        )
        assert _failures(report, "unbound_host_alias_bad_host")


# ---------------------------------------------------------------------------
# hostname
# ---------------------------------------------------------------------------


class TestHostname:
    def test_string_passes(
        self, validator: UnboundHostAliasValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_alias("ok", hostname="db")],
            managed_host_override_names={"db-primary"},
            existing_host_override_names=set(),
        )
        assert not _failures(report, "unbound_host_alias_ok_hostname")

    def test_missing_rejected(
        self, validator: UnboundHostAliasValidator, report: ValidationReport
    ) -> None:
        r = ResourceConfig(
            name="bad",
            type="unbound.host_aliases",
            provider="opnsense",
            config={"host": "db-primary", "domain": "internal"},
        )
        validator.validate(
            [r],
            managed_host_override_names={"db-primary"},
            existing_host_override_names=set(),
        )
        assert _failures(report, "unbound_host_alias_bad_hostname")

    def test_empty_rejected(
        self, validator: UnboundHostAliasValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_alias("bad", hostname="")],
            managed_host_override_names={"db-primary"},
            existing_host_override_names=set(),
        )
        assert _failures(report, "unbound_host_alias_bad_hostname")

    def test_non_string_rejected(
        self, validator: UnboundHostAliasValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_alias("bad", hostname=12345)],
            managed_host_override_names={"db-primary"},
            existing_host_override_names=set(),
        )
        assert _failures(report, "unbound_host_alias_bad_hostname")


# ---------------------------------------------------------------------------
# domain
# ---------------------------------------------------------------------------


class TestDomain:
    def test_string_passes(
        self, validator: UnboundHostAliasValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_alias("ok", domain="internal")],
            managed_host_override_names={"db-primary"},
            existing_host_override_names=set(),
        )
        assert not _failures(report, "unbound_host_alias_ok_domain")

    def test_missing_rejected(
        self, validator: UnboundHostAliasValidator, report: ValidationReport
    ) -> None:
        r = ResourceConfig(
            name="bad",
            type="unbound.host_aliases",
            provider="opnsense",
            config={"host": "db-primary", "hostname": "db"},
        )
        validator.validate(
            [r],
            managed_host_override_names={"db-primary"},
            existing_host_override_names=set(),
        )
        assert _failures(report, "unbound_host_alias_bad_domain")

    def test_empty_rejected(
        self, validator: UnboundHostAliasValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_alias("bad", domain="")],
            managed_host_override_names={"db-primary"},
            existing_host_override_names=set(),
        )
        assert _failures(report, "unbound_host_alias_bad_domain")

    def test_non_string_rejected(
        self, validator: UnboundHostAliasValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_alias("bad", domain=12345)],
            managed_host_override_names={"db-primary"},
            existing_host_override_names=set(),
        )
        assert _failures(report, "unbound_host_alias_bad_domain")


# ---------------------------------------------------------------------------
# bool type checks
# ---------------------------------------------------------------------------


class TestBoolFields:
    def test_enabled_must_be_bool(
        self, validator: UnboundHostAliasValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_alias("bad", enabled="yes")],
            managed_host_override_names={"db-primary"},
            existing_host_override_names=set(),
        )
        assert _failures(report, "unbound_host_alias_bad_enabled")

    def test_lock_must_be_bool(
        self, validator: UnboundHostAliasValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_alias("bad", lock="yes")],
            managed_host_override_names={"db-primary"},
            existing_host_override_names=set(),
        )
        assert _failures(report, "unbound_host_alias_bad_lock")

    def test_enabled_true_passes(
        self, validator: UnboundHostAliasValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_alias("ok", enabled=True)],
            managed_host_override_names={"db-primary"},
            existing_host_override_names=set(),
        )
        assert not _failures(report, "unbound_host_alias_ok_enabled")

    def test_lock_true_passes(
        self, validator: UnboundHostAliasValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_alias("ok", lock=True)],
            managed_host_override_names={"db-primary"},
            existing_host_override_names=set(),
        )
        assert not _failures(report, "unbound_host_alias_ok_lock")


# ---------------------------------------------------------------------------
# description
# ---------------------------------------------------------------------------


class TestDescription:
    def test_string_passes(
        self, validator: UnboundHostAliasValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_alias("ok", description="my description")],
            managed_host_override_names={"db-primary"},
            existing_host_override_names=set(),
        )
        assert not _failures(report, "unbound_host_alias_ok_description")

    def test_non_string_fails(
        self, validator: UnboundHostAliasValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_alias("bad", description=12345)],
            managed_host_override_names={"db-primary"},
            existing_host_override_names=set(),
        )
        assert _failures(report, "unbound_host_alias_bad_description")


# ---------------------------------------------------------------------------
# uniqueness
# ---------------------------------------------------------------------------


class TestUniqueness:
    def test_distinct_tuples_pass(
        self, validator: UnboundHostAliasValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [
                _alias("a", hostname="db1"),
                _alias("b", hostname="db2"),
            ],
            managed_host_override_names={"db-primary"},
            existing_host_override_names=set(),
        )
        assert not _failures(report, "unbound_host_alias_a_uniqueness")
        assert not _failures(report, "unbound_host_alias_b_uniqueness")

    def test_duplicate_tuple_rejected(
        self, validator: UnboundHostAliasValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [
                _alias("first", hostname="db"),
                _alias("dup", hostname="db"),
            ],
            managed_host_override_names={"db-primary"},
            existing_host_override_names=set(),
        )
        assert _failures(report, "unbound_host_alias_dup_uniqueness")

    def test_same_hostname_different_host_passes(
        self, validator: UnboundHostAliasValidator, report: ValidationReport
    ) -> None:
        # ``hostname`` matches but ``host`` differs — distinct tuple.
        validator.validate(
            [
                _alias("a", host="db-primary", hostname="db"),
                _alias("b", host="db-secondary", hostname="db"),
            ],
            managed_host_override_names={"db-primary", "db-secondary"},
            existing_host_override_names=set(),
        )
        assert not _failures(report, "unbound_host_alias_b_uniqueness")


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_list_no_failures(
        self, validator: UnboundHostAliasValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [],
            managed_host_override_names=set(),
            existing_host_override_names=set(),
        )
        assert report.results == []

    def test_multiple_aliases_all_validated(
        self, validator: UnboundHostAliasValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [
                _alias("a", hostname="db1"),
                _alias("b", hostname="db2"),
                _alias("c", hostname="db3"),
            ],
            managed_host_override_names={"db-primary"},
            existing_host_override_names=set(),
        )
        names = {c.check_name for c in report.results if c.check_name.endswith("_host")}
        assert "unbound_host_alias_a_host" in names
        assert "unbound_host_alias_b_host" in names
        assert "unbound_host_alias_c_host" in names


# ---------------------------------------------------------------------------
# Dotted-path cross-references (#793) — forward-compat
# ---------------------------------------------------------------------------


class TestDottedPathXRefs:
    """Forward-compat tests for the dotted-path resolver. Bare-name
    behaviour (``index=None``) is unchanged. Validating dotted refs
    requires an ``index``."""

    def test_cross_plugin_absolute_host_resolves(
        self, validator: UnboundHostAliasValidator, report: ValidationReport
    ) -> None:
        from infrafoundry.providers.opnsense.validators._xref import build_xref_index

        host = ResourceConfig(
            name="db-primary",
            type="unbound.host_overrides",
            provider="opnsense",
            config={"hostname": "db", "domain": "internal", "ip": "10.0.0.1"},
        )
        index = build_xref_index([host])
        # ``unbound.host_overrides.db-primary`` is a 3-part path → cross-
        # plugin absolute. Resolver matches the (type, name) tuple.
        validator.validate(
            [_alias("ok", host="unbound.host_overrides.db-primary")],
            managed_host_override_names={"db-primary"},
            existing_host_override_names=set(),
            index=index,
        )
        passed = [
            c for c in report.results if c.check_name == "unbound_host_alias_ok_host" and c.passed
        ]
        assert passed

    def test_in_plugin_relative_host_resolves(
        self, validator: UnboundHostAliasValidator, report: ValidationReport
    ) -> None:
        from infrafoundry.providers.opnsense.validators._xref import build_xref_index

        host = ResourceConfig(
            name="db-primary",
            type="unbound.host_overrides",
            provider="opnsense",
            config={"hostname": "db", "domain": "internal", "ip": "10.0.0.1"},
        )
        index = build_xref_index([host])
        # Alias type ``unbound.host_aliases`` → current_plugin="unbound"
        # → ``host_overrides.db-primary`` resolves to
        # ``unbound.host_overrides.db-primary``.
        validator.validate(
            [_alias("ok", host="host_overrides.db-primary")],
            managed_host_override_names={"db-primary"},
            existing_host_override_names=set(),
            index=index,
        )
        passed = [
            c for c in report.results if c.check_name == "unbound_host_alias_ok_host" and c.passed
        ]
        assert passed

    def test_live_hostname_with_dot_falls_back_to_existing(
        self, validator: UnboundHostAliasValidator, report: ValidationReport
    ) -> None:
        # The live ``hostname.domain`` form contains a dot but is NOT a
        # dotted xref — the resolver lookup misses, then the bare-name
        # fallback finds it in ``existing_host_override_names``.
        from infrafoundry.providers.opnsense.validators._xref import build_xref_index

        index = build_xref_index([])
        validator.validate(
            [_alias("ok", host="db.internal")],
            managed_host_override_names=set(),
            existing_host_override_names={"db.internal"},
            index=index,
        )
        passed = [
            c for c in report.results if c.check_name == "unbound_host_alias_ok_host" and c.passed
        ]
        assert passed

    def test_index_none_preserves_legacy_behaviour(
        self, validator: UnboundHostAliasValidator, report: ValidationReport
    ) -> None:
        validator.validate(
            [_alias("ok")],
            managed_host_override_names={"db-primary"},
            existing_host_override_names=set(),
        )
        passed = [
            c for c in report.results if c.check_name == "unbound_host_alias_ok_host" and c.passed
        ]
        assert passed
