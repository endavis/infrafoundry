"""Unit tests for ``infrafoundry.providers.opnsense.services.alias`` (#747, #775).

Coverage:
    - Read-side helpers (preserved from #747): ``_row_to_live``,
      ``_split_content``, ``_normalize_field``, ``_selected_uuids``,
      ``_live_to_export_config``.
    - ``AliasService.search`` and ``export_to_yaml`` (read path
      preserved unchanged from #747).
    - Write surface (#775): ``AliasConfig.to_payload`` envelope shape,
      ``compute_diff`` adds/updates/deletes/lock/add-only,
      ``alias_configs_from_resources`` parser, CRUD endpoint dispatch
      through ``OPNsenseClient.request``, ``apply_diff`` orchestration
      (single ``reconfigure`` per apply when changes occurred).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
import yaml

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.services.alias import (
    AliasConfig,
    AliasService,
    Diff,
    LiveAlias,
    _live_to_export_config,
    _normalize_field,
    _row_to_live,
    _selected_uuids,
    _split_content,
    alias_configs_from_resources,
    compute_diff,
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


def _alias(
    name: str,
    *,
    type: str = "host",
    description: str = "",
    content: tuple[str, ...] = (),
    enabled: bool = True,
    proto: str = "",
    updatefreq: str = "",
    categories: tuple[str, ...] = (),
    counters: bool = False,
    interface: str = "",
    lock: bool = False,
) -> AliasConfig:
    return AliasConfig(
        name=name,
        type=type,
        description=description,
        content=content,
        enabled=enabled,
        proto=proto,
        updatefreq=updatefreq,
        categories=categories,
        counters=counters,
        interface=interface,
        lock=lock,
    )


def _live(
    uuid: str,
    *,
    name: str = "web-servers",
    alias_type: str = "host",
    description: str = "",
    content: str = "",
    enabled: str = "1",
    extra: dict[str, Any] | None = None,
) -> LiveAlias:
    raw = _row(
        name,
        uuid=uuid,
        type_value=alias_type,
        description=description,
        content=content,
        enabled=enabled,
        extra=extra,
    )
    return LiveAlias(uuid=uuid, name=name, type=alias_type, raw=raw)


def _resource(name: str, config: dict[str, Any]) -> ResourceConfig:
    return ResourceConfig(name=name, type="firewall.aliases", provider="opnsense", config=config)


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
                "ipv6_host",
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

    def test_enabled_zero_returns_false(self) -> None:
        live = _row_to_live(_row("alias", type_value="host", content="10.0.0.1", enabled="0"))
        cfg = _live_to_export_config(live)
        assert cfg["enabled"] is False

    def test_optional_fields_omitted_when_absent(self) -> None:
        # A bare host alias must not carry any of the type-specific keys —
        # keeps existing operator YAML round-tripping identical.
        live = _row_to_live(_row("alias", type_value="host", content="10.0.0.1"))
        cfg = _live_to_export_config(live)
        for key in ("proto", "updatefreq", "categories", "counters", "interface"):
            assert key not in cfg


# ---------------------------------------------------------------------------
# AliasConfig.to_payload
# ---------------------------------------------------------------------------


class TestPayload:
    def test_payload_has_envelope(self) -> None:
        payload = _alias("foo").to_payload()
        assert set(payload.keys()) == {"alias"}

    def test_payload_field_set(self) -> None:
        alias = _alias(
            "web_servers",
            type="host",
            description="Web tier",
            content=("10.0.0.1", "10.0.0.2"),
        )
        inner = alias.to_payload()["alias"]
        assert inner["name"] == "web_servers"
        assert inner["type"] == "host"
        assert inner["description"] == "Web tier"
        assert inner["content"] == "10.0.0.1\n10.0.0.2"

    def test_enabled_true_serializes_one(self) -> None:
        inner = _alias("foo", enabled=True).to_payload()["alias"]
        assert inner["enabled"] == "1"

    def test_enabled_false_serializes_zero(self) -> None:
        inner = _alias("foo", enabled=False).to_payload()["alias"]
        assert inner["enabled"] == "0"

    def test_counters_true_serializes_one(self) -> None:
        inner = _alias("foo", counters=True).to_payload()["alias"]
        assert inner["counters"] == "1"

    def test_counters_false_serializes_zero(self) -> None:
        inner = _alias("foo").to_payload()["alias"]
        assert inner["counters"] == "0"

    def test_categories_join_to_comma_string(self) -> None:
        inner = _alias("foo", categories=("uuid-a", "uuid-b")).to_payload()["alias"]
        assert inner["categories"] == "uuid-a,uuid-b"

    def test_empty_categories_become_empty_string(self) -> None:
        inner = _alias("foo").to_payload()["alias"]
        assert inner["categories"] == ""

    def test_empty_content_becomes_empty_string(self) -> None:
        inner = _alias("foo").to_payload()["alias"]
        assert inner["content"] == ""


class TestDiffKey:
    def test_diff_key_is_name(self) -> None:
        assert _alias("web_servers").diff_key == "web_servers"

    def test_live_diff_key_is_name(self) -> None:
        live = _live("u1", name="web_servers")
        assert live.diff_key == "web_servers"


# ---------------------------------------------------------------------------
# compute_diff
# ---------------------------------------------------------------------------


class TestComputeDiffEmpty:
    def test_no_desired_no_live_is_empty(self) -> None:
        diff = compute_diff([], [])
        assert diff.is_empty
        assert diff.adds == []
        assert diff.deletes == []
        assert diff.updates == []
        assert diff.locked == []


class TestComputeDiffAdds:
    def test_new_alias_adds(self) -> None:
        diff = compute_diff([_alias("web_servers", content=("10.0.0.1",))], [])
        assert len(diff.adds) == 1
        assert diff.adds[0].name == "web_servers"


class TestComputeDiffUpdates:
    def test_update_when_description_changes(self) -> None:
        alias = _alias("web_servers", content=("10.0.0.1",), description="new desc")
        live = _live(
            "u1",
            name="web_servers",
            description="old desc",
            content="10.0.0.1",
        )
        diff = compute_diff([alias], [live])
        assert len(diff.updates) == 1
        live_record, want = diff.updates[0]
        assert live_record.uuid == "u1"
        assert want.description == "new desc"

    def test_update_when_enabled_flips(self) -> None:
        alias = _alias("web_servers", enabled=False, content=("10.0.0.1",))
        live = _live("u1", name="web_servers", enabled="1", content="10.0.0.1")
        diff = compute_diff([alias], [live])
        assert len(diff.updates) == 1

    def test_update_when_content_changes(self) -> None:
        alias = _alias("web_servers", content=("10.0.0.1", "10.0.0.2"))
        live = _live("u1", name="web_servers", content="10.0.0.1")
        diff = compute_diff([alias], [live])
        assert len(diff.updates) == 1

    def test_update_when_counters_flips(self) -> None:
        alias = _alias("web_servers", content=("10.0.0.1",), counters=True)
        live = _live(
            "u1",
            name="web_servers",
            content="10.0.0.1",
            extra={"counters": "0"},
        )
        diff = compute_diff([alias], [live])
        assert len(diff.updates) == 1

    def test_no_update_when_payload_matches(self) -> None:
        # Build a live record carrying every field with default values
        # to verify the ``_needs_update`` engine compares apples to apples.
        alias = _alias("web_servers", content=("10.0.0.1",))
        live = _live(
            "u1",
            name="web_servers",
            content="10.0.0.1",
            extra={
                "proto": "",
                "updatefreq": "",
                "categories": "",
                "counters": "0",
                "interface": "",
            },
        )
        diff = compute_diff([alias], [live])
        assert diff.is_empty

    def test_changing_name_is_delete_plus_add(self) -> None:
        # Identity changed — old record has no YAML counterpart (delete)
        # and new name has no live counterpart (add).
        live = _live("u1", name="web_servers")
        new_alias = _alias("web_servers_renamed")
        diff = compute_diff([new_alias], [live])
        assert len(diff.adds) == 1
        assert diff.adds[0].name == "web_servers_renamed"
        assert len(diff.deletes) == 1
        assert diff.deletes[0].uuid == "u1"


class TestComputeDiffDeletes:
    def test_live_with_no_desired_is_deleted(self) -> None:
        diff = compute_diff([], [_live("u1")])
        assert len(diff.deletes) == 1
        assert diff.deletes[0].uuid == "u1"

    def test_add_only_suppresses_deletes(self) -> None:
        diff = compute_diff([], [_live("u1")], add_only=True)
        assert diff.deletes == []
        assert diff.is_empty

    def test_add_only_still_emits_updates(self) -> None:
        alias = _alias("web_servers", content=("10.0.0.1",), description="changed")
        live = _live(
            "u1",
            name="web_servers",
            description="old",
            content="10.0.0.1",
        )
        diff = compute_diff([alias], [live], add_only=True)
        assert len(diff.updates) == 1


class TestComputeDiffSystemFiltering:
    def test_internal_alias_excluded_from_deletes(self) -> None:
        # __lan_network is type=internal; OPNsense regenerates it from
        # interface state and the operator can't write or remove it.
        # The diff engine must filter it before computing deletes.
        live = LiveAlias(
            uuid="i1",
            name="__lan_network",
            type="internal",
            raw={"uuid": "i1", "name": "__lan_network", "type": "internal"},
        )
        diff = compute_diff([], [live])
        assert diff.deletes == []
        assert diff.is_empty

    def test_external_alias_excluded_from_deletes(self) -> None:
        live = LiveAlias(
            uuid="e1",
            name="bogons",
            type="external",
            raw={"uuid": "e1", "name": "bogons", "type": "external"},
        )
        diff = compute_diff([], [live])
        assert diff.deletes == []
        assert diff.is_empty

    def test_managed_alias_unaffected_by_system_filter(self) -> None:
        # System aliases coexisting with managed aliases must not affect
        # the diff for the managed entries.
        managed = _live("m1", name="web_servers", content="10.0.0.1")
        system = LiveAlias(
            uuid="i1",
            name="__lan_network",
            type="internal",
            raw={"uuid": "i1", "name": "__lan_network", "type": "internal"},
        )
        diff = compute_diff([], [managed, system])
        # Only the managed alias appears as a delete; system alias is filtered.
        assert len(diff.deletes) == 1
        assert diff.deletes[0].name == "web_servers"


class TestComputeDiffLocked:
    def test_locked_resource_with_match_skipped_from_actions(self) -> None:
        alias = _alias("survival", content=("10.0.0.1",), description="locked", lock=True)
        live = _live(
            "u1",
            name="survival",
            description="drift!",
            content="10.0.0.1",
        )
        diff = compute_diff([alias], [live])
        assert diff.adds == []
        assert diff.updates == []
        assert diff.deletes == []
        assert len(diff.locked) == 1
        want, have = diff.locked[0]
        assert want.lock is True
        assert have is not None
        assert have.uuid == "u1"

    def test_locked_resource_without_match(self) -> None:
        alias = _alias("missing", lock=True)
        diff = compute_diff([alias], [])
        assert len(diff.locked) == 1
        _want, have = diff.locked[0]
        assert have is None


class TestDiffIsEmpty:
    def test_empty_diff(self) -> None:
        assert Diff().is_empty

    def test_locked_alone_counts_as_empty(self) -> None:
        diff = Diff(locked=[(_alias("foo", lock=True), None)])
        assert diff.is_empty

    def test_non_empty_when_adds(self) -> None:
        diff = Diff(adds=[_alias("foo")])
        assert not diff.is_empty

    def test_non_empty_when_updates(self) -> None:
        diff = Diff(updates=[(_live("u1"), _alias("foo"))])
        assert not diff.is_empty

    def test_non_empty_when_deletes(self) -> None:
        diff = Diff(deletes=[_live("u1")])
        assert not diff.is_empty


# ---------------------------------------------------------------------------
# alias_configs_from_resources
# ---------------------------------------------------------------------------


class TestConfigsFromResources:
    def test_valid_parses(self) -> None:
        r = _resource(
            "web_servers",
            {
                "name": "web_servers",
                "type": "host",
                "description": "lan",
                "content": ["10.0.0.1"],
            },
        )
        result = alias_configs_from_resources([r])
        assert len(result) == 1
        cfg = result[0]
        assert cfg.name == "web_servers"
        assert cfg.type == "host"
        assert cfg.description == "lan"
        assert cfg.content == ("10.0.0.1",)

    def test_default_enabled_true(self) -> None:
        r = _resource("foo", {"name": "foo", "type": "host"})
        cfg = alias_configs_from_resources([r])[0]
        assert cfg.enabled is True

    def test_explicit_enabled_false(self) -> None:
        r = _resource("foo", {"name": "foo", "type": "host", "enabled": False})
        cfg = alias_configs_from_resources([r])[0]
        assert cfg.enabled is False

    def test_default_counters_false(self) -> None:
        r = _resource("foo", {"name": "foo", "type": "host"})
        cfg = alias_configs_from_resources([r])[0]
        assert cfg.counters is False

    def test_explicit_counters_true(self) -> None:
        r = _resource("foo", {"name": "foo", "type": "host", "counters": True})
        cfg = alias_configs_from_resources([r])[0]
        assert cfg.counters is True

    def test_lock_passthrough(self) -> None:
        r = _resource("foo", {"name": "foo", "type": "host", "lock": True})
        cfg = alias_configs_from_resources([r])[0]
        assert cfg.lock is True

    def test_falls_back_to_resource_name_when_config_name_omitted(self) -> None:
        # ``config.name`` is the wire identity; if the operator drops it
        # we fall back to the operator-facing top-level name.
        r = _resource("web_servers", {"type": "host"})
        cfg = alias_configs_from_resources([r])[0]
        assert cfg.name == "web_servers"

    def test_missing_type_rejected(self) -> None:
        r = _resource("bad", {"name": "bad"})
        with pytest.raises(ValueError, match="type"):
            alias_configs_from_resources([r])

    def test_empty_type_rejected(self) -> None:
        r = _resource("bad", {"name": "bad", "type": ""})
        with pytest.raises(ValueError, match="type"):
            alias_configs_from_resources([r])

    def test_non_string_description_rejected(self) -> None:
        r = _resource(
            "bad",
            {"name": "bad", "type": "host", "description": 12345},
        )
        with pytest.raises(ValueError, match="description"):
            alias_configs_from_resources([r])

    def test_non_list_content_rejected(self) -> None:
        r = _resource(
            "bad",
            {"name": "bad", "type": "host", "content": "10.0.0.1"},
        )
        with pytest.raises(ValueError, match="content"):
            alias_configs_from_resources([r])

    def test_non_string_content_entry_rejected(self) -> None:
        r = _resource(
            "bad",
            {"name": "bad", "type": "host", "content": [123]},
        )
        with pytest.raises(ValueError, match="content"):
            alias_configs_from_resources([r])

    def test_non_string_proto_rejected(self) -> None:
        r = _resource(
            "bad",
            {"name": "bad", "type": "geoip", "proto": 4},
        )
        with pytest.raises(ValueError, match="proto"):
            alias_configs_from_resources([r])

    def test_non_string_updatefreq_rejected(self) -> None:
        r = _resource(
            "bad",
            {"name": "bad", "type": "urltable", "updatefreq": 0.5},
        )
        with pytest.raises(ValueError, match="updatefreq"):
            alias_configs_from_resources([r])

    def test_non_list_categories_rejected(self) -> None:
        r = _resource(
            "bad",
            {"name": "bad", "type": "host", "categories": "uuid-a"},
        )
        with pytest.raises(ValueError, match="categories"):
            alias_configs_from_resources([r])

    def test_non_string_categories_entry_rejected(self) -> None:
        r = _resource(
            "bad",
            {"name": "bad", "type": "host", "categories": [123]},
        )
        with pytest.raises(ValueError, match="categories"):
            alias_configs_from_resources([r])

    def test_non_bool_enabled_rejected(self) -> None:
        r = _resource(
            "bad",
            {"name": "bad", "type": "host", "enabled": "yes"},
        )
        with pytest.raises(ValueError, match="enabled"):
            alias_configs_from_resources([r])

    def test_non_bool_counters_rejected(self) -> None:
        r = _resource(
            "bad",
            {"name": "bad", "type": "host", "counters": "yes"},
        )
        with pytest.raises(ValueError, match="counters"):
            alias_configs_from_resources([r])

    def test_non_bool_lock_rejected(self) -> None:
        r = _resource(
            "bad",
            {"name": "bad", "type": "host", "lock": "yes"},
        )
        with pytest.raises(ValueError, match="lock"):
            alias_configs_from_resources([r])

    def test_non_dict_config_rejected(self) -> None:
        r = ResourceConfig(
            name="bad",
            type="firewall.aliases",
            provider="opnsense",
            config={"name": "bad", "type": "host"},
        )
        # Bypass pydantic — guard the service-side defensive check.
        r.config = "not-a-dict"  # type: ignore[assignment]
        with pytest.raises(ValueError, match="non-dict"):
            alias_configs_from_resources([r])

    def test_non_aliases_resources_ignored(self) -> None:
        ok = _resource("ok", {"name": "ok", "type": "host"})
        other = ResourceConfig(name="x", type="interfaces.vlans", provider="opnsense", config={})
        result = alias_configs_from_resources([ok, other])
        assert len(result) == 1
        assert result[0].name == "ok"


# ---------------------------------------------------------------------------
# AliasService API methods
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


class TestServiceGet:
    def test_get_uses_get_verb(self) -> None:
        client = MagicMock()
        client.request.return_value = {"alias": {"name": "web_servers"}}
        svc = AliasService(client)
        result = svc.get("u1")
        client.request.assert_called_once_with("GET", "firewall/alias/getItem/u1")
        assert result == {"alias": {"name": "web_servers"}}


class TestServiceWriteOps:
    def test_add_posts_correct_endpoint(self) -> None:
        client = MagicMock()
        client.request.return_value = {"result": "saved", "uuid": "new"}
        svc = AliasService(client)
        alias = _alias("web_servers", content=("10.0.0.1",))
        svc.add(alias)
        client.request.assert_called_once_with(
            "POST", "firewall/alias/addItem", data=alias.to_payload()
        )

    def test_update_posts_correct_endpoint(self) -> None:
        client = MagicMock()
        client.request.return_value = {"result": "saved"}
        svc = AliasService(client)
        alias = _alias("web_servers")
        svc.update("uuid-abc", alias)
        client.request.assert_called_once_with(
            "POST", "firewall/alias/setItem/uuid-abc", data=alias.to_payload()
        )

    def test_delete_posts_correct_endpoint(self) -> None:
        client = MagicMock()
        svc = AliasService(client)
        svc.delete("u1")
        client.request.assert_called_once_with("POST", "firewall/alias/delItem/u1")

    def test_reconfigure_posts_correct_endpoint(self) -> None:
        client = MagicMock()
        svc = AliasService(client)
        svc.reconfigure()
        client.request.assert_called_once_with("POST", "firewall/alias/reconfigure")

    def test_add_failure_raises(self) -> None:
        # Service does not swallow API errors — they propagate up to the
        # manager which converts them into ApplyResult.error.
        client = MagicMock()
        client.request.side_effect = RuntimeError("API failure")
        svc = AliasService(client)
        with pytest.raises(RuntimeError, match="API failure"):
            svc.add(_alias("foo"))


class TestApplyDiff:
    def test_empty_diff_is_noop(self) -> None:
        client = MagicMock()
        svc = AliasService(client)
        counts = svc.apply_diff(Diff())
        client.request.assert_not_called()
        assert counts == {"created": 0, "updated": 0, "deleted": 0}

    def test_add_calls_reconfigure_once(self) -> None:
        client = MagicMock()
        client.request.return_value = {"result": "saved"}
        svc = AliasService(client)
        diff = Diff(adds=[_alias("a"), _alias("b")])
        counts = svc.apply_diff(diff)
        endpoints = [c.args[1] for c in client.request.call_args_list]
        assert endpoints.count("firewall/alias/addItem") == 2
        assert endpoints.count("firewall/alias/reconfigure") == 1
        assert counts == {"created": 2, "updated": 0, "deleted": 0}

    def test_update_calls_reconfigure_once(self) -> None:
        client = MagicMock()
        client.request.return_value = {"result": "saved"}
        svc = AliasService(client)
        live = _live("u1")
        alias = _alias("web_servers")
        diff = Diff(updates=[(live, alias)])
        counts = svc.apply_diff(diff)
        endpoints = [c.args[1] for c in client.request.call_args_list]
        assert "firewall/alias/setItem/u1" in endpoints
        assert endpoints.count("firewall/alias/reconfigure") == 1
        assert counts == {"created": 0, "updated": 1, "deleted": 0}

    def test_delete_calls_reconfigure_once(self) -> None:
        client = MagicMock()
        svc = AliasService(client)
        diff = Diff(
            deletes=[
                _live("u1", name="a"),
                _live("u2", name="b"),
            ]
        )
        counts = svc.apply_diff(diff)
        endpoints = [c.args[1] for c in client.request.call_args_list]
        assert "firewall/alias/delItem/u1" in endpoints
        assert "firewall/alias/delItem/u2" in endpoints
        assert endpoints.count("firewall/alias/reconfigure") == 1
        assert counts == {"created": 0, "updated": 0, "deleted": 2}

    def test_mixed_diff_single_reconfigure(self) -> None:
        client = MagicMock()
        client.request.return_value = {"result": "saved"}
        svc = AliasService(client)
        live_for_update = _live("u1", name="a")
        live_for_delete = _live("u2", name="b")
        new = _alias("new")
        update_target = _alias("a", description="changed")
        diff = Diff(
            adds=[new],
            updates=[(live_for_update, update_target)],
            deletes=[live_for_delete],
        )
        counts = svc.apply_diff(diff)
        endpoints = [c.args[1] for c in client.request.call_args_list]
        assert endpoints.count("firewall/alias/reconfigure") == 1
        assert counts == {"created": 1, "updated": 1, "deleted": 1}

    def test_locked_only_diff_no_reconfigure(self) -> None:
        # A diff carrying only locked entries (which are never applied)
        # must not fire a reconfigure.
        client = MagicMock()
        svc = AliasService(client)
        diff = Diff(locked=[(_alias("foo", lock=True), None)])
        counts = svc.apply_diff(diff)
        client.request.assert_not_called()
        assert counts == {"created": 0, "updated": 0, "deleted": 0}


class TestComputeDiffServiceWrapper:
    def test_service_wrapper_delegates(self) -> None:
        client = MagicMock()
        svc = AliasService(client)
        diff = svc.compute_diff([], [_live("u1")], add_only=True)
        assert diff.deletes == []


# ---------------------------------------------------------------------------
# AliasService.export_to_yaml (read path; preserved from #747)
# ---------------------------------------------------------------------------


class TestExportToYaml:
    def test_aliases_appear_in_export(self) -> None:
        client = MagicMock()
        client.request.return_value = {
            "rows": [
                _row(
                    "web_servers",
                    uuid="u1",
                    type_value=_selected_type("host"),
                    description="Web tier",
                    content="10.0.0.1\n10.0.0.2",
                ),
            ]
        }
        svc = AliasService(client)
        text = svc.export_to_yaml()
        assert "name: web_servers" in text
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
        # Nested format: empty list at the leaf, not flat ``resources: []``.
        assert "aliases: []" in text
        loaded = yaml.safe_load(text)
        assert loaded == {"opnsense": {"firewall": {"aliases": []}}}

    def test_export_round_trip_loads_back_to_dict(self) -> None:
        client = MagicMock()
        client.request.return_value = {
            "rows": [
                _row(
                    "web_servers",
                    uuid="u1",
                    type_value=_selected_type("host"),
                    description="Web tier",
                    content="10.0.0.1",
                ),
                _row(
                    "geo_eu",
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
        # Nested format per ADR-0016 (#793 Phase 4).
        assert loaded["opnsense"]["firewall"]["aliases"]
        aliases = loaded["opnsense"]["firewall"]["aliases"]
        assert len(aliases) == 2

        web = aliases[0]
        assert web["name"] == "web_servers"
        assert web["config"]["name"] == "web_servers"
        assert web["config"]["type"] == "host"
        assert web["config"]["content"] == ["10.0.0.1"]
        assert "proto" not in web["config"]

        geo = aliases[1]
        assert geo["name"] == "geo_eu"
        assert geo["config"]["type"] == "geoip"
        assert geo["config"]["proto"] == "IPv4"
        assert geo["config"]["content"] == ["DE", "FR"]

    def test_system_alias_types_filtered(self) -> None:
        client = MagicMock()
        client.request.return_value = {
            "rows": [
                _row("__lan_network", type_value=_selected_type("internal")),
                _row("bogons", type_value=_selected_type("external")),
                _row("web_servers", type_value=_selected_type("host"), content="10.0.0.1"),
            ]
        }
        svc = AliasService(client)
        loaded = yaml.safe_load(svc.export_to_yaml())
        aliases = loaded["opnsense"]["firewall"]["aliases"]
        names = [r["name"] for r in aliases]
        assert names == ["web_servers"]


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
