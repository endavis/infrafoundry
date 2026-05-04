"""Unit tests for ``infrafoundry.providers.opnsense.services.static_route``.

Coverage:
    - ``StaticRouteConfig.to_payload`` envelope + boolean inversion
      (``enabled`` → ``disabled``) + ``description`` → ``descr`` mapping.
    - ``compute_diff`` with adds / updates / deletes / lock + add-only.
    - Identity is the ``(network, gateway)`` natural-key tuple — YAML
      ``name`` changes don't trigger updates.
    - ``static_route_configs_from_resources`` validation.
    - ``StaticRouteService`` API method dispatch via ``OPNsenseClient.request``.
    - ``apply_diff`` orchestration (single ``reconfigure`` if any mutation).
    - ``_normalize_field`` for OPNsense select dicts and bool variants.
    - ``export_to_yaml`` round-trip with synthetic name generation.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.services.static_route import (
    Diff,
    LiveStaticRoute,
    StaticRouteConfig,
    StaticRouteService,
    _live_to_export_config,
    _normalize_field,
    _row_to_live,
    _synthesize_name,
    compute_diff,
    static_route_configs_from_resources,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _route(
    name: str,
    *,
    network: str = "10.0.0.0/24",
    gateway: str = "WAN_DHCP",
    enabled: bool = True,
    description: str = "",
    lock: bool = False,
) -> StaticRouteConfig:
    return StaticRouteConfig(
        name=name,
        network=network,
        gateway=gateway,
        enabled=enabled,
        description=description,
        lock=lock,
    )


def _live(
    uuid: str,
    *,
    network: str = "10.0.0.0/24",
    gateway: str = "WAN_DHCP",
    raw_overrides: dict[str, Any] | None = None,
) -> LiveStaticRoute:
    raw: dict[str, Any] = {
        "uuid": uuid,
        "network": network,
        "gateway": gateway,
        "disabled": "0",
        "descr": "",
    }
    if raw_overrides:
        raw.update(raw_overrides)
    return LiveStaticRoute(uuid=uuid, network=network, gateway=gateway, raw=raw)


def _resource(name: str, config: dict[str, Any]) -> ResourceConfig:
    return ResourceConfig(name=name, type="static_routes", provider="opnsense", config=config)


# ---------------------------------------------------------------------------
# StaticRouteConfig.to_payload
# ---------------------------------------------------------------------------


class TestPayload:
    def test_payload_has_envelope(self) -> None:
        payload = _route("foo").to_payload()
        assert set(payload.keys()) == {"route"}

    def test_payload_field_set(self) -> None:
        route = _route(
            "lan-via-wan",
            network="10.0.0.0/24",
            gateway="WAN_DHCP",
            description="reach the LAN",
        )
        inner = route.to_payload()["route"]
        assert inner["network"] == "10.0.0.0/24"
        assert inner["gateway"] == "WAN_DHCP"
        assert inner["descr"] == "reach the LAN"

    def test_enabled_true_serializes_disabled_zero(self) -> None:
        # operator-facing ``enabled=True`` → wire ``disabled=0``.
        inner = _route("foo", enabled=True).to_payload()["route"]
        assert inner["disabled"] == "0"

    def test_enabled_false_serializes_disabled_one(self) -> None:
        inner = _route("foo", enabled=False).to_payload()["route"]
        assert inner["disabled"] == "1"

    def test_name_not_sent_on_wire(self) -> None:
        # ``name`` is operator-facing only; the wire only carries
        # ``network``, ``gateway``, ``descr``, ``disabled``.
        inner = _route("operator-friendly-name").to_payload()["route"]
        assert "name" not in inner
        assert set(inner.keys()) == {"network", "gateway", "descr", "disabled"}

    def test_default_description_empty(self) -> None:
        inner = _route("foo").to_payload()["route"]
        assert inner["descr"] == ""


class TestDiffKey:
    def test_diff_key_is_tuple(self) -> None:
        route = _route("foo", network="10.0.0.0/24", gateway="WAN_DHCP")
        assert route.diff_key == ("10.0.0.0/24", "WAN_DHCP")

    def test_live_diff_key_is_tuple(self) -> None:
        live = _live("u1", network="10.0.0.0/24", gateway="WAN_DHCP")
        assert live.diff_key == ("10.0.0.0/24", "WAN_DHCP")

    def test_yaml_name_does_not_affect_diff_key(self) -> None:
        a = _route("name-one", network="10.0.0.0/24", gateway="WAN_DHCP")
        b = _route("name-two", network="10.0.0.0/24", gateway="WAN_DHCP")
        assert a.diff_key == b.diff_key


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
    def test_new_route_adds(self) -> None:
        diff = compute_diff([_route("foo")], [])
        assert len(diff.adds) == 1
        assert diff.adds[0].network == "10.0.0.0/24"
        assert diff.adds[0].gateway == "WAN_DHCP"


class TestComputeDiffUpdates:
    def test_update_when_description_changes(self) -> None:
        # Only ``descr`` differs; the identity tuple matches.
        route = _route("foo", description="new description")
        live_raw: dict[str, Any] = {
            "uuid": "u1",
            "network": "10.0.0.0/24",
            "gateway": "WAN_DHCP",
            "disabled": "0",
            "descr": "old description",
        }
        live = LiveStaticRoute(
            uuid="u1",
            network="10.0.0.0/24",
            gateway="WAN_DHCP",
            raw=live_raw,
        )
        diff = compute_diff([route], [live])
        assert len(diff.updates) == 1
        live_record, want = diff.updates[0]
        assert live_record.uuid == "u1"
        assert want.description == "new description"

    def test_update_when_disabled_flips(self) -> None:
        route = _route("foo", enabled=False)
        live_raw: dict[str, Any] = {
            "uuid": "u1",
            "network": "10.0.0.0/24",
            "gateway": "WAN_DHCP",
            "disabled": "0",
            "descr": "",
        }
        live = LiveStaticRoute(
            uuid="u1",
            network="10.0.0.0/24",
            gateway="WAN_DHCP",
            raw=live_raw,
        )
        diff = compute_diff([route], [live])
        assert len(diff.updates) == 1

    def test_no_update_when_payload_matches(self) -> None:
        route = _route("foo")
        live_raw: dict[str, Any] = {"uuid": "u1", **route.to_payload()["route"]}
        live = LiveStaticRoute(
            uuid="u1",
            network="10.0.0.0/24",
            gateway="WAN_DHCP",
            raw=live_raw,
        )
        diff = compute_diff([route], [live])
        assert diff.is_empty

    def test_yaml_name_change_alone_is_noop(self) -> None:
        # ``name`` change with same identity tuple is a no-op (name is
        # operator metadata, not on the wire).
        route = _route("renamed-route")
        live_raw: dict[str, Any] = {"uuid": "u1", **route.to_payload()["route"]}
        live = LiveStaticRoute(
            uuid="u1",
            network="10.0.0.0/24",
            gateway="WAN_DHCP",
            raw=live_raw,
        )
        diff = compute_diff([route], [live])
        assert diff.is_empty

    def test_changing_gateway_is_delete_plus_add(self) -> None:
        # Identity tuple changed — old record has no YAML counterpart
        # (delete) and new tuple has no live counterpart (add).
        old_live = _live("u1", network="10.0.0.0/24", gateway="WAN_DHCP")
        new_route = _route("foo", network="10.0.0.0/24", gateway="ALT_GW")
        diff = compute_diff([new_route], [old_live])
        assert len(diff.adds) == 1
        assert diff.adds[0].gateway == "ALT_GW"
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
        route = _route("foo", description="changed")
        live_raw: dict[str, Any] = {
            "uuid": "u1",
            "network": "10.0.0.0/24",
            "gateway": "WAN_DHCP",
            "disabled": "0",
            "descr": "old",
        }
        live = LiveStaticRoute(
            uuid="u1",
            network="10.0.0.0/24",
            gateway="WAN_DHCP",
            raw=live_raw,
        )
        diff = compute_diff([route], [live], add_only=True)
        assert len(diff.updates) == 1


class TestComputeDiffLocked:
    def test_locked_resource_with_match_skipped_from_actions(self) -> None:
        route = _route("survival", description="locked", lock=True)
        live_raw: dict[str, Any] = {
            "uuid": "u1",
            "network": "10.0.0.0/24",
            "gateway": "WAN_DHCP",
            "disabled": "0",
            "descr": "drift!",
        }
        live = LiveStaticRoute(
            uuid="u1",
            network="10.0.0.0/24",
            gateway="WAN_DHCP",
            raw=live_raw,
        )
        diff = compute_diff([route], [live])
        assert diff.adds == []
        assert diff.updates == []
        assert diff.deletes == []
        assert len(diff.locked) == 1
        want, have = diff.locked[0]
        assert want.lock is True
        assert have is not None
        assert have.uuid == "u1"

    def test_locked_resource_without_match(self) -> None:
        route = _route("missing", lock=True)
        diff = compute_diff([route], [])
        assert len(diff.locked) == 1
        _want, have = diff.locked[0]
        assert have is None

    def test_locked_resource_does_not_appear_as_delete_when_only_in_yaml(self) -> None:
        # Confirms locked tuples are excluded from the delete pass even
        # when they have no live counterpart and there's another live
        # to delete.
        route = _route("locked-name", lock=True)
        live_other = _live("u2", network="172.16.0.0/24", gateway="WAN_DHCP")
        diff = compute_diff([route], [live_other])
        # The other live (172.16/24) should still be deleted.
        assert len(diff.deletes) == 1
        assert diff.deletes[0].network == "172.16.0.0/24"


class TestDiffIsEmpty:
    def test_empty_diff(self) -> None:
        assert Diff().is_empty

    def test_locked_alone_counts_as_empty(self) -> None:
        diff = Diff(locked=[(_route("foo", lock=True), None)])
        assert diff.is_empty

    def test_non_empty_when_adds(self) -> None:
        diff = Diff(adds=[_route("foo")])
        assert not diff.is_empty

    def test_non_empty_when_updates(self) -> None:
        diff = Diff(updates=[(_live("u1"), _route("foo"))])
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
        assert _normalize_field("WAN_DHCP") == "WAN_DHCP"

    def test_int_stringified(self) -> None:
        assert _normalize_field(42) == "42"

    def test_select_dict_extracts_selected_key(self) -> None:
        # getroute returns gateway as a select dict.
        value = {
            "WAN_DHCP": {"value": "WAN_DHCP - 10.0.0.1", "selected": 1},
            "WAN_DHCP6": {"value": "WAN_DHCP6 - fe80::1", "selected": 0},
        }
        assert _normalize_field(value) == "WAN_DHCP"

    def test_select_dict_no_selection_returns_empty(self) -> None:
        value = {"WAN_DHCP": {"value": "WAN_DHCP - 10.0.0.1", "selected": 0}}
        assert _normalize_field(value) == ""


# ---------------------------------------------------------------------------
# static_route_configs_from_resources
# ---------------------------------------------------------------------------


class TestConfigsFromResources:
    def test_valid_parses(self) -> None:
        r = _resource(
            "lan-via-wan",
            {
                "network": "10.0.0.0/24",
                "gateway": "WAN_DHCP",
                "description": "lan",
            },
        )
        result = static_route_configs_from_resources([r])
        assert len(result) == 1
        cfg = result[0]
        assert cfg.name == "lan-via-wan"
        assert cfg.network == "10.0.0.0/24"
        assert cfg.gateway == "WAN_DHCP"
        assert cfg.description == "lan"

    def test_default_enabled_true(self) -> None:
        r = _resource(
            "foo",
            {"network": "10.0.0.0/24", "gateway": "WAN_DHCP"},
        )
        cfg = static_route_configs_from_resources([r])[0]
        assert cfg.enabled is True

    def test_explicit_enabled_false(self) -> None:
        r = _resource(
            "foo",
            {"network": "10.0.0.0/24", "gateway": "WAN_DHCP", "enabled": False},
        )
        cfg = static_route_configs_from_resources([r])[0]
        assert cfg.enabled is False

    def test_lock_passthrough(self) -> None:
        r = _resource(
            "foo",
            {"network": "10.0.0.0/24", "gateway": "WAN_DHCP", "lock": True},
        )
        cfg = static_route_configs_from_resources([r])[0]
        assert cfg.lock is True

    def test_missing_network_rejected(self) -> None:
        r = _resource("bad", {"gateway": "WAN_DHCP"})
        with pytest.raises(ValueError, match="network"):
            static_route_configs_from_resources([r])

    def test_empty_network_rejected(self) -> None:
        r = _resource("bad", {"network": "", "gateway": "WAN_DHCP"})
        with pytest.raises(ValueError, match="network"):
            static_route_configs_from_resources([r])

    def test_missing_gateway_rejected(self) -> None:
        r = _resource("bad", {"network": "10.0.0.0/24"})
        with pytest.raises(ValueError, match="gateway"):
            static_route_configs_from_resources([r])

    def test_empty_gateway_rejected(self) -> None:
        r = _resource("bad", {"network": "10.0.0.0/24", "gateway": ""})
        with pytest.raises(ValueError, match="gateway"):
            static_route_configs_from_resources([r])

    def test_non_string_description_rejected(self) -> None:
        r = _resource(
            "bad",
            {"network": "10.0.0.0/24", "gateway": "WAN_DHCP", "description": 12345},
        )
        with pytest.raises(ValueError, match="description"):
            static_route_configs_from_resources([r])

    def test_non_bool_enabled_rejected(self) -> None:
        r = _resource(
            "bad",
            {"network": "10.0.0.0/24", "gateway": "WAN_DHCP", "enabled": "yes"},
        )
        with pytest.raises(ValueError, match="enabled"):
            static_route_configs_from_resources([r])

    def test_non_bool_lock_rejected(self) -> None:
        r = _resource(
            "bad",
            {"network": "10.0.0.0/24", "gateway": "WAN_DHCP", "lock": "yes"},
        )
        with pytest.raises(ValueError, match="lock"):
            static_route_configs_from_resources([r])

    def test_non_dict_config_rejected(self) -> None:
        r = ResourceConfig(
            name="bad",
            type="static_routes",
            provider="opnsense",
            config={"network": "10.0.0.0/24", "gateway": "WAN_DHCP"},
        )
        # Bypass pydantic — guard the service-side defensive check.
        r.config = "not-a-dict"  # type: ignore[assignment]
        with pytest.raises(ValueError, match="non-dict"):
            static_route_configs_from_resources([r])

    def test_non_static_routes_resources_ignored(self) -> None:
        sr = _resource("ok", {"network": "10.0.0.0/24", "gateway": "WAN_DHCP"})
        other = ResourceConfig(name="x", type="aliases", provider="opnsense", config={})
        result = static_route_configs_from_resources([sr, other])
        assert len(result) == 1
        assert result[0].name == "ok"


# ---------------------------------------------------------------------------
# _row_to_live
# ---------------------------------------------------------------------------


class TestRowToLive:
    def test_basic_row(self) -> None:
        row = {
            "uuid": "u1",
            "network": "10.0.0.0/24",
            "gateway": "WAN_DHCP",
            "descr": "lan",
            "disabled": "0",
        }
        live = _row_to_live(row)
        assert live.uuid == "u1"
        assert live.network == "10.0.0.0/24"
        assert live.gateway == "WAN_DHCP"
        assert live.raw == row

    def test_missing_keys_default(self) -> None:
        live = _row_to_live({})
        assert live.uuid == ""
        assert live.network == ""
        assert live.gateway == ""

    def test_gateway_as_select_dict_normalizes(self) -> None:
        # Defensive — search rows currently return flat strings, but
        # the helper handles the option-dict case if it ever changes.
        row = {
            "uuid": "u1",
            "network": "10.0.0.0/24",
            "gateway": {"WAN_DHCP": {"value": "x", "selected": 1}},
        }
        live = _row_to_live(row)
        assert live.gateway == "WAN_DHCP"


# ---------------------------------------------------------------------------
# _synthesize_name
# ---------------------------------------------------------------------------


class TestSynthesizeName:
    def test_v4_cidr(self) -> None:
        live = _live("u1", network="10.0.0.0/24", gateway="WAN_DHCP")
        assert _synthesize_name(live) == "route-10-0-0-0-24-via-wan_dhcp"

    def test_v6_cidr(self) -> None:
        live = _live("u1", network="2001:db8::/32", gateway="WAN_DHCP6")
        # ``:`` is replaced with ``-`` and lowercased.
        assert _synthesize_name(live) == "route-2001-db8---32-via-wan_dhcp6"

    def test_lowercase(self) -> None:
        live = _live("u1", network="10.0.0.0/24", gateway="MyGW")
        assert _synthesize_name(live) == "route-10-0-0-0-24-via-mygw"


# ---------------------------------------------------------------------------
# StaticRouteService API methods
# ---------------------------------------------------------------------------


class TestServiceSearch:
    def test_search_calls_correct_endpoint(self) -> None:
        client = MagicMock()
        client.request.return_value = {"rows": []}
        svc = StaticRouteService(client)
        result = svc.search()
        client.request.assert_called_once_with("POST", "routes/routes/searchroute")
        assert result == []

    def test_search_normalizes_rows(self) -> None:
        client = MagicMock()
        client.request.return_value = {
            "rows": [
                {"uuid": "u1", "network": "10.0.0.0/24", "gateway": "WAN_DHCP"},
                "not-a-dict",  # filtered out
                {"uuid": "u2", "network": "172.16.0.0/24", "gateway": "WAN_DHCP"},
            ]
        }
        svc = StaticRouteService(client)
        result = svc.search()
        assert len(result) == 2
        assert result[0].uuid == "u1"
        assert result[1].uuid == "u2"

    def test_search_handles_non_dict_response(self) -> None:
        client = MagicMock()
        client.request.return_value = "not-a-dict"
        svc = StaticRouteService(client)
        assert svc.search() == []

    def test_search_handles_missing_rows_key(self) -> None:
        client = MagicMock()
        client.request.return_value = {}
        svc = StaticRouteService(client)
        assert svc.search() == []


class TestServiceGet:
    def test_get_uses_get_verb(self) -> None:
        client = MagicMock()
        client.request.return_value = {"route": {"network": "10.0.0.0/24"}}
        svc = StaticRouteService(client)
        result = svc.get("u1")
        client.request.assert_called_once_with("GET", "routes/routes/getroute/u1")
        assert result == {"route": {"network": "10.0.0.0/24"}}


class TestServiceWriteOps:
    def test_add_posts_correct_endpoint(self) -> None:
        client = MagicMock()
        client.request.return_value = {"result": "saved", "uuid": "new"}
        svc = StaticRouteService(client)
        route = _route("foo")
        svc.add(route)
        client.request.assert_called_once_with(
            "POST", "routes/routes/addroute", data=route.to_payload()
        )

    def test_update_posts_correct_endpoint(self) -> None:
        client = MagicMock()
        client.request.return_value = {"result": "saved"}
        svc = StaticRouteService(client)
        route = _route("foo")
        svc.update("uuid-abc", route)
        client.request.assert_called_once_with(
            "POST", "routes/routes/setroute/uuid-abc", data=route.to_payload()
        )

    def test_delete_posts_correct_endpoint(self) -> None:
        client = MagicMock()
        svc = StaticRouteService(client)
        svc.delete("u1")
        client.request.assert_called_once_with("POST", "routes/routes/delroute/u1")

    def test_reconfigure_posts_correct_endpoint(self) -> None:
        client = MagicMock()
        svc = StaticRouteService(client)
        svc.reconfigure()
        client.request.assert_called_once_with("POST", "routes/routes/reconfigure")


class TestApplyDiff:
    def test_empty_diff_is_noop(self) -> None:
        client = MagicMock()
        svc = StaticRouteService(client)
        counts = svc.apply_diff(Diff())
        client.request.assert_not_called()
        assert counts == {"created": 0, "updated": 0, "deleted": 0}

    def test_add_calls_reconfigure_once(self) -> None:
        client = MagicMock()
        client.request.return_value = {"result": "saved"}
        svc = StaticRouteService(client)
        diff = Diff(adds=[_route("foo"), _route("bar", network="172.16.0.0/24")])
        counts = svc.apply_diff(diff)
        endpoints = [c.args[1] for c in client.request.call_args_list]
        assert endpoints.count("routes/routes/addroute") == 2
        assert endpoints.count("routes/routes/reconfigure") == 1
        assert counts == {"created": 2, "updated": 0, "deleted": 0}

    def test_update_calls_reconfigure_once(self) -> None:
        client = MagicMock()
        client.request.return_value = {"result": "saved"}
        svc = StaticRouteService(client)
        live = _live("u1")
        route = _route("foo")
        diff = Diff(updates=[(live, route)])
        counts = svc.apply_diff(diff)
        endpoints = [c.args[1] for c in client.request.call_args_list]
        assert "routes/routes/setroute/u1" in endpoints
        assert endpoints.count("routes/routes/reconfigure") == 1
        assert counts == {"created": 0, "updated": 1, "deleted": 0}

    def test_delete_calls_reconfigure_once(self) -> None:
        client = MagicMock()
        svc = StaticRouteService(client)
        diff = Diff(
            deletes=[
                _live("u1"),
                _live("u2", network="172.16.0.0/24"),
            ]
        )
        counts = svc.apply_diff(diff)
        endpoints = [c.args[1] for c in client.request.call_args_list]
        assert "routes/routes/delroute/u1" in endpoints
        assert "routes/routes/delroute/u2" in endpoints
        assert endpoints.count("routes/routes/reconfigure") == 1
        assert counts == {"created": 0, "updated": 0, "deleted": 2}

    def test_mixed_diff_single_reconfigure(self) -> None:
        client = MagicMock()
        client.request.return_value = {"result": "saved"}
        svc = StaticRouteService(client)
        live_for_update = _live("u1")
        live_for_delete = _live("u2", network="172.16.0.0/24")
        new = _route("new", network="192.168.0.0/24")
        update_target = _route("foo", description="changed")
        diff = Diff(
            adds=[new],
            updates=[(live_for_update, update_target)],
            deletes=[live_for_delete],
        )
        counts = svc.apply_diff(diff)
        endpoints = [c.args[1] for c in client.request.call_args_list]
        assert endpoints.count("routes/routes/reconfigure") == 1
        assert counts == {"created": 1, "updated": 1, "deleted": 1}


class TestComputeDiffServiceWrapper:
    def test_service_wrapper_delegates(self) -> None:
        client = MagicMock()
        svc = StaticRouteService(client)
        # Module-level compute_diff is the source of truth; just make
        # sure the wrapper threads add_only.
        diff = svc.compute_diff([], [_live("u1")], add_only=True)
        assert diff.deletes == []


# ---------------------------------------------------------------------------
# export_to_yaml + _live_to_export_config
# ---------------------------------------------------------------------------


class TestExportToYaml:
    def test_routes_appear_in_export(self) -> None:
        client = MagicMock()
        # First call: searchroute. Subsequent calls: per-uuid getroute.
        client.request.side_effect = [
            {
                "rows": [
                    {
                        "uuid": "u1",
                        "network": "10.0.0.0/24",
                        "gateway": "WAN_DHCP",
                        "descr": "lan",
                        "disabled": "0",
                    },
                ]
            },
            # getroute/u1
            {
                "route": {
                    "network": "10.0.0.0/24",
                    "gateway": {
                        "WAN_DHCP": {"value": "WAN_DHCP - 10.0.0.1", "selected": 1},
                        "WAN_DHCP6": {"value": "WAN_DHCP6 - fe80::1", "selected": 0},
                    },
                    "descr": "lan",
                    "disabled": "0",
                }
            },
        ]
        svc = StaticRouteService(client)
        text = svc.export_to_yaml()
        # Synthetic name appears.
        assert "route-10-0-0-0-24-via-wan_dhcp" in text
        # Field decoding worked.
        assert "network: 10.0.0.0/24" in text
        assert "gateway: WAN_DHCP" in text
        assert "description: lan" in text
        assert "enabled: true" in text

    def test_export_with_no_routes_yields_empty_resources(self) -> None:
        client = MagicMock()
        client.request.return_value = {"rows": []}
        svc = StaticRouteService(client)
        text = svc.export_to_yaml()
        assert "resources: []" in text


class TestLiveToExportConfig:
    def test_decoding_select_dict_and_bools(self) -> None:
        get_response = {
            "route": {
                "network": "2001:db8::/32",
                "gateway": {
                    "WAN_DHCP": {"value": "WAN_DHCP - 10.0.0.1", "selected": 0},
                    "WAN_DHCP6": {"value": "WAN_DHCP6 - fe80::1", "selected": 1},
                },
                "descr": "v6 route",
                "disabled": "1",
            }
        }
        cfg = _live_to_export_config(get_response)
        assert cfg["enabled"] is False  # disabled "1" → enabled False
        assert cfg["network"] == "2001:db8::/32"
        assert cfg["gateway"] == "WAN_DHCP6"
        assert cfg["description"] == "v6 route"

    def test_missing_envelope_yields_defaults(self) -> None:
        cfg = _live_to_export_config({})
        # Defensive defaults so an empty response doesn't crash.
        assert cfg["enabled"] is True
        assert cfg["network"] == ""
        assert cfg["gateway"] == ""
        assert cfg["description"] == ""

    def test_non_dict_envelope_yields_defaults(self) -> None:
        cfg = _live_to_export_config(None)  # type: ignore[arg-type]
        assert cfg["enabled"] is True
        assert cfg["network"] == ""
