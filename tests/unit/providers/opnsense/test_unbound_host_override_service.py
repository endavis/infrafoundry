"""Unit tests for ``infrafoundry.providers.opnsense.services.unbound_host_override``.

Coverage:
    - ``_row_to_live`` — wire row → ``LiveUnboundHostOverride`` with
      select-dict ``rr`` normalization.
    - ``_normalize_field`` — None / scalar / select-dict shapes.
    - ``_synthesize_name`` — ``hostname-domain`` form (dot-to-hyphen,
      lowercase, ``rr`` suffix on non-A records) with defensive
      fallbacks.
    - ``_live_to_export_config`` — base fields always emitted;
      type-specific fields (``server``, ``description``, ``rr``,
      ``mxprio``, ``mx``) only when non-default.
    - ``UnboundHostOverrideService.search`` — endpoint dispatch +
      defensive parsing.
    - ``UnboundHostOverrideService.export_to_yaml`` — round-trip shape +
      multi-record export + empty-state.
    - ``UnboundHostOverrideConfig.to_payload`` — wire envelope and field
      naming (#776). OPNsense's REST uses ``rr`` / ``mxprio`` / ``mx`` —
      NOT terraform-schema ``type`` / ``mx_priority`` / ``mx_host``.
    - ``compute_diff`` — adds / updates / deletes / lock / add-only,
      keyed by ``(hostname, domain, rr)`` tuple (#776).
    - ``unbound_host_override_configs_from_resources`` — validation.
    - ``UnboundHostOverrideService`` write API method dispatch (#776).
    - ``apply_diff`` orchestration — does NOT call ``reconfigure``
      inline (runner fires ``unbound_reconfigure`` finalization hook
      per #776).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
import yaml

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.services.unbound_host_override import (
    Diff,
    LiveUnboundHostOverride,
    UnboundHostOverrideConfig,
    UnboundHostOverrideService,
    _live_to_export_config,
    _normalize_field,
    _row_to_live,
    _synthesize_name,
    compute_diff,
    unbound_host_override_configs_from_resources,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _row(
    hostname: str,
    domain: str,
    *,
    uuid: str = "u1",
    rr: str | dict[str, Any] | None = None,
    server: str = "",
    description: str = "",
    enabled: str = "1",
    mxprio: str = "",
    mx: str = "",
) -> dict[str, Any]:
    """Build a ``searchHostOverride`` row mimicking what OPNsense returns."""
    row: dict[str, Any] = {
        "uuid": uuid,
        "hostname": hostname,
        "domain": domain,
        "server": server,
        "description": description,
        "enabled": enabled,
        "mxprio": mxprio,
        "mx": mx,
    }
    if rr is not None:
        row["rr"] = rr
    return row


def _selected_rr(value: str) -> dict[str, Any]:
    """Build a select-dict like OPNsense's ``searchHostOverride`` returns for ``rr``."""
    return {value: {"value": value, "selected": 1}}


# ---------------------------------------------------------------------------
# _normalize_field
# ---------------------------------------------------------------------------


class TestNormalizeField:
    def test_none_becomes_empty(self) -> None:
        assert _normalize_field(None) == ""

    def test_string_passthrough(self) -> None:
        assert _normalize_field("web") == "web"

    def test_int_stringified(self) -> None:
        assert _normalize_field(10) == "10"

    def test_select_dict_extracts_selected_key(self) -> None:
        value = {
            "A": {"value": "A", "selected": 1},
            "AAAA": {"value": "AAAA", "selected": 0},
        }
        assert _normalize_field(value) == "A"

    def test_select_dict_no_selection_returns_empty(self) -> None:
        value = {"A": {"value": "A", "selected": 0}}
        assert _normalize_field(value) == ""


# ---------------------------------------------------------------------------
# _synthesize_name
# ---------------------------------------------------------------------------


class TestSynthesizeName:
    def test_a_record_uses_hyphenated_form(self) -> None:
        # Dots in domain replaced with hyphens; lowercased so the
        # resource key is a valid terraform identifier post-filter.
        live = LiveUnboundHostOverride(uuid="u1", hostname="web", domain="example.com", rr="A")
        assert _synthesize_name(live) == "web-example-com"

    def test_aaaa_record_appends_rr(self) -> None:
        # AAAA suffix lets A + AAAA on the same host coexist as
        # distinct resource keys (no collision in YAML or terraform).
        live = LiveUnboundHostOverride(uuid="u2", hostname="web", domain="example.com", rr="AAAA")
        assert _synthesize_name(live) == "web-example-com-aaaa"

    def test_mx_record_appends_rr(self) -> None:
        live = LiveUnboundHostOverride(uuid="u3", hostname="@", domain="example.com", rr="MX")
        assert _synthesize_name(live) == "@-example-com-mx"

    def test_missing_domain_returns_hostname(self) -> None:
        live = LiveUnboundHostOverride(uuid="u1", hostname="web", domain="", rr="A")
        assert _synthesize_name(live) == "web"

    def test_missing_hostname_returns_domain(self) -> None:
        live = LiveUnboundHostOverride(uuid="u1", hostname="", domain="example.com", rr="A")
        assert _synthesize_name(live) == "example-com"

    def test_both_missing_returns_uuid(self) -> None:
        live = LiveUnboundHostOverride(uuid="u-Fallback", hostname="", domain="", rr="A")
        assert _synthesize_name(live) == "u-fallback"

    def test_uppercase_inputs_lowercased(self) -> None:
        # OPNsense allows mixed-case in hostnames; the synthesized name
        # is lowercased so the operator key matches across renames.
        live = LiveUnboundHostOverride(uuid="u1", hostname="Web", domain="Example.COM", rr="A")
        assert _synthesize_name(live) == "web-example-com"


# ---------------------------------------------------------------------------
# _row_to_live
# ---------------------------------------------------------------------------


class TestRowToLive:
    def test_simple_a_record_row(self) -> None:
        row = _row("web", "example.com", server="10.0.0.1")
        live = _row_to_live(row)
        assert live.uuid == "u1"
        assert live.hostname == "web"
        assert live.domain == "example.com"
        assert live.rr == "A"  # default when no `rr` field on wire
        assert live.raw == row

    def test_select_dict_rr_normalized(self) -> None:
        row = _row("web6", "example.com", rr=_selected_rr("AAAA"), server="::1")
        live = _row_to_live(row)
        assert live.rr == "AAAA"

    def test_string_rr_passthrough(self) -> None:
        row = _row("web", "example.com", rr="MX")
        live = _row_to_live(row)
        assert live.rr == "MX"

    def test_missing_rr_defaults_to_a(self) -> None:
        # No ``rr`` field on the wire → default to ``A``.
        row = _row("web", "example.com", server="10.0.0.1")
        live = _row_to_live(row)
        assert live.rr == "A"

    def test_empty_rr_string_defaults_to_a(self) -> None:
        # Defensive: empty wire string also yields the default.
        row = _row("web", "example.com", rr="", server="10.0.0.1")
        live = _row_to_live(row)
        assert live.rr == "A"

    def test_missing_uuid_defaults_to_empty(self) -> None:
        live = _row_to_live({"hostname": "web", "domain": "example.com"})
        assert live.uuid == ""

    def test_missing_hostname_defaults_to_empty(self) -> None:
        live = _row_to_live({"uuid": "u1", "domain": "example.com"})
        assert live.hostname == ""


# ---------------------------------------------------------------------------
# _live_to_export_config
# ---------------------------------------------------------------------------


class TestLiveToExportConfig:
    def test_simple_a_record(self) -> None:
        live = _row_to_live(_row("web", "example.com", server="10.0.0.1", description="Web tier"))
        cfg = _live_to_export_config(live)
        assert cfg["hostname"] == "web"
        assert cfg["domain"] == "example.com"
        assert cfg["enabled"] is True
        assert cfg["server"] == "10.0.0.1"
        assert cfg["description"] == "Web tier"
        # ``rr`` is the default; must not appear in the YAML output.
        assert "rr" not in cfg
        # MX-only fields must not appear on an A record.
        assert "mxprio" not in cfg
        assert "mx" not in cfg

    def test_aaaa_record_emits_rr(self) -> None:
        live = _row_to_live(
            _row("web6", "example.com", rr=_selected_rr("AAAA"), server="2001:db8::1")
        )
        cfg = _live_to_export_config(live)
        assert cfg["rr"] == "AAAA"
        assert cfg["server"] == "2001:db8::1"
        assert "mxprio" not in cfg
        assert "mx" not in cfg

    def test_mx_record_emits_rr_mxprio_mx(self) -> None:
        live = _row_to_live(
            _row(
                "@",
                "example.com",
                rr=_selected_rr("MX"),
                mxprio="10",
                mx="mail.example.com",
            )
        )
        cfg = _live_to_export_config(live)
        assert cfg["rr"] == "MX"
        assert cfg["mxprio"] == "10"
        assert cfg["mx"] == "mail.example.com"

    def test_mx_record_omits_server_when_blank(self) -> None:
        # MX records frequently omit ``server``; YAML should exclude the
        # key rather than emit ``server: ""``.
        live = _row_to_live(
            _row(
                "@",
                "example.com",
                rr=_selected_rr("MX"),
                mxprio="10",
                mx="mail.example.com",
            )
        )
        cfg = _live_to_export_config(live)
        assert "server" not in cfg

    def test_mxprio_decimal_preserved_as_string(self) -> None:
        # Operator-set decimal precision must round-trip verbatim
        # (mirrors ``updatefreq`` handling on aliases).
        live = _row_to_live(
            _row(
                "@",
                "example.com",
                rr=_selected_rr("MX"),
                mxprio="20",
                mx="mail.example.com",
            )
        )
        cfg = _live_to_export_config(live)
        assert cfg["mxprio"] == "20"
        assert isinstance(cfg["mxprio"], str)

    def test_enabled_default_true_when_missing(self) -> None:
        # Defensive: missing ``enabled`` should default to True (no
        # override is created disabled by default).
        row = {
            "uuid": "u1",
            "hostname": "web",
            "domain": "example.com",
            "server": "10.0.0.1",
        }
        live = _row_to_live(row)
        cfg = _live_to_export_config(live)
        assert cfg["enabled"] is True

    def test_enabled_zero_returns_false(self) -> None:
        live = _row_to_live(_row("web", "example.com", server="10.0.0.1", enabled="0"))
        cfg = _live_to_export_config(live)
        assert cfg["enabled"] is False

    def test_description_passthrough(self) -> None:
        live = _row_to_live(
            _row("web", "example.com", server="10.0.0.1", description="Production web")
        )
        cfg = _live_to_export_config(live)
        assert cfg["description"] == "Production web"

    def test_description_empty_omitted(self) -> None:
        live = _row_to_live(_row("web", "example.com", server="10.0.0.1"))
        cfg = _live_to_export_config(live)
        assert "description" not in cfg

    def test_optional_fields_omitted_when_absent(self) -> None:
        # A bare A-record host override must not carry any of the
        # type-specific keys — keeps existing operator YAML
        # round-tripping identical.
        live = _row_to_live(_row("web", "example.com", server="10.0.0.1"))
        cfg = _live_to_export_config(live)
        for key in ("rr", "mxprio", "mx"):
            assert key not in cfg

    def test_rr_a_explicit_still_omitted(self) -> None:
        # Even when the wire explicitly says ``rr: A``, YAML omits it
        # so the existing 5-field operator YAML round-trips unchanged.
        live = _row_to_live(_row("web", "example.com", rr=_selected_rr("A"), server="10.0.0.1"))
        cfg = _live_to_export_config(live)
        assert "rr" not in cfg


# ---------------------------------------------------------------------------
# UnboundHostOverrideService.search
# ---------------------------------------------------------------------------


class TestServiceSearch:
    def test_search_calls_correct_endpoint(self) -> None:
        client = MagicMock()
        client.request.return_value = {"rows": []}
        svc = UnboundHostOverrideService(client)
        result = svc.search()
        client.request.assert_called_once_with("POST", "unbound/settings/searchHostOverride")
        assert result == []

    def test_search_normalizes_rows(self) -> None:
        client = MagicMock()
        client.request.return_value = {
            "rows": [
                _row("web", "example.com", uuid="u1", server="10.0.0.1"),
                "not-a-dict",
                _row(
                    "web6",
                    "example.com",
                    uuid="u2",
                    rr=_selected_rr("AAAA"),
                    server="::1",
                ),
            ]
        }
        svc = UnboundHostOverrideService(client)
        result = svc.search()
        assert len(result) == 2
        assert result[0].uuid == "u1"
        assert result[0].hostname == "web"
        assert result[0].rr == "A"
        assert result[1].uuid == "u2"
        assert result[1].rr == "AAAA"

    def test_search_handles_non_dict_response(self) -> None:
        client = MagicMock()
        client.request.return_value = "not-a-dict"
        svc = UnboundHostOverrideService(client)
        assert svc.search() == []

    def test_search_handles_missing_rows_key(self) -> None:
        client = MagicMock()
        client.request.return_value = {}
        svc = UnboundHostOverrideService(client)
        assert svc.search() == []

    def test_search_handles_non_list_rows_value(self) -> None:
        client = MagicMock()
        client.request.return_value = {"rows": "not-a-list"}
        svc = UnboundHostOverrideService(client)
        assert svc.search() == []


# ---------------------------------------------------------------------------
# UnboundHostOverrideService.export_to_yaml
# ---------------------------------------------------------------------------


class TestExportToYaml:
    def test_overrides_appear_in_export(self) -> None:
        client = MagicMock()
        client.request.return_value = {
            "rows": [
                _row(
                    "web",
                    "example.com",
                    uuid="u1",
                    server="10.0.0.1",
                    description="Web tier",
                ),
            ]
        }
        svc = UnboundHostOverrideService(client)
        text = svc.export_to_yaml()
        assert "name: web-example-com" in text
        assert "hostname: web" in text
        assert "domain: example.com" in text
        assert "10.0.0.1" in text
        assert "description: Web tier" in text
        assert "enabled: true" in text

    def test_export_with_no_overrides_yields_empty_resources(self) -> None:
        client = MagicMock()
        client.request.return_value = {"rows": []}
        svc = UnboundHostOverrideService(client)
        text = svc.export_to_yaml()
        # Nested format: empty leaf list at opnsense.unbound.host_overrides.
        assert "host_overrides: []" in text

    def test_export_round_trip_loads_back_to_dict(self) -> None:
        client = MagicMock()
        client.request.return_value = {
            "rows": [
                _row("web", "example.com", uuid="u1", server="10.0.0.1"),
                _row(
                    "web6",
                    "example.com",
                    uuid="u2",
                    rr=_selected_rr("AAAA"),
                    server="2001:db8::1",
                ),
                _row(
                    "@",
                    "example.com",
                    uuid="u3",
                    rr=_selected_rr("MX"),
                    mxprio="10",
                    mx="mail.example.com",
                ),
            ]
        }
        svc = UnboundHostOverrideService(client)
        text = svc.export_to_yaml()
        loaded = yaml.safe_load(text)
        # Nested format per ADR-0016 (#793 Phase 4).
        overrides = loaded["opnsense"]["unbound"]["host_overrides"]
        assert len(overrides) == 3

        web = overrides[0]
        assert web["name"] == "web-example-com"
        assert web["config"]["hostname"] == "web"
        assert web["config"]["domain"] == "example.com"
        assert web["config"]["server"] == "10.0.0.1"
        assert "rr" not in web["config"]

        web6 = overrides[1]
        assert web6["name"] == "web6-example-com-aaaa"
        assert web6["config"]["rr"] == "AAAA"
        assert web6["config"]["server"] == "2001:db8::1"

        mx = overrides[2]
        assert mx["name"] == "@-example-com-mx"
        assert mx["config"]["rr"] == "MX"
        assert mx["config"]["mxprio"] == "10"
        assert mx["config"]["mx"] == "mail.example.com"
        assert "server" not in mx["config"]

    def test_export_field_order_stable(self) -> None:
        # ``yaml.safe_dump(..., sort_keys=False)`` preserves insertion
        # order on the entry dict, so under nested format each entry's
        # ``name`` precedes ``config``. Operator diffs are noisy if this
        # churns.
        client = MagicMock()
        client.request.return_value = {"rows": [_row("web", "example.com", server="10.0.0.1")]}
        svc = UnboundHostOverrideService(client)
        text = svc.export_to_yaml()
        name_idx = text.index("name:")
        config_idx = text.index("config:")
        assert name_idx < config_idx


# ---------------------------------------------------------------------------
# LiveUnboundHostOverride dataclass
# ---------------------------------------------------------------------------


class TestLiveUnboundHostOverride:
    def test_dataclass_default_raw_is_empty_dict(self) -> None:
        live = LiveUnboundHostOverride(uuid="u1", hostname="web", domain="example.com", rr="A")
        assert live.raw == {}

    def test_frozen(self) -> None:
        # Defensive: dataclass is frozen so live records can't be
        # mutated in place by callers. Use ``dataclasses.replace`` if
        # needed.
        live = LiveUnboundHostOverride(uuid="u1", hostname="web", domain="example.com", rr="A")
        try:
            live.uuid = "other"  # type: ignore[misc]
        except Exception:
            return
        raise AssertionError("LiveUnboundHostOverride should be frozen")


# ---------------------------------------------------------------------------
# UnboundHostOverrideConfig (#776 write surface)
# ---------------------------------------------------------------------------


def _override(
    name: str,
    *,
    hostname: str = "web",
    domain: str = "example.com",
    rr: str = "A",
    server: str = "192.168.1.10",
    description: str = "",
    enabled: bool = True,
    mxprio: str = "",
    mx: str = "",
    lock: bool = False,
) -> UnboundHostOverrideConfig:
    return UnboundHostOverrideConfig(
        name=name,
        hostname=hostname,
        domain=domain,
        rr=rr,
        server=server,
        description=description,
        enabled=enabled,
        mxprio=mxprio,
        mx=mx,
        lock=lock,
    )


def _live_for_diff(
    uuid: str,
    *,
    hostname: str = "web",
    domain: str = "example.com",
    rr: str = "A",
    server: str = "192.168.1.10",
    description: str = "",
    enabled: str = "1",
    mxprio: str = "",
    mx: str = "",
    raw_overrides: dict[str, Any] | None = None,
) -> LiveUnboundHostOverride:
    raw: dict[str, Any] = {
        "uuid": uuid,
        "hostname": hostname,
        "domain": domain,
        "rr": rr,
        "server": server,
        "description": description,
        "enabled": enabled,
        "mxprio": mxprio,
        "mx": mx,
    }
    if raw_overrides:
        raw.update(raw_overrides)
    return LiveUnboundHostOverride(uuid=uuid, hostname=hostname, domain=domain, rr=rr, raw=raw)


def _resource_config(name: str, config: dict[str, Any]) -> ResourceConfig:
    return ResourceConfig(
        name=name, type="unbound.host_overrides", provider="opnsense", config=config
    )


class TestPayload:
    def test_payload_has_envelope(self) -> None:
        payload = _override("foo").to_payload()
        assert set(payload.keys()) == {"host"}

    def test_payload_field_set_for_a_record(self) -> None:
        override = _override(
            "web-host",
            hostname="web",
            domain="example.com",
            server="192.168.1.10",
            description="primary web",
        )
        inner = override.to_payload()["host"]
        assert inner["hostname"] == "web"
        assert inner["domain"] == "example.com"
        assert inner["rr"] == "A"
        assert inner["server"] == "192.168.1.10"
        assert inner["description"] == "primary web"

    def test_payload_field_set_for_aaaa_record(self) -> None:
        override = _override(
            "v6-host",
            hostname="v6",
            domain="example.com",
            rr="AAAA",
            server="2001:db8::10",
        )
        inner = override.to_payload()["host"]
        assert inner["rr"] == "AAAA"
        assert inner["server"] == "2001:db8::10"

    def test_payload_field_set_for_mx_record(self) -> None:
        override = _override(
            "mx-host",
            hostname="mail",
            domain="example.com",
            rr="MX",
            server="",
            mxprio="10",
            mx="mail.example.com",
        )
        inner = override.to_payload()["host"]
        assert inner["rr"] == "MX"
        assert inner["mxprio"] == "10"
        assert inner["mx"] == "mail.example.com"

    def test_payload_uses_opnsense_wire_field_names(self) -> None:
        # The legacy terraform schema (browningluke) renamed ``rr`` /
        # ``mxprio`` / ``mx`` to ``type`` / ``mx_priority`` / ``mx_host``
        # (#765/#766). The direct-API path stays true to OPNsense's own
        # wire names (#776).
        override = _override(
            "mx-host",
            rr="MX",
            mxprio="10",
            mx="mail.example.com",
        )
        inner = override.to_payload()["host"]
        # OPNsense names — present on the wire.
        assert "rr" in inner
        assert "mxprio" in inner
        assert "mx" in inner
        # Terraform-schema names — must NEVER appear on the wire.
        assert "type" not in inner
        assert "mx_priority" not in inner
        assert "mx_host" not in inner

    def test_enabled_true_serializes_one(self) -> None:
        inner = _override("foo", enabled=True).to_payload()["host"]
        assert inner["enabled"] == "1"

    def test_enabled_false_serializes_zero(self) -> None:
        inner = _override("foo", enabled=False).to_payload()["host"]
        assert inner["enabled"] == "0"

    def test_name_not_sent_on_wire(self) -> None:
        # Operator-facing top-level ``name`` is metadata only — never sent.
        inner = _override("operator-friendly-name").to_payload()["host"]
        assert "name" not in inner


class TestDiffKey:
    def test_diff_key_is_tuple(self) -> None:
        override = _override("foo", hostname="web", domain="example.com", rr="A")
        assert override.diff_key == ("web", "example.com", "A")

    def test_live_diff_key_is_tuple(self) -> None:
        live = _live_for_diff("u1", hostname="web", domain="example.com", rr="A")
        assert live.diff_key == ("web", "example.com", "A")

    def test_yaml_name_does_not_affect_diff_key(self) -> None:
        a = _override("name-one", hostname="web", domain="example.com", rr="A")
        b = _override("name-two", hostname="web", domain="example.com", rr="A")
        assert a.diff_key == b.diff_key

    def test_a_and_aaaa_have_different_diff_keys(self) -> None:
        # Same hostname + domain, different rr type — distinct identities
        # (a common dual-stack setup).
        a = _override("web-a", hostname="web", domain="example.com", rr="A")
        aaaa = _override("web-aaaa", hostname="web", domain="example.com", rr="AAAA")
        assert a.diff_key != aaaa.diff_key


class TestComputeDiffEmpty:
    def test_no_desired_no_live_is_empty(self) -> None:
        diff = compute_diff([], [])
        assert diff.is_empty
        assert diff.adds == []
        assert diff.deletes == []
        assert diff.updates == []
        assert diff.locked == []


class TestComputeDiffAdds:
    def test_new_override_adds(self) -> None:
        diff = compute_diff([_override("foo")], [])
        assert len(diff.adds) == 1
        assert diff.adds[0].hostname == "web"

    def test_a_and_aaaa_for_same_hostname_both_add(self) -> None:
        a = _override("web-a", rr="A", server="192.168.1.10")
        aaaa = _override("web-aaaa", rr="AAAA", server="2001:db8::10")
        diff = compute_diff([a, aaaa], [])
        assert len(diff.adds) == 2


class TestComputeDiffUpdates:
    def test_update_when_description_changes(self) -> None:
        override = _override("foo", description="new description")
        live = _live_for_diff("u1", description="old description")
        diff = compute_diff([override], [live])
        assert len(diff.updates) == 1
        live_record, want = diff.updates[0]
        assert live_record.uuid == "u1"
        assert want.description == "new description"

    def test_update_when_server_changes(self) -> None:
        override = _override("foo", server="10.0.0.99")
        live = _live_for_diff("u1", server="192.168.1.10")
        diff = compute_diff([override], [live])
        assert len(diff.updates) == 1

    def test_update_when_enabled_flips(self) -> None:
        override = _override("foo", enabled=False)
        live = _live_for_diff("u1", enabled="1")
        diff = compute_diff([override], [live])
        assert len(diff.updates) == 1

    def test_update_when_mxprio_changes_for_mx_record(self) -> None:
        override = _override("mx-host", rr="MX", server="", mxprio="20", mx="mail.example.com")
        live = _live_for_diff(
            "u1",
            hostname="web",
            domain="example.com",
            rr="MX",
            server="",
            mxprio="10",
            mx="mail.example.com",
        )
        diff = compute_diff([override], [live])
        assert len(diff.updates) == 1

    def test_no_update_when_payload_matches(self) -> None:
        override = _override("foo")
        live_raw: dict[str, Any] = {"uuid": "u1", **override.to_payload()["host"]}
        live = LiveUnboundHostOverride(
            uuid="u1", hostname="web", domain="example.com", rr="A", raw=live_raw
        )
        diff = compute_diff([override], [live])
        assert diff.is_empty

    def test_yaml_name_change_alone_is_noop(self) -> None:
        override = _override("renamed-override")
        live_raw: dict[str, Any] = {"uuid": "u1", **override.to_payload()["host"]}
        live = LiveUnboundHostOverride(
            uuid="u1", hostname="web", domain="example.com", rr="A", raw=live_raw
        )
        diff = compute_diff([override], [live])
        assert diff.is_empty

    def test_changing_hostname_is_delete_plus_add(self) -> None:
        old_live = _live_for_diff("u1", hostname="web", domain="example.com", rr="A")
        new_override = _override("foo", hostname="web2", domain="example.com", rr="A")
        diff = compute_diff([new_override], [old_live])
        assert len(diff.adds) == 1
        assert diff.adds[0].hostname == "web2"
        assert len(diff.deletes) == 1
        assert diff.deletes[0].uuid == "u1"

    def test_changing_rr_is_delete_plus_add(self) -> None:
        old_live = _live_for_diff("u1", hostname="web", domain="example.com", rr="A")
        new_override = _override(
            "foo", hostname="web", domain="example.com", rr="AAAA", server="2001:db8::10"
        )
        diff = compute_diff([new_override], [old_live])
        assert len(diff.adds) == 1
        assert diff.adds[0].rr == "AAAA"
        assert len(diff.deletes) == 1


class TestComputeDiffDeletes:
    def test_live_with_no_desired_is_deleted(self) -> None:
        diff = compute_diff([], [_live_for_diff("u1")])
        assert len(diff.deletes) == 1
        assert diff.deletes[0].uuid == "u1"

    def test_add_only_suppresses_deletes(self) -> None:
        diff = compute_diff([], [_live_for_diff("u1")], add_only=True)
        assert diff.deletes == []
        assert diff.is_empty

    def test_add_only_still_emits_updates(self) -> None:
        override = _override("foo", description="changed")
        live = _live_for_diff("u1", description="old")
        diff = compute_diff([override], [live], add_only=True)
        assert len(diff.updates) == 1


class TestComputeDiffLocked:
    def test_locked_resource_with_match_skipped_from_actions(self) -> None:
        override = _override("survival", description="locked", lock=True)
        live = _live_for_diff("u1", description="drift!")
        diff = compute_diff([override], [live])
        assert diff.adds == []
        assert diff.updates == []
        assert diff.deletes == []
        assert len(diff.locked) == 1
        want, have = diff.locked[0]
        assert want.lock is True
        assert have is not None
        assert have.uuid == "u1"

    def test_locked_resource_without_match(self) -> None:
        override = _override("missing", lock=True)
        diff = compute_diff([override], [])
        assert len(diff.locked) == 1
        _want, have = diff.locked[0]
        assert have is None

    def test_locked_resource_does_not_appear_as_delete_when_only_in_yaml(self) -> None:
        override = _override("locked-name", lock=True, hostname="locked-host")
        live_other = _live_for_diff("u2", hostname="other", domain="example.com")
        diff = compute_diff([override], [live_other])
        assert len(diff.deletes) == 1
        assert diff.deletes[0].hostname == "other"


class TestDiffIsEmpty:
    def test_empty_diff(self) -> None:
        assert Diff().is_empty

    def test_locked_alone_counts_as_empty(self) -> None:
        diff = Diff(locked=[(_override("foo", lock=True), None)])
        assert diff.is_empty

    def test_non_empty_when_adds(self) -> None:
        diff = Diff(adds=[_override("foo")])
        assert not diff.is_empty

    def test_non_empty_when_updates(self) -> None:
        diff = Diff(updates=[(_live_for_diff("u1"), _override("foo"))])
        assert not diff.is_empty

    def test_non_empty_when_deletes(self) -> None:
        diff = Diff(deletes=[_live_for_diff("u1")])
        assert not diff.is_empty


class TestConfigsFromResources:
    def test_valid_a_record_parses(self) -> None:
        r = _resource_config(
            "web-host",
            {
                "hostname": "web",
                "domain": "example.com",
                "server": "192.168.1.10",
                "description": "primary web",
            },
        )
        result = unbound_host_override_configs_from_resources([r])
        assert len(result) == 1
        cfg = result[0]
        assert cfg.name == "web-host"
        assert cfg.hostname == "web"
        assert cfg.domain == "example.com"
        assert cfg.rr == "A"
        assert cfg.server == "192.168.1.10"
        assert cfg.description == "primary web"

    def test_valid_aaaa_record_parses(self) -> None:
        r = _resource_config(
            "v6-host",
            {
                "hostname": "v6",
                "domain": "example.com",
                "server": "2001:db8::10",
                "rr": "AAAA",
            },
        )
        cfg = unbound_host_override_configs_from_resources([r])[0]
        assert cfg.rr == "AAAA"

    def test_valid_mx_record_parses(self) -> None:
        r = _resource_config(
            "mx-host",
            {
                "hostname": "mail",
                "domain": "example.com",
                "rr": "MX",
                "mxprio": "10",
                "mx": "mail.example.com",
            },
        )
        cfg = unbound_host_override_configs_from_resources([r])[0]
        assert cfg.rr == "MX"
        assert cfg.mxprio == "10"
        assert cfg.mx == "mail.example.com"

    def test_default_rr_is_a(self) -> None:
        r = _resource_config("foo", {"hostname": "h", "domain": "d"})
        cfg = unbound_host_override_configs_from_resources([r])[0]
        assert cfg.rr == "A"

    def test_default_enabled_true(self) -> None:
        r = _resource_config("foo", {"hostname": "h", "domain": "d"})
        cfg = unbound_host_override_configs_from_resources([r])[0]
        assert cfg.enabled is True

    def test_explicit_enabled_false(self) -> None:
        r = _resource_config("foo", {"hostname": "h", "domain": "d", "enabled": False})
        cfg = unbound_host_override_configs_from_resources([r])[0]
        assert cfg.enabled is False

    def test_lock_passthrough(self) -> None:
        r = _resource_config("foo", {"hostname": "h", "domain": "d", "lock": True})
        cfg = unbound_host_override_configs_from_resources([r])[0]
        assert cfg.lock is True

    def test_missing_hostname_rejected(self) -> None:
        r = _resource_config("bad", {"domain": "d"})
        with pytest.raises(ValueError, match="hostname"):
            unbound_host_override_configs_from_resources([r])

    def test_empty_hostname_rejected(self) -> None:
        r = _resource_config("bad", {"hostname": "", "domain": "d"})
        with pytest.raises(ValueError, match="hostname"):
            unbound_host_override_configs_from_resources([r])

    def test_missing_domain_rejected(self) -> None:
        r = _resource_config("bad", {"hostname": "h"})
        with pytest.raises(ValueError, match="domain"):
            unbound_host_override_configs_from_resources([r])

    def test_empty_domain_rejected(self) -> None:
        r = _resource_config("bad", {"hostname": "h", "domain": ""})
        with pytest.raises(ValueError, match="domain"):
            unbound_host_override_configs_from_resources([r])

    def test_non_string_server_rejected(self) -> None:
        r = _resource_config("bad", {"hostname": "h", "domain": "d", "server": 12345})
        with pytest.raises(ValueError, match="server"):
            unbound_host_override_configs_from_resources([r])

    def test_non_string_description_rejected(self) -> None:
        r = _resource_config("bad", {"hostname": "h", "domain": "d", "description": 12345})
        with pytest.raises(ValueError, match="description"):
            unbound_host_override_configs_from_resources([r])

    def test_non_string_mxprio_rejected(self) -> None:
        # ``mxprio`` is preserved as a string at the YAML layer.
        r = _resource_config("bad", {"hostname": "h", "domain": "d", "mxprio": 10})
        with pytest.raises(ValueError, match="mxprio"):
            unbound_host_override_configs_from_resources([r])

    def test_non_string_mx_rejected(self) -> None:
        r = _resource_config("bad", {"hostname": "h", "domain": "d", "mx": 12345})
        with pytest.raises(ValueError, match="mx"):
            unbound_host_override_configs_from_resources([r])

    def test_non_bool_enabled_rejected(self) -> None:
        r = _resource_config("bad", {"hostname": "h", "domain": "d", "enabled": "yes"})
        with pytest.raises(ValueError, match="enabled"):
            unbound_host_override_configs_from_resources([r])

    def test_non_bool_lock_rejected(self) -> None:
        r = _resource_config("bad", {"hostname": "h", "domain": "d", "lock": "yes"})
        with pytest.raises(ValueError, match="lock"):
            unbound_host_override_configs_from_resources([r])

    def test_non_dict_config_rejected(self) -> None:
        r = ResourceConfig(
            name="bad",
            type="unbound.host_overrides",
            provider="opnsense",
            config={"hostname": "h", "domain": "d"},
        )
        # Bypass pydantic — guard the service-side defensive check.
        r.config = "not-a-dict"  # type: ignore[assignment]
        with pytest.raises(ValueError, match="non-dict"):
            unbound_host_override_configs_from_resources([r])

    def test_non_unbound_host_override_resources_ignored(self) -> None:
        ok = _resource_config("ok", {"hostname": "h", "domain": "d"})
        other = ResourceConfig(name="x", type="firewall.aliases", provider="opnsense", config={})
        result = unbound_host_override_configs_from_resources([ok, other])
        assert len(result) == 1
        assert result[0].name == "ok"


class TestServiceGet:
    def test_get_uses_get_verb(self) -> None:
        client = MagicMock()
        client.request.return_value = {"host": {"hostname": "web"}}
        svc = UnboundHostOverrideService(client)
        result = svc.get("u1")
        client.request.assert_called_once_with("GET", "unbound/settings/getHostOverride/u1")
        assert result == {"host": {"hostname": "web"}}


class TestServiceWriteOps:
    def test_add_posts_correct_endpoint(self) -> None:
        client = MagicMock()
        client.request.return_value = {"result": "saved", "uuid": "new"}
        svc = UnboundHostOverrideService(client)
        override = _override("foo")
        svc.add(override)
        client.request.assert_called_once_with(
            "POST", "unbound/settings/addHostOverride", data=override.to_payload()
        )

    def test_add_aaaa_posts_correct_payload(self) -> None:
        client = MagicMock()
        client.request.return_value = {"result": "saved", "uuid": "new"}
        svc = UnboundHostOverrideService(client)
        override = _override("v6", rr="AAAA", server="2001:db8::10")
        svc.add(override)
        call = client.request.call_args
        payload = call.kwargs["data"]
        assert payload["host"]["rr"] == "AAAA"
        assert payload["host"]["server"] == "2001:db8::10"

    def test_add_mx_posts_correct_payload(self) -> None:
        client = MagicMock()
        client.request.return_value = {"result": "saved", "uuid": "new"}
        svc = UnboundHostOverrideService(client)
        override = _override("mx", rr="MX", server="", mxprio="10", mx="mail.example.com")
        svc.add(override)
        call = client.request.call_args
        payload = call.kwargs["data"]
        # Wire field names use OPNsense's own spelling.
        assert payload["host"]["rr"] == "MX"
        assert payload["host"]["mxprio"] == "10"
        assert payload["host"]["mx"] == "mail.example.com"

    def test_update_posts_correct_endpoint(self) -> None:
        client = MagicMock()
        client.request.return_value = {"result": "saved"}
        svc = UnboundHostOverrideService(client)
        override = _override("foo")
        svc.update("uuid-abc", override)
        client.request.assert_called_once_with(
            "POST", "unbound/settings/setHostOverride/uuid-abc", data=override.to_payload()
        )

    def test_delete_posts_correct_endpoint(self) -> None:
        client = MagicMock()
        svc = UnboundHostOverrideService(client)
        svc.delete("u1")
        client.request.assert_called_once_with("POST", "unbound/settings/delHostOverride/u1")

    def test_reconfigure_posts_correct_endpoint(self) -> None:
        client = MagicMock()
        svc = UnboundHostOverrideService(client)
        svc.reconfigure()
        client.request.assert_called_once_with("POST", "unbound/service/reconfigure")


class TestApplyDiff:
    def test_empty_diff_is_noop(self) -> None:
        client = MagicMock()
        svc = UnboundHostOverrideService(client)
        counts = svc.apply_diff(Diff())
        client.request.assert_not_called()
        assert counts == {"created": 0, "updated": 0, "deleted": 0}

    def test_add_does_not_call_reconfigure(self) -> None:
        # Per #776 the service no longer calls reconfigure inline; the
        # runner fires the shared ``unbound_reconfigure`` finalization
        # hook exactly once per apply across all three unbound managers.
        client = MagicMock()
        client.request.return_value = {"result": "saved"}
        svc = UnboundHostOverrideService(client)
        diff = Diff(adds=[_override("foo"), _override("bar", hostname="db2")])
        counts = svc.apply_diff(diff)
        endpoints = [c.args[1] for c in client.request.call_args_list]
        assert endpoints.count("unbound/settings/addHostOverride") == 2
        assert "unbound/service/reconfigure" not in endpoints
        assert counts == {"created": 2, "updated": 0, "deleted": 0}

    def test_update_does_not_call_reconfigure(self) -> None:
        client = MagicMock()
        client.request.return_value = {"result": "saved"}
        svc = UnboundHostOverrideService(client)
        live = _live_for_diff("u1")
        override = _override("foo")
        diff = Diff(updates=[(live, override)])
        counts = svc.apply_diff(diff)
        endpoints = [c.args[1] for c in client.request.call_args_list]
        assert "unbound/settings/setHostOverride/u1" in endpoints
        assert "unbound/service/reconfigure" not in endpoints
        assert counts == {"created": 0, "updated": 1, "deleted": 0}

    def test_delete_does_not_call_reconfigure(self) -> None:
        client = MagicMock()
        svc = UnboundHostOverrideService(client)
        diff = Diff(deletes=[_live_for_diff("u1"), _live_for_diff("u2", hostname="db2")])
        counts = svc.apply_diff(diff)
        endpoints = [c.args[1] for c in client.request.call_args_list]
        assert "unbound/settings/delHostOverride/u1" in endpoints
        assert "unbound/settings/delHostOverride/u2" in endpoints
        assert "unbound/service/reconfigure" not in endpoints
        assert counts == {"created": 0, "updated": 0, "deleted": 2}

    def test_mixed_diff_does_not_call_reconfigure(self) -> None:
        client = MagicMock()
        client.request.return_value = {"result": "saved"}
        svc = UnboundHostOverrideService(client)
        live_for_update = _live_for_diff("u1")
        live_for_delete = _live_for_diff("u2", hostname="db2")
        new = _override("new", hostname="db3")
        update_target = _override("foo", description="changed")
        diff = Diff(
            adds=[new],
            updates=[(live_for_update, update_target)],
            deletes=[live_for_delete],
        )
        counts = svc.apply_diff(diff)
        endpoints = [c.args[1] for c in client.request.call_args_list]
        assert "unbound/service/reconfigure" not in endpoints
        assert counts == {"created": 1, "updated": 1, "deleted": 1}


class TestComputeDiffServiceWrapper:
    def test_service_wrapper_delegates(self) -> None:
        client = MagicMock()
        svc = UnboundHostOverrideService(client)
        diff = svc.compute_diff([], [_live_for_diff("u1")], add_only=True)
        assert diff.deletes == []
