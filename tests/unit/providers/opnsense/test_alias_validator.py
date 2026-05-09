"""Unit tests for ``AliasValidator``.

Coverage:
    - ``name``: required, non-empty, charset (``^[A-Za-z0-9_]+$``),
      length cap (32 chars), reserved-name rejection (``pkg-*``,
      ``__*``, ``bogons``, ``virusprot``, ``sshlockout``,
      ``bogonsv6``).
    - ``type``: required, non-empty string, known kinds pass, unknown
      kinds soft-warn, system-only kinds (``internal`` / ``external``)
      hard-fail.
    - ``content`` shape per type: ``host`` / ``network`` (IP or CIDR),
      ``port`` / ``urltable_ports`` (port number or hyphenated range),
      ``geoip`` (ISO 3166-1 alpha-2), ``mac`` (colon-separated hex);
      list typing; entry-type checks.
    - ``proto``: type, value (``IPv4`` / ``IPv6``), only meaningful with
      ``type=geoip``.
    - ``updatefreq``: must be a string parseable as a positive number.
    - ``categories``: must be a list of strings.
    - Bool fields (``enabled``, ``counters``, ``lock``).
    - ``description``: must be a string.
    - Uniqueness: two YAML entries with the same wire ``name`` collide.
"""

from __future__ import annotations

from typing import Any

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.opnsense.validators.alias_validator import AliasValidator

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _alias(name: str, **overrides: Any) -> ResourceConfig:
    config: dict[str, Any] = {
        "name": name,
        "type": "host",
        "content": ["192.0.2.1"],
    }
    config.update(overrides)
    return ResourceConfig(name=name, type="firewall.aliases", provider="opnsense", config=config)


@pytest.fixture
def report() -> ValidationReport:
    return ValidationReport()


@pytest.fixture
def validator(report: ValidationReport) -> AliasValidator:
    return AliasValidator(report)


def _failures(report: ValidationReport, check_name: str) -> list[Any]:
    return [c for c in report.results if c.check_name == check_name and not c.passed]


def _warnings(report: ValidationReport, check_name: str) -> list[Any]:
    return [
        c
        for c in report.results
        if c.check_name == check_name and c.level == ValidationLevel.WARNING
    ]


def _errors(report: ValidationReport, check_name: str) -> list[Any]:
    return [
        c for c in report.results if c.check_name == check_name and c.level == ValidationLevel.ERROR
    ]


# ---------------------------------------------------------------------------
# name
# ---------------------------------------------------------------------------


class TestName:
    def test_valid_name_passes(self, validator: AliasValidator, report: ValidationReport) -> None:
        validator.validate([_alias("web_servers")])
        assert not _failures(report, "alias_web_servers_name")

    def test_alphanumeric_only_passes(
        self, validator: AliasValidator, report: ValidationReport
    ) -> None:
        validator.validate([_alias("WebServers123")])
        assert not _failures(report, "alias_WebServers123_name")

    def test_underscore_passes(self, validator: AliasValidator, report: ValidationReport) -> None:
        validator.validate([_alias("web_servers_2")])
        assert not _failures(report, "alias_web_servers_2_name")

    def test_hyphen_rejected(self, validator: AliasValidator, report: ValidationReport) -> None:
        # OPNsense's wire rule: only ``[A-Za-z0-9_]``.
        validator.validate([_alias("web-servers")])
        assert _failures(report, "alias_web-servers_name")

    def test_dot_rejected(self, validator: AliasValidator, report: ValidationReport) -> None:
        validator.validate([_alias("web.servers")])
        assert _failures(report, "alias_web.servers_name")

    def test_space_rejected(self, validator: AliasValidator, report: ValidationReport) -> None:
        r = ResourceConfig(
            name="bad space",
            type="firewall.aliases",
            provider="opnsense",
            config={"name": "bad space", "type": "host", "content": ["192.0.2.1"]},
        )
        validator.validate([r])
        assert _failures(report, "alias_bad space_name")

    def test_too_long_rejected(self, validator: AliasValidator, report: ValidationReport) -> None:
        # 33 chars — one over the cap.
        long_name = "a" * 33
        validator.validate([_alias(long_name)])
        assert _failures(report, f"alias_{long_name}_name")

    def test_max_length_passes(self, validator: AliasValidator, report: ValidationReport) -> None:
        # 32 chars — at the cap.
        max_name = "a" * 32
        validator.validate([_alias(max_name)])
        assert not _failures(report, f"alias_{max_name}_name")

    def test_empty_name_rejected(self, validator: AliasValidator, report: ValidationReport) -> None:
        r = ResourceConfig(
            name="bad",
            type="firewall.aliases",
            provider="opnsense",
            config={"name": "", "type": "host", "content": ["192.0.2.1"]},
        )
        validator.validate([r])
        assert _failures(report, "alias_bad_name")

    def test_non_string_name_rejected(
        self, validator: AliasValidator, report: ValidationReport
    ) -> None:
        r = ResourceConfig(
            name="bad",
            type="firewall.aliases",
            provider="opnsense",
            config={"name": 12345, "type": "host", "content": ["192.0.2.1"]},
        )
        validator.validate([r])
        assert _failures(report, "alias_bad_name")

    def test_falls_back_to_top_level_name(
        self, validator: AliasValidator, report: ValidationReport
    ) -> None:
        # Operator may omit ``config.name`` and lean on the top-level
        # resource name.
        r = ResourceConfig(
            name="ok_name",
            type="firewall.aliases",
            provider="opnsense",
            config={"type": "host", "content": ["192.0.2.1"]},
        )
        validator.validate([r])
        assert not _failures(report, "alias_ok_name_name")

    @pytest.mark.parametrize(
        "reserved",
        ["bogons", "bogonsv6", "sshlockout", "virusprot"],
    )
    def test_reserved_name_rejected(
        self,
        validator: AliasValidator,
        report: ValidationReport,
        reserved: str,
    ) -> None:
        validator.validate([_alias(reserved)])
        assert _failures(report, f"alias_{reserved}_name")

    @pytest.mark.parametrize("prefixed", ["pkg_python", "__lan_network"])
    def test_reserved_prefix_rejected(
        self,
        validator: AliasValidator,
        report: ValidationReport,
        prefixed: str,
    ) -> None:
        # Note: pkg- prefix uses hyphen (rejected by charset); ``pkg_*``
        # is a valid charset but not in the reserved set per the
        # validator. We exercise the ``__*`` prefix here which is both
        # valid charset AND reserved.
        validator.validate([_alias(prefixed)])
        # The ``__lan_network`` case must hit the reserved-name path; the
        # ``pkg_python`` case is allowed (pkg- with hyphen is reserved
        # but pkg_ with underscore is not).
        if prefixed.startswith("__"):
            assert _failures(report, f"alias_{prefixed}_name")


# ---------------------------------------------------------------------------
# type
# ---------------------------------------------------------------------------


class TestType:
    @pytest.mark.parametrize(
        "alias_type",
        ["host", "network", "networkgroup", "port", "url", "urltable", "mac", "geoip"],
    )
    def test_known_types_pass(
        self,
        validator: AliasValidator,
        report: ValidationReport,
        alias_type: str,
    ) -> None:
        config: dict[str, Any] = {"type": alias_type}
        if alias_type == "geoip":
            config["content"] = ["US"]
        elif alias_type == "port":
            config["content"] = ["80"]
        elif alias_type == "mac":
            config["content"] = ["aa:bb:cc:dd:ee:ff"]
        elif alias_type in {"host", "network"}:
            config["content"] = ["192.0.2.0/24"]
        else:
            config["content"] = ["something"]
        validator.validate([_alias("ok", **config)])
        # No type-related ERROR (warnings on geoip / urljson aren't
        # raised on these known kinds).
        assert not _errors(report, "alias_ok_type")

    def test_unknown_type_warns(self, validator: AliasValidator, report: ValidationReport) -> None:
        validator.validate([_alias("ok", type="madeup_kind", content=["something"])])
        assert _warnings(report, "alias_ok_type")

    def test_missing_type_rejected(
        self, validator: AliasValidator, report: ValidationReport
    ) -> None:
        r = ResourceConfig(
            name="bad",
            type="firewall.aliases",
            provider="opnsense",
            config={"name": "bad", "content": ["192.0.2.1"]},
        )
        validator.validate([r])
        assert _failures(report, "alias_bad_type")

    def test_empty_type_rejected(self, validator: AliasValidator, report: ValidationReport) -> None:
        r = ResourceConfig(
            name="bad",
            type="firewall.aliases",
            provider="opnsense",
            config={"name": "bad", "type": "", "content": []},
        )
        validator.validate([r])
        assert _failures(report, "alias_bad_type")

    def test_non_string_type_rejected(
        self, validator: AliasValidator, report: ValidationReport
    ) -> None:
        r = ResourceConfig(
            name="bad",
            type="firewall.aliases",
            provider="opnsense",
            config={"name": "bad", "type": 12345, "content": []},
        )
        validator.validate([r])
        assert _failures(report, "alias_bad_type")

    @pytest.mark.parametrize("system_kind", ["internal", "external"])
    def test_system_only_types_rejected(
        self,
        validator: AliasValidator,
        report: ValidationReport,
        system_kind: str,
    ) -> None:
        validator.validate([_alias("system_alias", type=system_kind, content=[])])
        errors = _errors(report, "alias_system_alias_type")
        assert errors


# ---------------------------------------------------------------------------
# content (per type)
# ---------------------------------------------------------------------------


class TestContentHost:
    def test_valid_ip_passes(self, validator: AliasValidator, report: ValidationReport) -> None:
        validator.validate([_alias("ok", type="host", content=["192.0.2.1"])])
        assert not _failures(report, "alias_ok_content_0")

    def test_valid_cidr_passes(self, validator: AliasValidator, report: ValidationReport) -> None:
        validator.validate([_alias("ok", type="host", content=["192.0.2.0/24"])])
        assert not _failures(report, "alias_ok_content_0")

    def test_valid_ipv6_passes(self, validator: AliasValidator, report: ValidationReport) -> None:
        validator.validate([_alias("ok", type="host", content=["2001:db8::1"])])
        assert not _failures(report, "alias_ok_content_0")

    def test_invalid_ip_rejected(self, validator: AliasValidator, report: ValidationReport) -> None:
        validator.validate([_alias("bad", type="host", content=["not-an-ip"])])
        assert _failures(report, "alias_bad_content_0")

    def test_network_cidr_passes(self, validator: AliasValidator, report: ValidationReport) -> None:
        validator.validate([_alias("ok", type="network", content=["10.0.0.0/8"])])
        assert not _failures(report, "alias_ok_content_0")

    def test_network_invalid_rejected(
        self, validator: AliasValidator, report: ValidationReport
    ) -> None:
        validator.validate([_alias("bad", type="network", content=["definitely-not-a-cidr"])])
        assert _failures(report, "alias_bad_content_0")


class TestContentPort:
    def test_bare_port_passes(self, validator: AliasValidator, report: ValidationReport) -> None:
        validator.validate([_alias("ok", type="port", content=["80"])])
        assert not _failures(report, "alias_ok_content_0")

    def test_port_range_passes(self, validator: AliasValidator, report: ValidationReport) -> None:
        validator.validate([_alias("ok", type="port", content=["8000-8999"])])
        assert not _failures(report, "alias_ok_content_0")

    def test_invalid_port_rejected(
        self, validator: AliasValidator, report: ValidationReport
    ) -> None:
        validator.validate([_alias("bad", type="port", content=["http"])])
        assert _failures(report, "alias_bad_content_0")

    def test_urltable_ports_kind_uses_port_regex(
        self, validator: AliasValidator, report: ValidationReport
    ) -> None:
        validator.validate([_alias("ok", type="urltable_ports", content=["443"])])
        assert not _failures(report, "alias_ok_content_0")


class TestContentGeoip:
    def test_valid_country_code_passes(
        self, validator: AliasValidator, report: ValidationReport
    ) -> None:
        validator.validate([_alias("ok", type="geoip", content=["US", "CA"])])
        assert not _failures(report, "alias_ok_content_0")
        assert not _failures(report, "alias_ok_content_1")

    def test_lowercase_country_code_rejected(
        self, validator: AliasValidator, report: ValidationReport
    ) -> None:
        validator.validate([_alias("bad", type="geoip", content=["us"])])
        assert _failures(report, "alias_bad_content_0")

    def test_three_letter_code_rejected(
        self, validator: AliasValidator, report: ValidationReport
    ) -> None:
        validator.validate([_alias("bad", type="geoip", content=["USA"])])
        assert _failures(report, "alias_bad_content_0")


class TestContentMac:
    def test_full_mac_passes(self, validator: AliasValidator, report: ValidationReport) -> None:
        validator.validate([_alias("ok", type="mac", content=["aa:bb:cc:dd:ee:ff"])])
        assert not _failures(report, "alias_ok_content_0")

    def test_partial_vendor_prefix_passes(
        self, validator: AliasValidator, report: ValidationReport
    ) -> None:
        validator.validate([_alias("ok", type="mac", content=["aa:bb"])])
        assert not _failures(report, "alias_ok_content_0")

    def test_invalid_mac_rejected(
        self, validator: AliasValidator, report: ValidationReport
    ) -> None:
        validator.validate([_alias("bad", type="mac", content=["zz:zz"])])
        assert _failures(report, "alias_bad_content_0")

    def test_no_colons_rejected(self, validator: AliasValidator, report: ValidationReport) -> None:
        validator.validate([_alias("bad", type="mac", content=["aabbccddeeff"])])
        assert _failures(report, "alias_bad_content_0")


class TestContentShape:
    def test_content_must_be_list(
        self, validator: AliasValidator, report: ValidationReport
    ) -> None:
        validator.validate([_alias("bad", content="not-a-list")])
        assert _failures(report, "alias_bad_content")

    def test_content_entry_must_be_string(
        self, validator: AliasValidator, report: ValidationReport
    ) -> None:
        validator.validate([_alias("bad", content=[12345])])
        assert _failures(report, "alias_bad_content_0")

    def test_omitted_content_skipped(
        self, validator: AliasValidator, report: ValidationReport
    ) -> None:
        # No ``content`` field — validator defers required-field check
        # to OPNsense.
        r = ResourceConfig(
            name="ok",
            type="firewall.aliases",
            provider="opnsense",
            config={"name": "ok", "type": "host"},
        )
        validator.validate([r])
        assert not _failures(report, "alias_ok_content")

    def test_url_kind_accepts_arbitrary_strings(
        self, validator: AliasValidator, report: ValidationReport
    ) -> None:
        # ``url`` / ``urltable`` accept any non-empty string — the
        # OPNsense API is the authority on the per-type schema.
        validator.validate([_alias("ok", type="url", content=["https://example.com/list.txt"])])
        assert not _failures(report, "alias_ok_content_0")


# ---------------------------------------------------------------------------
# proto
# ---------------------------------------------------------------------------


class TestProto:
    def test_ipv4_passes(self, validator: AliasValidator, report: ValidationReport) -> None:
        validator.validate([_alias("ok", type="geoip", content=["US"], proto="IPv4")])
        assert not _failures(report, "alias_ok_proto")

    def test_ipv6_passes(self, validator: AliasValidator, report: ValidationReport) -> None:
        validator.validate([_alias("ok", type="geoip", content=["US"], proto="IPv6")])
        assert not _failures(report, "alias_ok_proto")

    def test_invalid_proto_rejected(
        self, validator: AliasValidator, report: ValidationReport
    ) -> None:
        validator.validate([_alias("bad", type="geoip", content=["US"], proto="ipv4")])
        assert _failures(report, "alias_bad_proto")

    def test_non_string_proto_rejected(
        self, validator: AliasValidator, report: ValidationReport
    ) -> None:
        validator.validate([_alias("bad", type="geoip", content=["US"], proto=4)])
        assert _failures(report, "alias_bad_proto")

    def test_proto_with_non_geoip_warns(
        self, validator: AliasValidator, report: ValidationReport
    ) -> None:
        validator.validate([_alias("ok", type="host", content=["192.0.2.1"], proto="IPv4")])
        assert _warnings(report, "alias_ok_proto")

    def test_empty_proto_passes(self, validator: AliasValidator, report: ValidationReport) -> None:
        # Default value is empty string — must not flag.
        validator.validate([_alias("ok", proto="")])
        assert not _failures(report, "alias_ok_proto")


# ---------------------------------------------------------------------------
# updatefreq
# ---------------------------------------------------------------------------


class TestUpdatefreq:
    def test_positive_int_passes(self, validator: AliasValidator, report: ValidationReport) -> None:
        validator.validate([_alias("ok", updatefreq="7")])
        assert not _failures(report, "alias_ok_updatefreq")

    def test_decimal_passes(self, validator: AliasValidator, report: ValidationReport) -> None:
        validator.validate([_alias("ok", updatefreq="0.5")])
        assert not _failures(report, "alias_ok_updatefreq")

    def test_zero_rejected(self, validator: AliasValidator, report: ValidationReport) -> None:
        validator.validate([_alias("bad", updatefreq="0")])
        assert _failures(report, "alias_bad_updatefreq")

    def test_negative_rejected(self, validator: AliasValidator, report: ValidationReport) -> None:
        validator.validate([_alias("bad", updatefreq="-7")])
        assert _failures(report, "alias_bad_updatefreq")

    def test_unparseable_rejected(
        self, validator: AliasValidator, report: ValidationReport
    ) -> None:
        validator.validate([_alias("bad", updatefreq="not-a-number")])
        assert _failures(report, "alias_bad_updatefreq")

    def test_non_string_rejected(self, validator: AliasValidator, report: ValidationReport) -> None:
        validator.validate([_alias("bad", updatefreq=7)])
        assert _failures(report, "alias_bad_updatefreq")

    def test_empty_string_passes(self, validator: AliasValidator, report: ValidationReport) -> None:
        # Empty = absent; not flagged.
        validator.validate([_alias("ok", updatefreq="")])
        assert not _failures(report, "alias_ok_updatefreq")


# ---------------------------------------------------------------------------
# categories
# ---------------------------------------------------------------------------


class TestCategories:
    def test_list_of_strings_passes(
        self, validator: AliasValidator, report: ValidationReport
    ) -> None:
        validator.validate([_alias("ok", categories=["uuid-1", "uuid-2"])])
        assert not _failures(report, "alias_ok_categories")

    def test_empty_list_passes(self, validator: AliasValidator, report: ValidationReport) -> None:
        validator.validate([_alias("ok", categories=[])])
        assert not _failures(report, "alias_ok_categories")

    def test_non_list_rejected(self, validator: AliasValidator, report: ValidationReport) -> None:
        validator.validate([_alias("bad", categories="uuid-1,uuid-2")])
        assert _failures(report, "alias_bad_categories")

    def test_non_string_entry_rejected(
        self, validator: AliasValidator, report: ValidationReport
    ) -> None:
        validator.validate([_alias("bad", categories=[12345])])
        assert _failures(report, "alias_bad_categories_0")


# ---------------------------------------------------------------------------
# bool fields
# ---------------------------------------------------------------------------


class TestBoolFields:
    def test_enabled_bool_passes(self, validator: AliasValidator, report: ValidationReport) -> None:
        validator.validate([_alias("ok", enabled=False)])
        assert not _failures(report, "alias_ok_enabled")

    def test_enabled_string_rejected(
        self, validator: AliasValidator, report: ValidationReport
    ) -> None:
        validator.validate([_alias("bad", enabled="yes")])
        assert _failures(report, "alias_bad_enabled")

    def test_counters_bool_passes(
        self, validator: AliasValidator, report: ValidationReport
    ) -> None:
        validator.validate([_alias("ok", counters=True)])
        assert not _failures(report, "alias_ok_counters")

    def test_counters_string_rejected(
        self, validator: AliasValidator, report: ValidationReport
    ) -> None:
        validator.validate([_alias("bad", counters="1")])
        assert _failures(report, "alias_bad_counters")

    def test_lock_bool_passes(self, validator: AliasValidator, report: ValidationReport) -> None:
        validator.validate([_alias("ok", lock=True)])
        assert not _failures(report, "alias_ok_lock")

    def test_lock_string_rejected(
        self, validator: AliasValidator, report: ValidationReport
    ) -> None:
        validator.validate([_alias("bad", lock="yes")])
        assert _failures(report, "alias_bad_lock")


# ---------------------------------------------------------------------------
# description
# ---------------------------------------------------------------------------


class TestDescription:
    def test_string_passes(self, validator: AliasValidator, report: ValidationReport) -> None:
        validator.validate([_alias("ok", description="my description")])
        assert not _failures(report, "alias_ok_description")

    def test_non_string_rejected(self, validator: AliasValidator, report: ValidationReport) -> None:
        validator.validate([_alias("bad", description=12345)])
        assert _failures(report, "alias_bad_description")

    def test_empty_string_passes(self, validator: AliasValidator, report: ValidationReport) -> None:
        validator.validate([_alias("ok", description="")])
        assert not _failures(report, "alias_ok_description")


# ---------------------------------------------------------------------------
# uniqueness
# ---------------------------------------------------------------------------


class TestUniqueness:
    def test_distinct_names_pass(self, validator: AliasValidator, report: ValidationReport) -> None:
        validator.validate([_alias("a"), _alias("b")])
        assert not _failures(report, "alias_a_uniqueness")
        assert not _failures(report, "alias_b_uniqueness")

    def test_duplicate_wire_name_rejected(
        self, validator: AliasValidator, report: ValidationReport
    ) -> None:
        # Build resources directly so we can pin ``config.name`` (the
        # wire identity) independently from the top-level resource name.
        first = ResourceConfig(
            name="first",
            type="firewall.aliases",
            provider="opnsense",
            config={"name": "shared", "type": "host", "content": ["192.0.2.1"]},
        )
        dup = ResourceConfig(
            name="dup",
            type="firewall.aliases",
            provider="opnsense",
            config={"name": "shared", "type": "host", "content": ["192.0.2.2"]},
        )
        validator.validate([first, dup])
        assert _failures(report, "alias_dup_uniqueness")

    def test_distinct_wire_names_pass(
        self, validator: AliasValidator, report: ValidationReport
    ) -> None:
        # Two entries with distinct wire names — no collision.
        a = ResourceConfig(
            name="entry_a",
            type="firewall.aliases",
            provider="opnsense",
            config={"name": "entry_a", "type": "host", "content": ["192.0.2.1"]},
        )
        b = ResourceConfig(
            name="entry_b",
            type="firewall.aliases",
            provider="opnsense",
            config={"name": "entry_b", "type": "host", "content": ["192.0.2.2"]},
        )
        validator.validate([a, b])
        assert not _failures(report, "alias_entry_a_uniqueness")
        assert not _failures(report, "alias_entry_b_uniqueness")


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_list_no_failures(
        self, validator: AliasValidator, report: ValidationReport
    ) -> None:
        validator.validate([])
        assert report.results == []

    def test_multiple_aliases_all_validated(
        self, validator: AliasValidator, report: ValidationReport
    ) -> None:
        # Validator only emits failures (no passing-check entries). Use
        # three invalid hyphenated names to confirm each is processed.
        validator.validate(
            [
                _alias("bad-a"),
                _alias("bad-b"),
                _alias("bad-c"),
            ]
        )
        names = {c.check_name for c in report.results if c.check_name.endswith("_name")}
        assert "alias_bad-a_name" in names
        assert "alias_bad-b_name" in names
        assert "alias_bad-c_name" in names

    def test_first_invalid_does_not_block_subsequent(
        self, validator: AliasValidator, report: ValidationReport
    ) -> None:
        # An invalid first entry should not abort the second's checks.
        validator.validate(
            [
                _alias("bad-name"),  # hyphen — fails name regex
                _alias("ok"),
            ]
        )
        assert _failures(report, "alias_bad-name_name")
        assert not _failures(report, "alias_ok_name")
