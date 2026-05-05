"""Unit tests for ``infrafoundry.providers.opnsense.services.alias``.

Coverage:
    - ``_row_to_live`` — wire row → ``LiveAlias`` with select-dict
      ``type`` normalization.
    - ``_split_content`` — newline-joined wire string → YAML list,
      dropping empties and trailing newlines.
    - ``_normalize_field`` — None / scalar / select-dict shapes.
    - ``_selected_uuids`` — selected-dict and comma-string fallback.
    - ``_live_to_export_config`` — base fields always emitted;
      type-specific fields (``proto``, ``updatefreq``, ``categories``,
      ``counters``, ``interface``) only when non-default.
    - ``AliasService.search`` — endpoint dispatch + defensive parsing.
    - ``AliasService.export_to_yaml`` — round-trip shape + multi-alias
      ordering + empty-state.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import yaml

from infrafoundry.providers.opnsense.services.alias import (
    AliasService,
    LiveAlias,
    _live_to_export_config,
    _normalize_field,
    _row_to_live,
    _selected_uuids,
    _split_content,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _row(
    name: str,
    *,
    uuid: str = "u1",
    type_value: str | dict[str, Any] = "host",
    description: str = "",
    content: str = "",
    enabled: str = "1",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a ``searchItem`` row mimicking what OPNsense returns."""
    row: dict[str, Any] = {
        "uuid": uuid,
        "name": name,
        "type": type_value,
        "description": description,
        "content": content,
        "enabled": enabled,
    }
    if extra:
        row.update(extra)
    return row


def _selected_type(value: str) -> dict[str, Any]:
    """Build a select-dict like OPNsense's ``searchItem`` returns for ``type``."""
    return {value: {"value": value.title(), "selected": 1}}


# ---------------------------------------------------------------------------
# _normalize_field
# ---------------------------------------------------------------------------


class TestNormalizeField:
    def test_none_becomes_empty(self) -> None:
        assert _normalize_field(None) == ""

    def test_string_passthrough(self) -> None:
        assert _normalize_field("host") == "host"

    def test_int_stringified(self) -> None:
        assert _normalize_field(42) == "42"

    def test_select_dict_extracts_selected_key(self) -> None:
        value = {
            "host": {"value": "Host(s)", "selected": 1},
            "network": {"value": "Network(s)", "selected": 0},
        }
        assert _normalize_field(value) == "host"

    def test_select_dict_no_selection_returns_empty(self) -> None:
        value = {"host": {"value": "Host(s)", "selected": 0}}
        assert _normalize_field(value) == ""


# ---------------------------------------------------------------------------
# _split_content
# ---------------------------------------------------------------------------


class TestSplitContent:
    def test_empty_string_returns_empty_list(self) -> None:
        assert _split_content("") == []

    def test_none_returns_empty_list(self) -> None:
        assert _split_content(None) == []

    def test_non_string_returns_empty_list(self) -> None:
        assert _split_content(["10.0.0.1"]) == []

    def test_single_value_returns_singleton(self) -> None:
        assert _split_content("10.0.0.1") == ["10.0.0.1"]

    def test_multiline_splits(self) -> None:
        assert _split_content("10.0.0.1\n10.0.0.2") == ["10.0.0.1", "10.0.0.2"]

    def test_trailing_newline_dropped(self) -> None:
        assert _split_content("10.0.0.1\n10.0.0.2\n") == ["10.0.0.1", "10.0.0.2"]

    def test_blank_lines_dropped(self) -> None:
        assert _split_content("10.0.0.1\n\n10.0.0.2") == ["10.0.0.1", "10.0.0.2"]

    def test_lines_stripped(self) -> None:
        assert _split_content("  10.0.0.1  \n\t10.0.0.2\n") == ["10.0.0.1", "10.0.0.2"]


# ---------------------------------------------------------------------------
# _selected_uuids
# ---------------------------------------------------------------------------


class TestSelectedUuids:
    def test_select_dict_extracts_selected(self) -> None:
        value = {
            "uuid-a": {"value": "Cat A", "selected": 1},
            "uuid-b": {"value": "Cat B", "selected": 0},
            "uuid-c": {"value": "Cat C", "selected": 1},
        }
        assert _selected_uuids(value) == ["uuid-a", "uuid-c"]

    def test_no_selection_returns_empty(self) -> None:
        value = {"uuid-a": {"value": "Cat A", "selected": 0}}
        assert _selected_uuids(value) == []

    def test_comma_string_fallback(self) -> None:
        # OPNsense versions where the wire shape is a comma-string.
        assert _selected_uuids("uuid-b,uuid-a,uuid-c") == ["uuid-a", "uuid-b", "uuid-c"]

    def test_comma_string_strips_whitespace(self) -> None:
        assert _selected_uuids("uuid-a, uuid-b , uuid-c") == ["uuid-a", "uuid-b", "uuid-c"]

    def test_empty_string_returns_empty(self) -> None:
        assert _selected_uuids("") == []

    def test_none_returns_empty(self) -> None:
        assert _selected_uuids(None) == []


# ---------------------------------------------------------------------------
# _row_to_live
# ---------------------------------------------------------------------------


class TestRowToLive:
    def test_simple_host_row(self) -> None:
        row = _row("web-servers", type_value="host", content="10.0.0.1")
        live = _row_to_live(row)
        assert live.uuid == "u1"
        assert live.name == "web-servers"
        assert live.type == "host"
        assert live.raw == row

    def test_select_dict_type_normalized(self) -> None:
        row = _row("g", type_value=_selected_type("geoip"))
        live = _row_to_live(row)
        assert live.type == "geoip"

    def test_missing_uuid_defaults_to_empty(self) -> None:
        live = _row_to_live({"name": "x", "type": "host"})
        assert live.uuid == ""

    def test_missing_name_defaults_to_empty(self) -> None:
        live = _row_to_live({"uuid": "u1", "type": "host"})
        assert live.name == ""


# ---------------------------------------------------------------------------
# _live_to_export_config
# ---------------------------------------------------------------------------


class TestLiveToExportConfig:
    def test_simple_host_alias(self) -> None:
        live = _row_to_live(
            _row(
                "web-servers",
                type_value="host",
                description="Web tier",
                content="10.0.0.1",
            )
        )
        cfg = _live_to_export_config(live)
        assert cfg["name"] == "web-servers"
        assert cfg["type"] == "host"
        assert cfg["description"] == "Web tier"
        assert cfg["content"] == ["10.0.0.1"]
        assert cfg["enabled"] is True

    def test_multiline_content_splits(self) -> None:
        live = _row_to_live(_row("hosts", type_value="host", content="10.0.0.1\n10.0.0.2\n"))
        cfg = _live_to_export_config(live)
        assert cfg["content"] == ["10.0.0.1", "10.0.0.2"]

    def test_geoip_alias_emits_proto(self) -> None:
        live = _row_to_live(
            _row(
                "geo-eu",
                type_value=_selected_type("geoip"),
                content="DE\nFR\nIT",
                extra={"proto": _selected_type("IPv4")},
            )
        )
        cfg = _live_to_export_config(live)
        assert cfg["type"] == "geoip"
        assert cfg["proto"] == "IPv4"

    def test_urltable_alias_emits_updatefreq(self) -> None:
        live = _row_to_live(
            _row(
                "block-list",
                type_value=_selected_type("urltable"),
                content="https://example.com/list.txt",
                extra={"updatefreq": "7"},
            )
        )
        cfg = _live_to_export_config(live)
        assert cfg["type"] == "urltable"
        assert cfg["updatefreq"] == "7"

    def test_urltable_updatefreq_decimal_preserved(self) -> None:
        # Operator-set fractional days must round-trip verbatim.
        live = _row_to_live(
            _row(
                "block-list",
                type_value=_selected_type("urltable"),
                content="https://example.com/list.txt",
                extra={"updatefreq": "0.5"},
            )
        )
        cfg = _live_to_export_config(live)
        assert cfg["updatefreq"] == "0.5"

    def test_dynipv6host_emits_interface(self) -> None:
        live = _row_to_live(
            _row(
                "ipv6-host",
                type_value=_selected_type("dynipv6host"),
                content="::1",
                extra={"interface": _selected_type("lan")},
            )
        )
        cfg = _live_to_export_config(live)
        assert cfg["type"] == "dynipv6host"
        assert cfg["interface"] == "lan"

    def test_categories_select_dict_normalized(self) -> None:
        live = _row_to_live(
            _row(
                "alias",
                type_value="host",
                content="10.0.0.1",
                extra={
                    "categories": {
                        "uuid-b": {"value": "Cat B", "selected": 1},
                        "uuid-a": {"value": "Cat A", "selected": 1},
                        "uuid-c": {"value": "Cat C", "selected": 0},
                    }
                },
            )
        )
        cfg = _live_to_export_config(live)
        # Sorted for stable diffing.
        assert cfg["categories"] == ["uuid-a", "uuid-b"]

    def test_categories_comma_string_normalized(self) -> None:
        live = _row_to_live(
            _row(
                "alias",
                type_value="host",
                content="10.0.0.1",
                extra={"categories": "uuid-b,uuid-a"},
            )
        )
        cfg = _live_to_export_config(live)
        assert cfg["categories"] == ["uuid-a", "uuid-b"]

    def test_counters_true_emitted(self) -> None:
        live = _row_to_live(
            _row(
                "alias",
                type_value="host",
                content="10.0.0.1",
                extra={"counters": "1"},
            )
        )
        cfg = _live_to_export_config(live)
        assert cfg["counters"] is True

    def test_counters_false_omitted(self) -> None:
        live = _row_to_live(
            _row(
                "alias",
                type_value="host",
                content="10.0.0.1",
                extra={"counters": "0"},
            )
        )
        cfg = _live_to_export_config(live)
        assert "counters" not in cfg

    def test_counters_missing_omitted(self) -> None:
        live = _row_to_live(_row("alias", type_value="host", content="10.0.0.1"))
        cfg = _live_to_export_config(live)
        assert "counters" not in cfg

    def test_enabled_default_true_when_missing(self) -> None:
        # Defensive: missing ``enabled`` should default to True (no
        # alias is created disabled by default).
        row = {
            "uuid": "u1",
            "name": "alias",
            "type": "host",
            "description": "",
            "content": "10.0.0.1",
        }
        live = _row_to_live(row)
        cfg = _live_to_export_config(live)
        assert cfg["enabled"] is True

    def test_enabled_zero_returns_false(self) -> None:
        live = _row_to_live(_row("alias", type_value="host", content="10.0.0.1", enabled="0"))
        cfg = _live_to_export_config(live)
        assert cfg["enabled"] is False

    def test_optional_fields_omitted_when_absent(self) -> None:
        # A bare host alias must not carry any of the type-specific
        # keys — keeps existing operator YAML round-tripping identical.
        live = _row_to_live(_row("alias", type_value="host", content="10.0.0.1"))
        cfg = _live_to_export_config(live)
        for key in ("proto", "updatefreq", "categories", "counters", "interface"):
            assert key not in cfg

    def test_description_passthrough(self) -> None:
        live = _row_to_live(
            _row(
                "alias",
                type_value="host",
                description="Production web tier",
                content="10.0.0.1",
            )
        )
        cfg = _live_to_export_config(live)
        assert cfg["description"] == "Production web tier"

    def test_description_empty_preserved_as_empty(self) -> None:
        live = _row_to_live(_row("alias", type_value="host", content="10.0.0.1"))
        cfg = _live_to_export_config(live)
        assert cfg["description"] == ""


# ---------------------------------------------------------------------------
# AliasService.search
# ---------------------------------------------------------------------------


class TestServiceSearch:
    def test_search_calls_correct_endpoint(self) -> None:
        client = MagicMock()
        client.request.return_value = {"rows": []}
        svc = AliasService(client)
        result = svc.search()
        client.request.assert_called_once_with("POST", "firewall/alias/searchItem")
        assert result == []

    def test_search_normalizes_rows(self) -> None:
        client = MagicMock()
        client.request.return_value = {
            "rows": [
                _row("a", uuid="u1", type_value="host"),
                "not-a-dict",
                _row("b", uuid="u2", type_value=_selected_type("network")),
            ]
        }
        svc = AliasService(client)
        result = svc.search()
        assert len(result) == 2
        assert result[0].uuid == "u1"
        assert result[0].name == "a"
        assert result[0].type == "host"
        assert result[1].uuid == "u2"
        assert result[1].type == "network"

    def test_search_handles_non_dict_response(self) -> None:
        client = MagicMock()
        client.request.return_value = "not-a-dict"
        svc = AliasService(client)
        assert svc.search() == []

    def test_search_handles_missing_rows_key(self) -> None:
        client = MagicMock()
        client.request.return_value = {}
        svc = AliasService(client)
        assert svc.search() == []

    def test_search_handles_non_list_rows_value(self) -> None:
        client = MagicMock()
        client.request.return_value = {"rows": "not-a-list"}
        svc = AliasService(client)
        assert svc.search() == []


# ---------------------------------------------------------------------------
# AliasService.export_to_yaml
# ---------------------------------------------------------------------------


class TestExportToYaml:
    def test_aliases_appear_in_export(self) -> None:
        client = MagicMock()
        client.request.return_value = {
            "rows": [
                _row(
                    "web-servers",
                    uuid="u1",
                    type_value=_selected_type("host"),
                    description="Web tier",
                    content="10.0.0.1\n10.0.0.2",
                ),
            ]
        }
        svc = AliasService(client)
        text = svc.export_to_yaml()
        assert "name: web-servers" in text
        assert "type: host" in text
        assert "description: Web tier" in text
        assert "10.0.0.1" in text
        assert "10.0.0.2" in text
        assert "enabled: true" in text

    def test_export_with_no_aliases_yields_empty_resources(self) -> None:
        client = MagicMock()
        client.request.return_value = {"rows": []}
        svc = AliasService(client)
        text = svc.export_to_yaml()
        assert "resources: []" in text

    def test_export_round_trip_loads_back_to_dict(self) -> None:
        client = MagicMock()
        client.request.return_value = {
            "rows": [
                _row(
                    "web-servers",
                    uuid="u1",
                    type_value=_selected_type("host"),
                    description="Web tier",
                    content="10.0.0.1",
                ),
                _row(
                    "geo-eu",
                    uuid="u2",
                    type_value=_selected_type("geoip"),
                    content="DE\nFR",
                    extra={"proto": _selected_type("IPv4")},
                ),
            ]
        }
        svc = AliasService(client)
        text = svc.export_to_yaml()
        loaded = yaml.safe_load(text)
        assert "resources" in loaded
        assert len(loaded["resources"]) == 2

        web = loaded["resources"][0]
        assert web["provider"] == "opnsense"
        assert web["type"] == "aliases"
        assert web["name"] == "web-servers"
        assert web["config"]["name"] == "web-servers"
        assert web["config"]["type"] == "host"
        assert web["config"]["content"] == ["10.0.0.1"]
        assert "proto" not in web["config"]

        geo = loaded["resources"][1]
        assert geo["name"] == "geo-eu"
        assert geo["config"]["type"] == "geoip"
        assert geo["config"]["proto"] == "IPv4"
        assert geo["config"]["content"] == ["DE", "FR"]

    def test_export_field_order_stable(self) -> None:
        # ``yaml.safe_dump(..., sort_keys=False)`` preserves insertion
        # order on the resource dict, so ``provider`` precedes ``type``
        # precedes ``name`` precedes ``config`` in the output. Operator
        # diffs are noisy if this churns.
        client = MagicMock()
        client.request.return_value = {
            "rows": [_row("alias", type_value="host", content="10.0.0.1")]
        }
        svc = AliasService(client)
        text = svc.export_to_yaml()
        provider_idx = text.index("provider:")
        type_idx = text.index("type:")
        name_idx = text.index("name:")
        config_idx = text.index("config:")
        assert provider_idx < type_idx < name_idx < config_idx

    def test_system_alias_types_filtered(self) -> None:
        # ``internal`` and ``external`` types are OPNsense-managed
        # auto-generated entries (e.g., ``__lan_network``, ``bogons``)
        # that the operator cannot write via the alias controller.
        # Including them would produce YAML that the terraform write
        # path tries to (re)create on apply.
        client = MagicMock()
        client.request.return_value = {
            "rows": [
                _row("__lan_network", type_value=_selected_type("internal")),
                _row("bogons", type_value=_selected_type("external")),
                _row("web-servers", type_value=_selected_type("host"), content="10.0.0.1"),
            ]
        }
        svc = AliasService(client)
        loaded = yaml.safe_load(svc.export_to_yaml())
        names = [r["name"] for r in loaded["resources"]]
        assert names == ["web-servers"]

    def test_system_alias_only_box_yields_empty_resources(self) -> None:
        # A box with only OPNsense-internal aliases (no operator
        # entries) round-trips to an empty resource list, not a list of
        # un-applyable system entries. Mirrors the ``prod-mirror``
        # bare-box scenario.
        client = MagicMock()
        client.request.return_value = {
            "rows": [
                _row("__lan_network", type_value=_selected_type("internal")),
                _row("__wan_network", type_value=_selected_type("internal")),
                _row("bogons", type_value=_selected_type("external")),
                _row("sshlockout", type_value=_selected_type("external")),
            ]
        }
        svc = AliasService(client)
        text = svc.export_to_yaml()
        assert "resources: []" in text


# ---------------------------------------------------------------------------
# LiveAlias dataclass
# ---------------------------------------------------------------------------


class TestLiveAlias:
    def test_dataclass_default_raw_is_empty_dict(self) -> None:
        live = LiveAlias(uuid="u1", name="x", type="host")
        assert live.raw == {}

    def test_frozen(self) -> None:
        # Defensive: dataclass is frozen so live records can't be mutated
        # in place by callers. Use ``dataclasses.replace`` if needed.
        live = LiveAlias(uuid="u1", name="x", type="host")
        try:
            live.uuid = "other"  # type: ignore[misc]
        except Exception:
            return
        raise AssertionError("LiveAlias should be frozen")
