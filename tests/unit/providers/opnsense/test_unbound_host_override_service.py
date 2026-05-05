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
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import yaml

from infrafoundry.providers.opnsense.services.unbound_host_override import (
    LiveUnboundHostOverride,
    UnboundHostOverrideService,
    _live_to_export_config,
    _normalize_field,
    _row_to_live,
    _synthesize_name,
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
        assert "resources: []" in text

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
        assert "resources" in loaded
        assert len(loaded["resources"]) == 3

        web = loaded["resources"][0]
        assert web["provider"] == "opnsense"
        assert web["type"] == "unbound_host_override"
        assert web["name"] == "web-example-com"
        assert web["config"]["hostname"] == "web"
        assert web["config"]["domain"] == "example.com"
        assert web["config"]["server"] == "10.0.0.1"
        assert "rr" not in web["config"]

        web6 = loaded["resources"][1]
        assert web6["name"] == "web6-example-com-aaaa"
        assert web6["config"]["rr"] == "AAAA"
        assert web6["config"]["server"] == "2001:db8::1"

        mx = loaded["resources"][2]
        assert mx["name"] == "@-example-com-mx"
        assert mx["config"]["rr"] == "MX"
        assert mx["config"]["mxprio"] == "10"
        assert mx["config"]["mx"] == "mail.example.com"
        assert "server" not in mx["config"]

    def test_export_field_order_stable(self) -> None:
        # ``yaml.safe_dump(..., sort_keys=False)`` preserves insertion
        # order on the resource dict, so ``provider`` precedes ``type``
        # precedes ``name`` precedes ``config`` in the output. Operator
        # diffs are noisy if this churns.
        client = MagicMock()
        client.request.return_value = {"rows": [_row("web", "example.com", server="10.0.0.1")]}
        svc = UnboundHostOverrideService(client)
        text = svc.export_to_yaml()
        provider_idx = text.index("provider:")
        type_idx = text.index("type:")
        name_idx = text.index("name:")
        config_idx = text.index("config:")
        assert provider_idx < type_idx < name_idx < config_idx


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
