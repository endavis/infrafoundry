"""Unit tests for ``infrafoundry.providers.opnsense.services.unbound_host_alias``.

Coverage:
    - ``UnboundHostAliasConfig.to_payload`` envelope + boolean stringification.
    - ``compute_diff`` with adds / updates / deletes / lock + add-only.
    - Identity is the ``(host_uuid, hostname)`` natural-key tuple — YAML
      ``name`` changes don't trigger updates; ``host_name`` is operator-
      facing only.
    - ``unbound_host_alias_configs_from_resources`` validation.
    - ``UnboundHostAliasService`` API method dispatch via
      ``OPNsenseClient.request``.
    - ``apply_diff`` orchestration (does NOT call ``reconfigure`` — runner
      fires the shared ``unbound_reconfigure`` finalization hook per #776).
    - ``_normalize_field`` for OPNsense select dicts and bool variants.
    - ``export_to_yaml`` round-trip with synthetic name generation and
      parent-UUID-to-label mapping.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.services.unbound_host_alias import (
    Diff,
    LiveUnboundHostAlias,
    UnboundHostAliasConfig,
    UnboundHostAliasService,
    _live_to_export_config,
    _normalize_field,
    _row_to_live,
    _synthesize_name,
    compute_diff,
    unbound_host_alias_configs_from_resources,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _alias(
    name: str,
    *,
    host_name: str = "db-primary",
    host_uuid: str = "parent-uuid",
    hostname: str = "db",
    domain: str = "internal",
    enabled: bool = True,
    description: str = "",
    lock: bool = False,
) -> UnboundHostAliasConfig:
    return UnboundHostAliasConfig(
        name=name,
        host_name=host_name,
        host_uuid=host_uuid,
        hostname=hostname,
        domain=domain,
        enabled=enabled,
        description=description,
        lock=lock,
    )


def _live(
    uuid: str,
    *,
    host_uuid: str = "parent-uuid",
    hostname: str = "db",
    domain: str = "internal",
    enabled: str = "1",
    description: str = "",
    raw_overrides: dict[str, Any] | None = None,
) -> LiveUnboundHostAlias:
    raw: dict[str, Any] = {
        "uuid": uuid,
        "host": host_uuid,
        "hostname": hostname,
        "domain": domain,
        "enabled": enabled,
        "description": description,
    }
    if raw_overrides:
        raw.update(raw_overrides)
    return LiveUnboundHostAlias(uuid=uuid, host_uuid=host_uuid, hostname=hostname, raw=raw)


def _resource(name: str, config: dict[str, Any]) -> ResourceConfig:
    return ResourceConfig(
        name=name, type="unbound.host_aliases", provider="opnsense", config=config
    )


# ---------------------------------------------------------------------------
# UnboundHostAliasConfig.to_payload
# ---------------------------------------------------------------------------


class TestPayload:
    def test_payload_has_envelope(self) -> None:
        payload = _alias("foo").to_payload()
        assert set(payload.keys()) == {"alias"}

    def test_payload_field_set(self) -> None:
        alias = _alias(
            "db-alias",
            host_uuid="abc-1234",
            hostname="db",
            domain="internal",
            description="DB alias",
        )
        inner = alias.to_payload()["alias"]
        assert inner["host"] == "abc-1234"
        assert inner["hostname"] == "db"
        assert inner["domain"] == "internal"
        assert inner["description"] == "DB alias"

    def test_enabled_true_serializes_one(self) -> None:
        inner = _alias("foo", enabled=True).to_payload()["alias"]
        assert inner["enabled"] == "1"

    def test_enabled_false_serializes_zero(self) -> None:
        inner = _alias("foo", enabled=False).to_payload()["alias"]
        assert inner["enabled"] == "0"

    def test_name_not_sent_on_wire(self) -> None:
        # ``name`` and ``host_name`` are operator-facing; the wire only
        # carries ``host`` (UUID), ``hostname``, ``domain``, ``enabled``,
        # ``description``.
        inner = _alias("operator-friendly-name").to_payload()["alias"]
        assert "name" not in inner
        assert "host_name" not in inner
        assert set(inner.keys()) == {"host", "hostname", "domain", "enabled", "description"}

    def test_default_description_empty(self) -> None:
        inner = _alias("foo").to_payload()["alias"]
        assert inner["description"] == ""


class TestDiffKey:
    def test_diff_key_is_tuple(self) -> None:
        alias = _alias("foo", host_uuid="parent-uuid", hostname="db")
        assert alias.diff_key == ("parent-uuid", "db")

    def test_live_diff_key_is_tuple(self) -> None:
        live = _live("u1", host_uuid="parent-uuid", hostname="db")
        assert live.diff_key == ("parent-uuid", "db")

    def test_yaml_name_does_not_affect_diff_key(self) -> None:
        a = _alias("name-one", host_uuid="parent-uuid", hostname="db")
        b = _alias("name-two", host_uuid="parent-uuid", hostname="db")
        assert a.diff_key == b.diff_key


class TestWithHostUuid:
    def test_returns_new_instance_with_uuid_set(self) -> None:
        cfg = _alias("foo", host_uuid="")
        resolved = cfg.with_host_uuid("abc")
        assert resolved.host_uuid == "abc"
        # original unchanged
        assert cfg.host_uuid == ""

    def test_other_fields_preserved(self) -> None:
        cfg = _alias(
            "foo",
            host_name="db-primary",
            hostname="db",
            domain="internal",
            description="d",
            enabled=False,
            lock=True,
        )
        resolved = cfg.with_host_uuid("abc")
        assert resolved.host_name == "db-primary"
        assert resolved.hostname == "db"
        assert resolved.domain == "internal"
        assert resolved.description == "d"
        assert resolved.enabled is False
        assert resolved.lock is True


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
        diff = compute_diff([_alias("foo")], [])
        assert len(diff.adds) == 1
        assert diff.adds[0].host_uuid == "parent-uuid"
        assert diff.adds[0].hostname == "db"


class TestComputeDiffUpdates:
    def test_update_when_description_changes(self) -> None:
        alias = _alias("foo", description="new description")
        live_raw: dict[str, Any] = {
            "uuid": "u1",
            "host": "parent-uuid",
            "hostname": "db",
            "domain": "internal",
            "enabled": "1",
            "description": "old description",
        }
        live = LiveUnboundHostAlias(
            uuid="u1",
            host_uuid="parent-uuid",
            hostname="db",
            raw=live_raw,
        )
        diff = compute_diff([alias], [live])
        assert len(diff.updates) == 1
        live_record, want = diff.updates[0]
        assert live_record.uuid == "u1"
        assert want.description == "new description"

    def test_update_when_enabled_flips(self) -> None:
        alias = _alias("foo", enabled=False)
        live_raw: dict[str, Any] = {
            "uuid": "u1",
            "host": "parent-uuid",
            "hostname": "db",
            "domain": "internal",
            "enabled": "1",
            "description": "",
        }
        live = LiveUnboundHostAlias(
            uuid="u1",
            host_uuid="parent-uuid",
            hostname="db",
            raw=live_raw,
        )
        diff = compute_diff([alias], [live])
        assert len(diff.updates) == 1

    def test_no_update_when_payload_matches(self) -> None:
        alias = _alias("foo")
        live_raw: dict[str, Any] = {"uuid": "u1", **alias.to_payload()["alias"]}
        live = LiveUnboundHostAlias(
            uuid="u1",
            host_uuid="parent-uuid",
            hostname="db",
            raw=live_raw,
        )
        diff = compute_diff([alias], [live])
        assert diff.is_empty

    def test_yaml_name_change_alone_is_noop(self) -> None:
        alias = _alias("renamed-alias")
        live_raw: dict[str, Any] = {"uuid": "u1", **alias.to_payload()["alias"]}
        live = LiveUnboundHostAlias(
            uuid="u1",
            host_uuid="parent-uuid",
            hostname="db",
            raw=live_raw,
        )
        diff = compute_diff([alias], [live])
        assert diff.is_empty

    def test_changing_hostname_is_delete_plus_add(self) -> None:
        # Identity tuple changed — old record has no YAML counterpart
        # (delete) and new tuple has no live counterpart (add).
        old_live = _live("u1", host_uuid="parent-uuid", hostname="db")
        new_alias = _alias("foo", host_uuid="parent-uuid", hostname="db-renamed")
        diff = compute_diff([new_alias], [old_live])
        assert len(diff.adds) == 1
        assert diff.adds[0].hostname == "db-renamed"
        assert len(diff.deletes) == 1
        assert diff.deletes[0].uuid == "u1"

    def test_changing_host_uuid_is_delete_plus_add(self) -> None:
        # Resolving to a different parent override changes identity tuple.
        old_live = _live("u1", host_uuid="parent-uuid", hostname="db")
        new_alias = _alias("foo", host_uuid="other-parent-uuid", hostname="db")
        diff = compute_diff([new_alias], [old_live])
        assert len(diff.adds) == 1
        assert len(diff.deletes) == 1


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
        alias = _alias("foo", description="changed")
        live_raw: dict[str, Any] = {
            "uuid": "u1",
            "host": "parent-uuid",
            "hostname": "db",
            "domain": "internal",
            "enabled": "1",
            "description": "old",
        }
        live = LiveUnboundHostAlias(
            uuid="u1",
            host_uuid="parent-uuid",
            hostname="db",
            raw=live_raw,
        )
        diff = compute_diff([alias], [live], add_only=True)
        assert len(diff.updates) == 1


class TestComputeDiffLocked:
    def test_locked_resource_with_match_skipped_from_actions(self) -> None:
        alias = _alias("survival", description="locked", lock=True)
        live_raw: dict[str, Any] = {
            "uuid": "u1",
            "host": "parent-uuid",
            "hostname": "db",
            "domain": "internal",
            "enabled": "1",
            "description": "drift!",
        }
        live = LiveUnboundHostAlias(
            uuid="u1",
            host_uuid="parent-uuid",
            hostname="db",
            raw=live_raw,
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

    def test_locked_resource_does_not_appear_as_delete_when_only_in_yaml(self) -> None:
        alias = _alias("locked-name", lock=True)
        live_other = _live("u2", host_uuid="other-parent", hostname="other")
        diff = compute_diff([alias], [live_other])
        assert len(diff.deletes) == 1
        assert diff.deletes[0].hostname == "other"


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
# _normalize_field
# ---------------------------------------------------------------------------


class TestNormalizeField:
    def test_none_becomes_empty(self) -> None:
        assert _normalize_field(None) == ""

    def test_bool_true_becomes_one(self) -> None:
        assert _normalize_field(True) == "1"

    def test_bool_false_becomes_zero(self) -> None:
        assert _normalize_field(False) == "0"

    def test_string_passthrough(self) -> None:
        assert _normalize_field("db") == "db"

    def test_int_stringified(self) -> None:
        assert _normalize_field(42) == "42"

    def test_select_dict_extracts_selected_key(self) -> None:
        # getHostAlias returns ``host`` as a select dict mapping parent
        # UUIDs to {"value": "...", "selected": 0|1}.
        value = {
            "parent-uuid": {"value": "db.internal", "selected": 1},
            "other-uuid": {"value": "x.example", "selected": 0},
        }
        assert _normalize_field(value) == "parent-uuid"

    def test_select_dict_no_selection_returns_empty(self) -> None:
        value = {"parent-uuid": {"value": "x", "selected": 0}}
        assert _normalize_field(value) == ""


# ---------------------------------------------------------------------------
# unbound_host_alias_configs_from_resources
# ---------------------------------------------------------------------------


class TestConfigsFromResources:
    def test_valid_parses(self) -> None:
        r = _resource(
            "db-alias",
            {
                "host": "db-primary",
                "hostname": "db",
                "domain": "internal",
                "description": "lan",
            },
        )
        result = unbound_host_alias_configs_from_resources([r])
        assert len(result) == 1
        cfg = result[0]
        assert cfg.name == "db-alias"
        assert cfg.host_name == "db-primary"
        assert cfg.hostname == "db"
        assert cfg.domain == "internal"
        assert cfg.description == "lan"

    def test_default_enabled_true(self) -> None:
        r = _resource(
            "foo",
            {"host": "p", "hostname": "h", "domain": "d"},
        )
        cfg = unbound_host_alias_configs_from_resources([r])[0]
        assert cfg.enabled is True

    def test_explicit_enabled_false(self) -> None:
        r = _resource(
            "foo",
            {"host": "p", "hostname": "h", "domain": "d", "enabled": False},
        )
        cfg = unbound_host_alias_configs_from_resources([r])[0]
        assert cfg.enabled is False

    def test_lock_passthrough(self) -> None:
        r = _resource(
            "foo",
            {"host": "p", "hostname": "h", "domain": "d", "lock": True},
        )
        cfg = unbound_host_alias_configs_from_resources([r])[0]
        assert cfg.lock is True

    def test_host_uuid_starts_empty(self) -> None:
        r = _resource(
            "foo",
            {"host": "p", "hostname": "h", "domain": "d"},
        )
        cfg = unbound_host_alias_configs_from_resources([r])[0]
        assert cfg.host_uuid == ""

    def test_missing_host_rejected(self) -> None:
        r = _resource("bad", {"hostname": "h", "domain": "d"})
        with pytest.raises(ValueError, match="host"):
            unbound_host_alias_configs_from_resources([r])

    def test_empty_host_rejected(self) -> None:
        r = _resource("bad", {"host": "", "hostname": "h", "domain": "d"})
        with pytest.raises(ValueError, match="host"):
            unbound_host_alias_configs_from_resources([r])

    def test_missing_hostname_rejected(self) -> None:
        r = _resource("bad", {"host": "p", "domain": "d"})
        with pytest.raises(ValueError, match="hostname"):
            unbound_host_alias_configs_from_resources([r])

    def test_empty_hostname_rejected(self) -> None:
        r = _resource("bad", {"host": "p", "hostname": "", "domain": "d"})
        with pytest.raises(ValueError, match="hostname"):
            unbound_host_alias_configs_from_resources([r])

    def test_missing_domain_rejected(self) -> None:
        r = _resource("bad", {"host": "p", "hostname": "h"})
        with pytest.raises(ValueError, match="domain"):
            unbound_host_alias_configs_from_resources([r])

    def test_empty_domain_rejected(self) -> None:
        r = _resource("bad", {"host": "p", "hostname": "h", "domain": ""})
        with pytest.raises(ValueError, match="domain"):
            unbound_host_alias_configs_from_resources([r])

    def test_non_string_description_rejected(self) -> None:
        r = _resource(
            "bad",
            {"host": "p", "hostname": "h", "domain": "d", "description": 12345},
        )
        with pytest.raises(ValueError, match="description"):
            unbound_host_alias_configs_from_resources([r])

    def test_non_bool_enabled_rejected(self) -> None:
        r = _resource(
            "bad",
            {"host": "p", "hostname": "h", "domain": "d", "enabled": "yes"},
        )
        with pytest.raises(ValueError, match="enabled"):
            unbound_host_alias_configs_from_resources([r])

    def test_non_bool_lock_rejected(self) -> None:
        r = _resource(
            "bad",
            {"host": "p", "hostname": "h", "domain": "d", "lock": "yes"},
        )
        with pytest.raises(ValueError, match="lock"):
            unbound_host_alias_configs_from_resources([r])

    def test_non_dict_config_rejected(self) -> None:
        r = ResourceConfig(
            name="bad",
            type="unbound.host_aliases",
            provider="opnsense",
            config={"host": "p", "hostname": "h", "domain": "d"},
        )
        # Bypass pydantic — guard the service-side defensive check.
        r.config = "not-a-dict"  # type: ignore[assignment]
        with pytest.raises(ValueError, match="non-dict"):
            unbound_host_alias_configs_from_resources([r])

    def test_non_unbound_host_alias_resources_ignored(self) -> None:
        ok = _resource("ok", {"host": "p", "hostname": "h", "domain": "d"})
        other = ResourceConfig(name="x", type="firewall.aliases", provider="opnsense", config={})
        result = unbound_host_alias_configs_from_resources([ok, other])
        assert len(result) == 1
        assert result[0].name == "ok"


# ---------------------------------------------------------------------------
# _row_to_live
# ---------------------------------------------------------------------------


class TestRowToLive:
    def test_basic_row(self) -> None:
        row = {
            "uuid": "u1",
            "host": "parent-uuid",
            "hostname": "db",
            "domain": "internal",
            "enabled": "1",
            "description": "lan",
        }
        live = _row_to_live(row)
        assert live.uuid == "u1"
        assert live.host_uuid == "parent-uuid"
        assert live.hostname == "db"
        assert live.raw == row

    def test_missing_keys_default(self) -> None:
        live = _row_to_live({})
        assert live.uuid == ""
        assert live.host_uuid == ""
        assert live.hostname == ""

    def test_host_as_select_dict_normalizes(self) -> None:
        # Defensive — search rows currently return flat strings, but
        # the helper handles the option-dict case if it ever changes.
        row = {
            "uuid": "u1",
            "host": {"parent-uuid": {"value": "x", "selected": 1}},
            "hostname": "db",
        }
        live = _row_to_live(row)
        assert live.host_uuid == "parent-uuid"


# ---------------------------------------------------------------------------
# _synthesize_name
# ---------------------------------------------------------------------------


class TestSynthesizeName:
    def test_normal(self) -> None:
        live = _live("u1", host_uuid="abcdef-1234-5678", hostname="db")
        assert _synthesize_name(live) == "alias-db-abcdef"

    def test_unknown_parent(self) -> None:
        live = LiveUnboundHostAlias(uuid="u1", host_uuid="", hostname="db", raw={})
        assert _synthesize_name(live) == "alias-db-unknown"

    def test_lowercase(self) -> None:
        live = _live("u1", host_uuid="ABCDEF-1234-5678", hostname="DB")
        assert _synthesize_name(live) == "alias-db-abcdef"


# ---------------------------------------------------------------------------
# UnboundHostAliasService API methods
# ---------------------------------------------------------------------------


class TestServiceSearch:
    def test_search_calls_correct_endpoint(self) -> None:
        client = MagicMock()
        client.request.return_value = {"rows": []}
        svc = UnboundHostAliasService(client)
        result = svc.search()
        client.request.assert_called_once_with("POST", "unbound/settings/searchHostAlias")
        assert result == []

    def test_search_normalizes_rows(self) -> None:
        client = MagicMock()
        client.request.return_value = {
            "rows": [
                {"uuid": "u1", "host": "parent", "hostname": "a"},
                "not-a-dict",  # filtered out
                {"uuid": "u2", "host": "parent", "hostname": "b"},
            ]
        }
        svc = UnboundHostAliasService(client)
        result = svc.search()
        assert len(result) == 2
        assert result[0].uuid == "u1"
        assert result[1].uuid == "u2"

    def test_search_handles_non_dict_response(self) -> None:
        client = MagicMock()
        client.request.return_value = "not-a-dict"
        svc = UnboundHostAliasService(client)
        assert svc.search() == []

    def test_search_handles_missing_rows_key(self) -> None:
        client = MagicMock()
        client.request.return_value = {}
        svc = UnboundHostAliasService(client)
        assert svc.search() == []


class TestServiceGet:
    def test_get_uses_get_verb(self) -> None:
        client = MagicMock()
        client.request.return_value = {"alias": {"hostname": "db"}}
        svc = UnboundHostAliasService(client)
        result = svc.get("u1")
        client.request.assert_called_once_with("GET", "unbound/settings/getHostAlias/u1")
        assert result == {"alias": {"hostname": "db"}}


class TestServiceSearchHostOverrides:
    def test_calls_correct_endpoint(self) -> None:
        client = MagicMock()
        client.request.return_value = {
            "rows": [{"uuid": "p1", "hostname": "db", "domain": "internal"}]
        }
        svc = UnboundHostAliasService(client)
        rows = svc.search_host_overrides()
        client.request.assert_called_once_with("POST", "unbound/settings/searchHostOverride")
        assert rows == [{"uuid": "p1", "hostname": "db", "domain": "internal"}]

    def test_handles_non_dict_response(self) -> None:
        client = MagicMock()
        client.request.return_value = "not-a-dict"
        svc = UnboundHostAliasService(client)
        assert svc.search_host_overrides() == []

    def test_handles_missing_rows(self) -> None:
        client = MagicMock()
        client.request.return_value = {}
        svc = UnboundHostAliasService(client)
        assert svc.search_host_overrides() == []

    def test_filters_non_dict_rows(self) -> None:
        client = MagicMock()
        client.request.return_value = {"rows": [{"uuid": "p1"}, "junk", 7]}
        svc = UnboundHostAliasService(client)
        rows = svc.search_host_overrides()
        assert rows == [{"uuid": "p1"}]


class TestServiceWriteOps:
    def test_add_posts_correct_endpoint(self) -> None:
        client = MagicMock()
        client.request.return_value = {"result": "saved", "uuid": "new"}
        svc = UnboundHostAliasService(client)
        alias = _alias("foo")
        svc.add(alias)
        client.request.assert_called_once_with(
            "POST", "unbound/settings/addHostAlias", data=alias.to_payload()
        )

    def test_update_posts_correct_endpoint(self) -> None:
        client = MagicMock()
        client.request.return_value = {"result": "saved"}
        svc = UnboundHostAliasService(client)
        alias = _alias("foo")
        svc.update("uuid-abc", alias)
        client.request.assert_called_once_with(
            "POST", "unbound/settings/setHostAlias/uuid-abc", data=alias.to_payload()
        )

    def test_delete_posts_correct_endpoint(self) -> None:
        client = MagicMock()
        svc = UnboundHostAliasService(client)
        svc.delete("u1")
        client.request.assert_called_once_with("POST", "unbound/settings/delHostAlias/u1")

    def test_reconfigure_posts_correct_endpoint(self) -> None:
        client = MagicMock()
        svc = UnboundHostAliasService(client)
        svc.reconfigure()
        client.request.assert_called_once_with("POST", "unbound/service/reconfigure")


class TestApplyDiff:
    def test_empty_diff_is_noop(self) -> None:
        client = MagicMock()
        svc = UnboundHostAliasService(client)
        counts = svc.apply_diff(Diff())
        client.request.assert_not_called()
        assert counts == {"created": 0, "updated": 0, "deleted": 0}

    def test_add_does_not_call_reconfigure(self) -> None:
        # Per #776 the service no longer calls reconfigure inline; the
        # runner fires the shared ``unbound_reconfigure`` finalization
        # hook exactly once per apply across all three unbound managers.
        client = MagicMock()
        client.request.return_value = {"result": "saved"}
        svc = UnboundHostAliasService(client)
        diff = Diff(adds=[_alias("foo"), _alias("bar", hostname="db2")])
        counts = svc.apply_diff(diff)
        endpoints = [c.args[1] for c in client.request.call_args_list]
        assert endpoints.count("unbound/settings/addHostAlias") == 2
        assert "unbound/service/reconfigure" not in endpoints
        assert counts == {"created": 2, "updated": 0, "deleted": 0}

    def test_update_does_not_call_reconfigure(self) -> None:
        client = MagicMock()
        client.request.return_value = {"result": "saved"}
        svc = UnboundHostAliasService(client)
        live = _live("u1")
        alias = _alias("foo")
        diff = Diff(updates=[(live, alias)])
        counts = svc.apply_diff(diff)
        endpoints = [c.args[1] for c in client.request.call_args_list]
        assert "unbound/settings/setHostAlias/u1" in endpoints
        assert "unbound/service/reconfigure" not in endpoints
        assert counts == {"created": 0, "updated": 1, "deleted": 0}

    def test_delete_does_not_call_reconfigure(self) -> None:
        client = MagicMock()
        svc = UnboundHostAliasService(client)
        diff = Diff(
            deletes=[
                _live("u1"),
                _live("u2", hostname="db2"),
            ]
        )
        counts = svc.apply_diff(diff)
        endpoints = [c.args[1] for c in client.request.call_args_list]
        assert "unbound/settings/delHostAlias/u1" in endpoints
        assert "unbound/settings/delHostAlias/u2" in endpoints
        assert "unbound/service/reconfigure" not in endpoints
        assert counts == {"created": 0, "updated": 0, "deleted": 2}

    def test_mixed_diff_does_not_call_reconfigure(self) -> None:
        client = MagicMock()
        client.request.return_value = {"result": "saved"}
        svc = UnboundHostAliasService(client)
        live_for_update = _live("u1")
        live_for_delete = _live("u2", hostname="db2")
        new = _alias("new", hostname="db3")
        update_target = _alias("foo", description="changed")
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
        svc = UnboundHostAliasService(client)
        diff = svc.compute_diff([], [_live("u1")], add_only=True)
        assert diff.deletes == []


# ---------------------------------------------------------------------------
# export_to_yaml + _live_to_export_config
# ---------------------------------------------------------------------------


class TestExportToYaml:
    def test_aliases_appear_in_export(self) -> None:
        client = MagicMock()
        # search returns one alias, search_host_overrides returns the
        # parent override, get returns the option-dict envelope.
        client.request.side_effect = [
            # searchHostAlias
            {
                "rows": [
                    {
                        "uuid": "u1",
                        "host": "parent-uuid",
                        "hostname": "db",
                        "domain": "internal",
                        "enabled": "1",
                        "description": "lan",
                    },
                ]
            },
            # searchHostOverride
            {
                "rows": [
                    {
                        "uuid": "parent-uuid",
                        "hostname": "db-primary",
                        "domain": "internal",
                    }
                ]
            },
            # getHostAlias/u1
            {
                "alias": {
                    "host": {
                        "parent-uuid": {"value": "db-primary.internal", "selected": 1},
                    },
                    "hostname": "db",
                    "domain": "internal",
                    "enabled": "1",
                    "description": "lan",
                }
            },
        ]
        svc = UnboundHostAliasService(client)
        text = svc.export_to_yaml()
        # Synthetic name appears.
        assert "alias-db-parent" in text
        # Field decoding worked, and parent is mapped to its label.
        assert "host: db-primary.internal" in text
        assert "hostname: db" in text
        assert "domain: internal" in text
        assert "description: lan" in text
        assert "enabled: true" in text

    def test_export_with_no_aliases_yields_empty_resources(self) -> None:
        client = MagicMock()
        # searchHostAlias then searchHostOverride
        client.request.side_effect = [{"rows": []}, {"rows": []}]
        svc = UnboundHostAliasService(client)
        text = svc.export_to_yaml()
        # Nested format: empty leaf list at opnsense.unbound.host_aliases.
        assert "host_aliases: []" in text


class TestLiveToExportConfig:
    def test_decoding_select_dict_and_bools(self) -> None:
        get_response = {
            "alias": {
                "host": {
                    "parent-uuid": {"value": "db-primary.internal", "selected": 1},
                    "other-uuid": {"value": "x.example", "selected": 0},
                },
                "hostname": "db",
                "domain": "internal",
                "enabled": "0",
                "description": "v6",
            }
        }
        cfg = _live_to_export_config(get_response, {"parent-uuid": "db-primary.internal"})
        assert cfg["enabled"] is False
        assert cfg["host"] == "db-primary.internal"
        assert cfg["hostname"] == "db"
        assert cfg["domain"] == "internal"
        assert cfg["description"] == "v6"

    def test_unknown_parent_falls_back_to_uuid(self) -> None:
        get_response = {
            "alias": {
                "host": {
                    "missing-uuid": {"value": "x", "selected": 1},
                },
                "hostname": "db",
                "domain": "internal",
                "enabled": "1",
                "description": "",
            }
        }
        cfg = _live_to_export_config(get_response, {})
        # Falls back to the raw UUID when there is no label mapping.
        assert cfg["host"] == "missing-uuid"

    def test_missing_envelope_yields_defaults(self) -> None:
        cfg = _live_to_export_config({}, {})
        # Defensive defaults so an empty response doesn't crash.
        assert cfg["enabled"] is False  # missing → "" → != "1" → False
        assert cfg["host"] == ""
        assert cfg["hostname"] == ""
        assert cfg["domain"] == ""

    def test_non_dict_envelope_yields_defaults(self) -> None:
        cfg = _live_to_export_config(None, {})  # type: ignore[arg-type]
        assert cfg["host"] == ""
        assert cfg["hostname"] == ""
