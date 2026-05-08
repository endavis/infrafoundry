"""Unit tests for ``infrafoundry.providers.opnsense.services.gateway``.

Coverage:
    - ``GatewayConfig.to_payload`` envelope + boolean inversion
      (``enabled`` → ``disabled``) + ``description`` → ``descr`` mapping.
    - ``compute_diff`` with adds / updates / deletes / lock + add-only.
    - Dynamic / virtual live gateways silently filtered.
    - ``gateway_configs_from_resources`` validation.
    - ``GatewayService`` API method dispatch via ``OPNsenseClient.request``.
    - ``apply_diff`` orchestration (single ``reconfigure`` if any mutation).
    - ``_normalize_field`` for OPNsense select dicts and bool variants.
    - ``export_to_yaml`` round-trip (managed gateways only).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.services.gateway import (
    DEFAULT_PRIORITY,
    DEFAULT_WEIGHT,
    Diff,
    GatewayConfig,
    GatewayService,
    LiveGateway,
    _live_to_export_config,
    _normalize_field,
    _row_to_live,
    compute_diff,
    gateway_configs_from_resources,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _gw(
    name: str,
    *,
    interface: str = "wan",
    protocol: str = "inet",
    gateway: str = "192.0.2.1",
    enabled: bool = True,
    defaultgw: bool = False,
    monitor: str = "",
    priority: int = DEFAULT_PRIORITY,
    weight: int = DEFAULT_WEIGHT,
    description: str = "",
    lock: bool = False,
    monitor_disable: bool = False,
) -> GatewayConfig:
    return GatewayConfig(
        name=name,
        interface=interface,
        protocol=protocol,  # type: ignore[arg-type]
        gateway=gateway,
        enabled=enabled,
        defaultgw=defaultgw,
        monitor=monitor,
        priority=priority,
        weight=weight,
        description=description,
        lock=lock,
        monitor_disable=monitor_disable,
    )


def _live(
    uuid: str,
    name: str,
    *,
    is_managed: bool = True,
    raw_overrides: dict[str, Any] | None = None,
) -> LiveGateway:
    raw: dict[str, Any] = {"uuid": uuid, "name": name}
    if raw_overrides:
        raw.update(raw_overrides)
    return LiveGateway(uuid=uuid, name=name, is_managed=is_managed, raw=raw)


def _resource(name: str, config: dict[str, Any]) -> ResourceConfig:
    return ResourceConfig(name=name, type="routing.gateways", provider="opnsense", config=config)


# ---------------------------------------------------------------------------
# GatewayConfig.to_payload
# ---------------------------------------------------------------------------


class TestPayload:
    def test_payload_has_envelope(self) -> None:
        payload = _gw("foo").to_payload()
        assert set(payload.keys()) == {"gateway_item"}

    def test_payload_field_set(self) -> None:
        rule = _gw(
            "wan-default",
            interface="wan",
            protocol="inet",
            gateway="192.0.2.1",
            defaultgw=True,
            monitor="1.1.1.1",
            description="WAN default",
            priority=200,
            weight=2,
        )
        inner = rule.to_payload()["gateway_item"]
        assert inner["name"] == "wan-default"
        assert inner["interface"] == "wan"
        assert inner["ipprotocol"] == "inet"
        assert inner["gateway"] == "192.0.2.1"
        assert inner["defaultgw"] == "1"
        assert inner["monitor"] == "1.1.1.1"
        assert inner["descr"] == "WAN default"
        assert inner["priority"] == "200"
        assert inner["weight"] == "2"

    def test_enabled_true_serializes_disabled_zero(self) -> None:
        # operator-facing ``enabled=True`` → wire ``disabled=0``.
        inner = _gw("foo", enabled=True).to_payload()["gateway_item"]
        assert inner["disabled"] == "0"

    def test_enabled_false_serializes_disabled_one(self) -> None:
        inner = _gw("foo", enabled=False).to_payload()["gateway_item"]
        assert inner["disabled"] == "1"

    def test_ipaddr_not_sent_on_wire(self) -> None:
        # ipaddr is operator-facing only; the wire only carries ``gateway``.
        rule = GatewayConfig(
            name="dyn",
            interface="wan",
            protocol="inet",
            gateway="",
            ipaddr="dynamic",
        )
        inner = rule.to_payload()["gateway_item"]
        assert "ipaddr" not in inner

    def test_default_priority_and_weight(self) -> None:
        inner = _gw("foo").to_payload()["gateway_item"]
        assert inner["priority"] == str(DEFAULT_PRIORITY)
        assert inner["weight"] == str(DEFAULT_WEIGHT)


class TestDiffKey:
    def test_diff_key_is_name(self) -> None:
        assert _gw("foo").diff_key == "foo"

    def test_live_diff_key_is_name(self) -> None:
        assert _live("u1", "foo").diff_key == "foo"


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
    def test_new_gateway_adds(self) -> None:
        diff = compute_diff([_gw("wan-default")], [])
        assert len(diff.adds) == 1
        assert diff.adds[0].name == "wan-default"


class TestComputeDiffUpdates:
    def test_update_when_gateway_ip_changes(self) -> None:
        # Live raw must reflect every field in to_payload so we only diff
        # on the one we want.
        rule = _gw("wan-default", gateway="192.0.2.1")
        live_raw = {"uuid": "u1", **rule.to_payload()["gateway_item"]}
        live_raw["gateway"] = "192.0.2.99"  # different
        live = LiveGateway(uuid="u1", name="wan-default", is_managed=True, raw=live_raw)
        diff = compute_diff([rule], [live])
        assert len(diff.updates) == 1
        live_record, want = diff.updates[0]
        assert live_record.uuid == "u1"
        assert want.gateway == "192.0.2.1"

    def test_no_update_when_payload_matches(self) -> None:
        rule = _gw("wan-default", gateway="192.0.2.1")
        live_raw = {"uuid": "u1", **rule.to_payload()["gateway_item"]}
        live = LiveGateway(uuid="u1", name="wan-default", is_managed=True, raw=live_raw)
        diff = compute_diff([rule], [live])
        assert diff.is_empty


class TestComputeDiffDeletes:
    def test_managed_live_with_no_desired_is_deleted(self) -> None:
        diff = compute_diff([], [_live("u1", "stale")])
        assert len(diff.deletes) == 1
        assert diff.deletes[0].uuid == "u1"

    def test_dynamic_live_silently_ignored(self) -> None:
        # Dynamic gateways (e.g., WAN_DHCP) must not be deletable.
        diff = compute_diff([], [_live("WAN_DHCP", "WAN_DHCP", is_managed=False)])
        assert diff.deletes == []
        assert diff.is_empty

    def test_add_only_suppresses_deletes(self) -> None:
        diff = compute_diff([], [_live("u1", "stale")], add_only=True)
        assert diff.deletes == []
        assert diff.is_empty


class TestComputeDiffLocked:
    def test_locked_resource_with_match_skipped_from_actions(self) -> None:
        rule = _gw("wan-survival", gateway="192.0.2.1", lock=True)
        # Force a field difference so update would normally fire.
        live_raw = {"uuid": "u1", **rule.to_payload()["gateway_item"]}
        live_raw["gateway"] = "192.0.2.99"
        live = LiveGateway(uuid="u1", name="wan-survival", is_managed=True, raw=live_raw)
        diff = compute_diff([rule], [live])
        assert diff.adds == []
        assert diff.updates == []
        assert diff.deletes == []
        assert len(diff.locked) == 1
        want, have = diff.locked[0]
        assert want.lock is True
        assert have is not None
        assert have.uuid == "u1"

    def test_locked_resource_without_match(self) -> None:
        rule = _gw("missing", lock=True)
        diff = compute_diff([rule], [])
        assert len(diff.locked) == 1
        _want, have = diff.locked[0]
        assert have is None

    def test_locked_resource_does_not_appear_as_delete_when_only_in_yaml(self) -> None:
        # Confirms locked names are excluded from the delete pass even when
        # they have no live counterpart and there's another live to delete.
        rule = _gw("locked-name", lock=True)
        live_other = _live("u2", "stale")
        diff = compute_diff([rule], [live_other])
        # ``stale`` should still be deleted (it's not the locked name).
        assert [d.name for d in diff.deletes] == ["stale"]


class TestDiffIsEmpty:
    def test_empty_diff(self) -> None:
        assert Diff().is_empty

    def test_locked_alone_counts_as_empty(self) -> None:
        diff = Diff(locked=[(_gw("foo", lock=True), None)])
        assert diff.is_empty

    def test_non_empty_when_adds(self) -> None:
        diff = Diff(adds=[_gw("foo")])
        assert not diff.is_empty


# ---------------------------------------------------------------------------
# _normalize_field
# ---------------------------------------------------------------------------


class TestNormalizeField:
    def test_none_becomes_empty(self) -> None:
        assert _normalize_field(None) == ""

    def test_bool_true_becomes_one(self) -> None:
        # searchGateway returns booleans for some fields; normalize to "1"/"0".
        assert _normalize_field(True) == "1"

    def test_bool_false_becomes_zero(self) -> None:
        assert _normalize_field(False) == "0"

    def test_string_passthrough(self) -> None:
        assert _normalize_field("wan") == "wan"

    def test_int_stringified(self) -> None:
        assert _normalize_field(254) == "254"

    def test_select_dict_extracts_selected_key(self) -> None:
        # getGateway returns interface as a select dict.
        value = {
            "lan": {"value": "LAN", "selected": 0},
            "wan": {"value": "WAN", "selected": 1},
        }
        assert _normalize_field(value) == "wan"

    def test_select_dict_no_selection_returns_empty(self) -> None:
        value = {"lan": {"value": "LAN", "selected": 0}}
        assert _normalize_field(value) == ""


# ---------------------------------------------------------------------------
# gateway_configs_from_resources
# ---------------------------------------------------------------------------


class TestConfigsFromResources:
    def test_valid_static_parses(self) -> None:
        r = _resource(
            "wan-default",
            {
                "interface": "wan",
                "protocol": "inet",
                "gateway": "192.0.2.1",
                "description": "WAN default",
                "defaultgw": True,
            },
        )
        result = gateway_configs_from_resources([r])
        assert len(result) == 1
        cfg = result[0]
        assert cfg.name == "wan-default"
        assert cfg.protocol == "inet"
        assert cfg.gateway == "192.0.2.1"
        assert cfg.defaultgw is True

    def test_dynamic_skips_gateway_requirement(self) -> None:
        r = _resource(
            "wan-dyn",
            {
                "interface": "wan",
                "protocol": "inet",
                "ipaddr": "dynamic",
            },
        )
        # No 'gateway' field; allowed because ipaddr is "dynamic".
        result = gateway_configs_from_resources([r])
        assert len(result) == 1
        assert result[0].gateway == ""
        assert result[0].ipaddr == "dynamic"

    def test_missing_gateway_when_not_dynamic_rejected(self) -> None:
        r = _resource(
            "bad",
            {"interface": "wan", "protocol": "inet"},
        )
        with pytest.raises(ValueError, match="gateway"):
            gateway_configs_from_resources([r])

    def test_missing_interface_rejected(self) -> None:
        r = _resource(
            "bad",
            {"protocol": "inet", "gateway": "192.0.2.1"},
        )
        with pytest.raises(ValueError, match="interface"):
            gateway_configs_from_resources([r])

    def test_missing_protocol_rejected(self) -> None:
        r = _resource("bad", {"interface": "wan", "gateway": "192.0.2.1"})
        with pytest.raises(ValueError, match="protocol"):
            gateway_configs_from_resources([r])

    def test_invalid_protocol_rejected(self) -> None:
        r = _resource(
            "bad",
            {"interface": "wan", "protocol": "ipv7", "gateway": "192.0.2.1"},
        )
        with pytest.raises(ValueError, match="protocol"):
            gateway_configs_from_resources([r])

    def test_non_nat_resources_ignored(self) -> None:
        gw = _resource(
            "ok",
            {"interface": "wan", "protocol": "inet", "gateway": "192.0.2.1"},
        )
        other = ResourceConfig(name="x", type="firewall.aliases", provider="opnsense", config={})
        result = gateway_configs_from_resources([gw, other])
        assert len(result) == 1

    def test_lock_must_be_bool(self) -> None:
        r = _resource(
            "bad",
            {
                "interface": "wan",
                "protocol": "inet",
                "gateway": "192.0.2.1",
                "lock": "yes",
            },
        )
        with pytest.raises(ValueError, match="lock"):
            gateway_configs_from_resources([r])

    def test_priority_must_be_int(self) -> None:
        r = _resource(
            "bad",
            {
                "interface": "wan",
                "protocol": "inet",
                "gateway": "192.0.2.1",
                "priority": "high",
            },
        )
        with pytest.raises(ValueError, match="priority"):
            gateway_configs_from_resources([r])

    def test_weight_must_be_int(self) -> None:
        r = _resource(
            "bad",
            {
                "interface": "wan",
                "protocol": "inet",
                "gateway": "192.0.2.1",
                "weight": "heavy",
            },
        )
        with pytest.raises(ValueError, match="weight"):
            gateway_configs_from_resources([r])

    def test_description_must_be_string(self) -> None:
        r = _resource(
            "bad",
            {
                "interface": "wan",
                "protocol": "inet",
                "gateway": "192.0.2.1",
                "description": 12345,
            },
        )
        with pytest.raises(ValueError, match="description"):
            gateway_configs_from_resources([r])

    def test_non_dict_config_rejected(self) -> None:
        r = ResourceConfig(
            name="bad",
            type="routing.gateways",
            provider="opnsense",
            config={"interface": "wan", "protocol": "inet", "gateway": "192.0.2.1"},
        )
        # Bypass pydantic — guard the service-side defensive check.
        r.config = "not-a-dict"  # type: ignore[assignment]
        with pytest.raises(ValueError, match="non-dict"):
            gateway_configs_from_resources([r])


# ---------------------------------------------------------------------------
# _row_to_live
# ---------------------------------------------------------------------------


class TestRowToLive:
    def test_managed_row(self) -> None:
        row = {"uuid": "u1", "name": "wan-default"}
        live = _row_to_live(row)
        assert live.uuid == "u1"
        assert live.name == "wan-default"
        assert live.is_managed is True

    def test_dynamic_row_marked_unmanaged(self) -> None:
        row = {"uuid": "WAN_DHCP", "name": "WAN_DHCP", "dynamic": True, "virtual": True}
        live = _row_to_live(row)
        assert live.is_managed is False

    def test_virtual_only_marked_unmanaged(self) -> None:
        # Defensive: even a virtual without dynamic counts as unmanaged.
        row = {"uuid": "u-v", "name": "vt", "virtual": True}
        live = _row_to_live(row)
        assert live.is_managed is False

    def test_missing_keys_default(self) -> None:
        live = _row_to_live({})
        assert live.uuid == ""
        assert live.name == ""
        assert live.is_managed is True


# ---------------------------------------------------------------------------
# GatewayService API methods
# ---------------------------------------------------------------------------


class TestServiceSearch:
    def test_search_calls_correct_endpoint(self) -> None:
        client = MagicMock()
        client.request.return_value = {"rows": []}
        svc = GatewayService(client)
        result = svc.search()
        client.request.assert_called_once_with("POST", "routing/settings/searchGateway")
        assert result == []

    def test_search_normalizes_rows(self) -> None:
        client = MagicMock()
        client.request.return_value = {
            "rows": [
                {"uuid": "u1", "name": "managed"},
                "not-a-dict",  # filtered out
                {"uuid": "WAN_DHCP", "name": "WAN_DHCP", "dynamic": True, "virtual": True},
            ]
        }
        svc = GatewayService(client)
        result = svc.search()
        assert len(result) == 2
        assert result[0].name == "managed" and result[0].is_managed
        assert result[1].name == "WAN_DHCP" and not result[1].is_managed


class TestServiceGet:
    def test_get_uses_get_verb(self) -> None:
        client = MagicMock()
        client.request.return_value = {"gateway_item": {"name": "foo"}}
        svc = GatewayService(client)
        result = svc.get("u1")
        client.request.assert_called_once_with("GET", "routing/settings/getGateway/u1")
        assert result == {"gateway_item": {"name": "foo"}}


class TestServiceWriteOps:
    def test_add_posts_correct_endpoint(self) -> None:
        client = MagicMock()
        client.request.return_value = {"result": "saved", "uuid": "new"}
        svc = GatewayService(client)
        rule = _gw("wan-default")
        svc.add(rule)
        client.request.assert_called_once_with(
            "POST", "routing/settings/addGateway", data=rule.to_payload()
        )

    def test_update_posts_correct_endpoint(self) -> None:
        client = MagicMock()
        client.request.return_value = {"result": "saved"}
        svc = GatewayService(client)
        rule = _gw("wan-default")
        svc.update("uuid-abc", rule)
        client.request.assert_called_once_with(
            "POST", "routing/settings/setGateway/uuid-abc", data=rule.to_payload()
        )

    def test_delete_posts_correct_endpoint(self) -> None:
        client = MagicMock()
        svc = GatewayService(client)
        svc.delete("u1")
        client.request.assert_called_once_with("POST", "routing/settings/delGateway/u1")

    def test_reconfigure_posts_correct_endpoint(self) -> None:
        client = MagicMock()
        svc = GatewayService(client)
        svc.reconfigure()
        client.request.assert_called_once_with("POST", "routing/settings/reconfigure")


class TestApplyDiff:
    def test_empty_diff_is_noop(self) -> None:
        client = MagicMock()
        svc = GatewayService(client)
        counts = svc.apply_diff(Diff())
        client.request.assert_not_called()
        assert counts == {"created": 0, "updated": 0, "deleted": 0}

    def test_add_calls_reconfigure_once(self) -> None:
        client = MagicMock()
        client.request.return_value = {"result": "saved"}
        svc = GatewayService(client)
        diff = Diff(adds=[_gw("wan-default")])
        counts = svc.apply_diff(diff)
        endpoints = [c.args[1] for c in client.request.call_args_list]
        assert "routing/settings/addGateway" in endpoints
        assert endpoints.count("routing/settings/reconfigure") == 1
        assert counts == {"created": 1, "updated": 0, "deleted": 0}

    def test_update_calls_reconfigure_once(self) -> None:
        client = MagicMock()
        client.request.return_value = {"result": "saved"}
        svc = GatewayService(client)
        live = _live("u1", "wan-default")
        rule = _gw("wan-default")
        diff = Diff(updates=[(live, rule)])
        counts = svc.apply_diff(diff)
        endpoints = [c.args[1] for c in client.request.call_args_list]
        assert "routing/settings/setGateway/u1" in endpoints
        assert endpoints.count("routing/settings/reconfigure") == 1
        assert counts == {"created": 0, "updated": 1, "deleted": 0}

    def test_delete_calls_reconfigure_once(self) -> None:
        client = MagicMock()
        svc = GatewayService(client)
        diff = Diff(deletes=[_live("u1", "stale"), _live("u2", "stale2")])
        counts = svc.apply_diff(diff)
        endpoints = [c.args[1] for c in client.request.call_args_list]
        assert "routing/settings/delGateway/u1" in endpoints
        assert "routing/settings/delGateway/u2" in endpoints
        assert endpoints.count("routing/settings/reconfigure") == 1
        assert counts == {"created": 0, "updated": 0, "deleted": 2}


# ---------------------------------------------------------------------------
# export_to_yaml + _live_to_export_config
# ---------------------------------------------------------------------------


class TestExportToYaml:
    def test_managed_gateways_appear_in_export(self) -> None:
        client = MagicMock()
        # First call: searchGateway. Subsequent calls: per-uuid getGateway.
        client.request.side_effect = [
            {
                "rows": [
                    {"uuid": "u1", "name": "wan-default"},
                    {
                        "uuid": "WAN_DHCP",
                        "name": "WAN_DHCP",
                        "dynamic": True,
                        "virtual": True,
                    },
                ]
            },
            # getGateway/u1
            {
                "gateway_item": {
                    "disabled": "0",
                    "name": "wan-default",
                    "interface": {"wan": {"value": "WAN", "selected": 1}},
                    "ipprotocol": {"inet": {"value": "IPv4", "selected": 1}},
                    "gateway": "192.0.2.1",
                    "defaultgw": "1",
                    "monitor": "1.1.1.1",
                    "monitor_disable": "0",
                    "monitor_noroute": "0",
                    "force_down": "0",
                    "fargw": "0",
                    "priority": "200",
                    "weight": "1",
                    "descr": "WAN default",
                }
            },
        ]
        svc = GatewayService(client)
        text = svc.export_to_yaml()
        # Managed gateway present.
        assert "wan-default" in text
        # Dynamic gateway excluded.
        assert "WAN_DHCP" not in text
        # Field decoding worked.
        assert "interface: wan" in text
        assert "protocol: inet" in text
        assert "defaultgw: true" in text
        assert "priority: 200" in text

    def test_export_with_no_gateways_yields_empty_resources(self) -> None:
        client = MagicMock()
        client.request.return_value = {"rows": []}
        svc = GatewayService(client)
        text = svc.export_to_yaml()
        assert "resources: []" in text


class TestLiveToExportConfig:
    def test_decoding_select_dicts_and_bools(self) -> None:
        get_response = {
            "gateway_item": {
                "disabled": "1",
                "interface": {"opt1": {"value": "OPT1", "selected": 1}},
                "ipprotocol": {"inet6": {"value": "IPv6", "selected": 1}},
                "gateway": "fe80::1",
                "defaultgw": "0",
                "fargw": "1",
                "monitor": "",
                "monitor_disable": "1",
                "monitor_noroute": "0",
                "force_down": "0",
                "priority": "100",
                "weight": "5",
                "descr": "v6 gw",
            }
        }
        cfg = _live_to_export_config(get_response)
        assert cfg["enabled"] is False  # disabled "1" → enabled False
        assert cfg["interface"] == "opt1"
        assert cfg["protocol"] == "inet6"
        assert cfg["fargw"] is True
        assert cfg["monitor_disable"] is True
        assert cfg["priority"] == 100
        assert cfg["weight"] == 5
        assert cfg["description"] == "v6 gw"

    def test_missing_envelope_yields_defaults(self) -> None:
        cfg = _live_to_export_config({})
        # Defensive defaults so an empty response doesn't crash.
        assert cfg["protocol"] == "inet"
        assert cfg["priority"] == DEFAULT_PRIORITY
        assert cfg["weight"] == DEFAULT_WEIGHT
