"""Unit tests for ``infrafoundry.providers.opnsense.services.virtual_ip``.

Coverage:
    - ``VirtualIPConfig.to_payload`` envelope shape per mode
      (ipalias / carp / proxyarp), bool stringification,
      ``description`` → ``descr`` mapping, name-not-on-wire invariant.
    - ``compute_diff`` adds / updates / deletes / lock / add_only
      semantics. Identity tuple ``(interface, mode, address, vhid)``
      is what governs matching; YAML name is metadata.
    - ``_normalize_field`` for option-dicts, bools, None, scalars.
    - ``virtual_ip_configs_from_resources`` parser validation per mode.
    - ``VirtualIPService`` CRUD method dispatch via mocked
      ``OPNsenseClient.request``.
    - ``apply_diff`` orchestration (single ``reconfigure`` if any mutation).
    - ``export_to_yaml`` round-trip with synthetic name + password
      redaction for CARP entries.
    - Update detection skips the ``password`` field (OPNsense never
      returns plaintext on read).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.services.virtual_ip import (
    Diff,
    LiveVirtualIP,
    VirtualIPConfig,
    VirtualIPService,
    _live_to_export_config,
    _normalize_field,
    _row_to_live,
    _synthesize_name,
    compute_diff,
    virtual_ip_configs_from_resources,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _vip(
    name: str,
    *,
    interface: str = "lan",
    mode: str = "ipalias",
    address: str = "10.0.0.10",
    network: str = "24",
    description: str = "",
    enabled: bool = True,
    lock: bool = False,
    password: str = "",
    vhid: str = "",
    advbase: str = "1",
    advskew: str = "0",
    peer: str = "",
    peer6: str = "",
    nosync: bool = False,
    gateway: str = "",
    noexpand: bool = False,
    nobind: bool = False,
) -> VirtualIPConfig:
    return VirtualIPConfig(
        name=name,
        interface=interface,
        mode=mode,  # type: ignore[arg-type]
        address=address,
        network=network,
        description=description,
        enabled=enabled,
        lock=lock,
        password=password,
        vhid=vhid,
        advbase=advbase,
        advskew=advskew,
        peer=peer,
        peer6=peer6,
        nosync=nosync,
        gateway=gateway,
        noexpand=noexpand,
        nobind=nobind,
    )


def _live(
    uuid: str,
    *,
    interface: str = "lan",
    mode: str = "ipalias",
    address: str = "10.0.0.10",
    vhid: str = "",
    raw_overrides: dict[str, Any] | None = None,
) -> LiveVirtualIP:
    raw: dict[str, Any] = {
        "uuid": uuid,
        "interface": interface,
        "mode": mode,
        "address": address,
        "network": "24",
        "vhid": vhid,
        "descr": "",
    }
    if raw_overrides:
        raw.update(raw_overrides)
    return LiveVirtualIP(
        uuid=uuid,
        interface=interface,
        mode=mode,
        address=address,
        vhid=vhid,
        raw=raw,
    )


def _resource(name: str, config: dict[str, Any]) -> ResourceConfig:
    return ResourceConfig(
        name=name, type="interfaces.virtual_ips", provider="opnsense", config=config
    )


# ---------------------------------------------------------------------------
# VirtualIPConfig.to_payload — envelope + per-mode
# ---------------------------------------------------------------------------


class TestPayloadEnvelope:
    def test_envelope_key_is_vip(self) -> None:
        payload = _vip("foo").to_payload()
        assert set(payload.keys()) == {"vip"}

    def test_name_not_on_wire(self) -> None:
        inner = _vip("operator-friendly").to_payload()["vip"]
        assert "name" not in inner

    def test_description_maps_to_descr(self) -> None:
        inner = _vip("foo", description="lan VIP").to_payload()["vip"]
        assert inner["descr"] == "lan VIP"
        assert "description" not in inner


class TestPayloadIpalias:
    def test_ipalias_only_fields(self) -> None:
        inner = _vip(
            "foo",
            mode="ipalias",
            gateway="my-gw",
            noexpand=True,
            nobind=False,
        ).to_payload()["vip"]
        assert inner["mode"] == "ipalias"
        assert inner["gateway"] == "my-gw"
        assert inner["noexpand"] == "1"
        assert inner["nobind"] == "0"
        # CARP-only fields absent.
        assert "vhid" not in inner
        assert "password" not in inner
        assert "advbase" not in inner

    def test_ipalias_default_gateway_empty(self) -> None:
        inner = _vip("foo", mode="ipalias").to_payload()["vip"]
        assert inner["gateway"] == ""


class TestPayloadCarp:
    def test_carp_required_fields(self) -> None:
        inner = _vip(
            "foo",
            mode="carp",
            address="10.0.0.1",
            password="s3kr1t",
            vhid="1",
            advbase="2",
            advskew="50",
            peer="10.0.0.2",
            peer6="fe80::2",
            nosync=True,
        ).to_payload()["vip"]
        assert inner["mode"] == "carp"
        assert inner["password"] == "s3kr1t"
        assert inner["vhid"] == "1"
        assert inner["advbase"] == "2"
        assert inner["advskew"] == "50"
        assert inner["peer"] == "10.0.0.2"
        assert inner["peer6"] == "fe80::2"
        assert inner["nosync"] == "1"
        # ipalias-only fields absent.
        assert "gateway" not in inner
        assert "noexpand" not in inner
        assert "nobind" not in inner

    def test_carp_defaults_advbase_advskew(self) -> None:
        inner = _vip("foo", mode="carp", password="x", vhid="1").to_payload()["vip"]
        assert inner["advbase"] == "1"
        assert inner["advskew"] == "0"
        assert inner["nosync"] == "0"


class TestPayloadProxyArp:
    def test_proxyarp_minimal_fields(self) -> None:
        inner = _vip("foo", mode="proxyarp").to_payload()["vip"]
        assert inner["mode"] == "proxyarp"
        # Neither CARP nor ipalias fields should appear.
        assert "vhid" not in inner
        assert "password" not in inner
        assert "gateway" not in inner
        assert "noexpand" not in inner
        # Required core fields still present.
        assert inner["interface"] == "lan"
        assert inner["address"] == "10.0.0.10"
        assert inner["network"] == "24"


# ---------------------------------------------------------------------------
# Diff key
# ---------------------------------------------------------------------------


class TestDiffKey:
    def test_includes_mode_and_vhid(self) -> None:
        v = _vip("foo", interface="lan", mode="carp", address="10.0.0.1", vhid="1")
        assert v.diff_key == ("lan", "carp", "10.0.0.1", "1")

    def test_yaml_name_does_not_affect_diff_key(self) -> None:
        a = _vip("name-one", interface="lan", mode="ipalias", address="10.0.0.1")
        b = _vip("name-two", interface="lan", mode="ipalias", address="10.0.0.1")
        assert a.diff_key == b.diff_key

    def test_two_carp_at_same_address_distinguished_by_vhid(self) -> None:
        a = _vip("a", mode="carp", address="10.0.0.1", vhid="1")
        b = _vip("b", mode="carp", address="10.0.0.1", vhid="2")
        assert a.diff_key != b.diff_key

    def test_ipalias_vs_carp_at_same_address_distinguished(self) -> None:
        a = _vip("a", mode="ipalias", address="10.0.0.1")
        b = _vip("b", mode="carp", address="10.0.0.1", vhid="1")
        assert a.diff_key != b.diff_key


# ---------------------------------------------------------------------------
# compute_diff
# ---------------------------------------------------------------------------


class TestComputeDiffEmpty:
    def test_no_desired_no_live_is_empty(self) -> None:
        diff = compute_diff([], [])
        assert diff.is_empty
        assert diff.adds == []
        assert diff.updates == []
        assert diff.deletes == []
        assert diff.locked == []


class TestComputeDiffAdds:
    def test_new_vip_adds(self) -> None:
        diff = compute_diff([_vip("foo")], [])
        assert len(diff.adds) == 1
        assert diff.adds[0].name == "foo"


class TestComputeDiffUpdates:
    def test_update_when_description_changes(self) -> None:
        v = _vip("foo", description="new")
        live = _live("u1", raw_overrides={"descr": "old"})
        diff = compute_diff([v], [live])
        assert len(diff.updates) == 1
        live_record, want = diff.updates[0]
        assert live_record.uuid == "u1"
        assert want.description == "new"

    def test_no_update_when_payload_matches(self) -> None:
        v = _vip("foo")
        # Mirror what to_payload would emit.
        live_raw: dict[str, Any] = {"uuid": "u1", **v.to_payload()["vip"]}
        live = LiveVirtualIP(
            uuid="u1",
            interface="lan",
            mode="ipalias",
            address="10.0.0.10",
            vhid="",
            raw=live_raw,
        )
        diff = compute_diff([v], [live])
        assert diff.is_empty

    def test_password_diff_does_not_trigger_update(self) -> None:
        # OPNsense never returns plaintext password on read; skipping
        # password from update detection avoids spurious updates on
        # every run.
        v = _vip("foo", mode="carp", password="newpass", vhid="1")
        live_raw: dict[str, Any] = {
            "uuid": "u1",
            **v.to_payload()["vip"],
            "password": "",  # API always returns empty
        }
        live = LiveVirtualIP(
            uuid="u1",
            interface="lan",
            mode="carp",
            address="10.0.0.10",
            vhid="1",
            raw=live_raw,
        )
        diff = compute_diff([v], [live])
        # No update should trigger from a password-only diff.
        assert diff.is_empty

    def test_changing_address_is_delete_plus_add(self) -> None:
        # Identity tuple changed → delete + add.
        old_live = _live("u1", address="10.0.0.10")
        new_vip = _vip("foo", address="10.0.0.20")
        diff = compute_diff([new_vip], [old_live])
        assert len(diff.adds) == 1
        assert diff.adds[0].address == "10.0.0.20"
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


class TestComputeDiffLocked:
    def test_locked_skipped_from_actions(self) -> None:
        v = _vip("survival", lock=True)
        live = _live("u1", raw_overrides={"descr": "drift!"})
        diff = compute_diff([v], [live])
        assert diff.adds == []
        assert diff.updates == []
        assert diff.deletes == []
        assert len(diff.locked) == 1
        want, have = diff.locked[0]
        assert want.lock is True
        assert have is not None and have.uuid == "u1"

    def test_locked_excluded_from_delete_pass(self) -> None:
        # Locked entry has no live counterpart; another live entry
        # exists at a different address → only the unmanaged live
        # entry should be deleted.
        locked_yaml = _vip("locked", lock=True, address="10.0.0.10")
        other_live = _live("u2", address="172.16.0.10")
        diff = compute_diff([locked_yaml], [other_live])
        assert len(diff.deletes) == 1
        assert diff.deletes[0].address == "172.16.0.10"


class TestDiffIsEmpty:
    def test_empty_diff(self) -> None:
        assert Diff().is_empty

    def test_locked_alone_counts_as_empty(self) -> None:
        diff = Diff(locked=[(_vip("foo", lock=True), None)])
        assert diff.is_empty

    def test_non_empty_when_adds(self) -> None:
        diff = Diff(adds=[_vip("foo")])
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
        assert _normalize_field("lan") == "lan"

    def test_int_stringified(self) -> None:
        assert _normalize_field(24) == "24"

    def test_select_dict_extracts_selected_key(self) -> None:
        value = {
            "ipalias": {"value": "IP Alias", "selected": 1},
            "carp": {"value": "CARP", "selected": 0},
        }
        assert _normalize_field(value) == "ipalias"

    def test_select_dict_no_selection_returns_empty(self) -> None:
        value = {"ipalias": {"value": "IP Alias", "selected": 0}}
        assert _normalize_field(value) == ""


# ---------------------------------------------------------------------------
# virtual_ip_configs_from_resources
# ---------------------------------------------------------------------------


class TestParserIpalias:
    def test_minimal_ipalias_parses(self) -> None:
        r = _resource(
            "foo",
            {
                "mode": "ipalias",
                "interface": "lan",
                "address": "10.0.0.10",
                "network": "24",
            },
        )
        result = virtual_ip_configs_from_resources([r])
        assert len(result) == 1
        cfg = result[0]
        assert cfg.mode == "ipalias"
        assert cfg.address == "10.0.0.10"
        assert cfg.network == "24"
        assert cfg.gateway == ""

    def test_default_mode_is_ipalias(self) -> None:
        r = _resource(
            "foo",
            {"interface": "lan", "address": "10.0.0.10", "network": "24"},
        )
        cfg = virtual_ip_configs_from_resources([r])[0]
        assert cfg.mode == "ipalias"


class TestParserCarp:
    def test_carp_with_required_fields(self) -> None:
        r = _resource(
            "foo",
            {
                "mode": "carp",
                "interface": "lan",
                "address": "10.0.0.1",
                "network": "24",
                "vhid": "1",
                "password": "s3kr1t",
            },
        )
        cfg = virtual_ip_configs_from_resources([r])[0]
        assert cfg.mode == "carp"
        assert cfg.password == "s3kr1t"
        assert cfg.vhid == "1"
        assert cfg.advbase == "1"
        assert cfg.advskew == "0"

    def test_carp_missing_vhid_rejected(self) -> None:
        r = _resource(
            "bad",
            {
                "mode": "carp",
                "interface": "lan",
                "address": "10.0.0.1",
                "network": "24",
                "password": "x",
            },
        )
        with pytest.raises(ValueError, match="vhid"):
            virtual_ip_configs_from_resources([r])

    def test_carp_vhid_as_int_coerced_to_string(self) -> None:
        r = _resource(
            "foo",
            {
                "mode": "carp",
                "interface": "lan",
                "address": "10.0.0.1",
                "network": "24",
                "vhid": 5,
                "password": "x",
            },
        )
        cfg = virtual_ip_configs_from_resources([r])[0]
        assert cfg.vhid == "5"


class TestParserProxyarp:
    def test_proxyarp_no_extra_fields(self) -> None:
        r = _resource(
            "foo",
            {
                "mode": "proxyarp",
                "interface": "lan",
                "address": "10.0.0.10",
                "network": "24",
            },
        )
        cfg = virtual_ip_configs_from_resources([r])[0]
        assert cfg.mode == "proxyarp"
        assert cfg.gateway == ""
        assert cfg.password == ""
        assert cfg.vhid == ""


class TestParserRejection:
    def test_invalid_mode_rejected(self) -> None:
        r = _resource(
            "bad",
            {
                "mode": "alias",  # NOT a valid mode (issue body was wrong)
                "interface": "lan",
                "address": "10.0.0.10",
                "network": "24",
            },
        )
        with pytest.raises(ValueError, match="mode"):
            virtual_ip_configs_from_resources([r])

    def test_missing_interface_rejected(self) -> None:
        r = _resource("bad", {"mode": "ipalias", "address": "10.0.0.10", "network": "24"})
        with pytest.raises(ValueError, match="interface"):
            virtual_ip_configs_from_resources([r])

    def test_missing_address_rejected(self) -> None:
        r = _resource("bad", {"mode": "ipalias", "interface": "lan", "network": "24"})
        with pytest.raises(ValueError, match="address"):
            virtual_ip_configs_from_resources([r])

    def test_missing_network_rejected(self) -> None:
        r = _resource("bad", {"mode": "ipalias", "interface": "lan", "address": "10.0.0.10"})
        with pytest.raises(ValueError, match="network"):
            virtual_ip_configs_from_resources([r])

    def test_non_dict_config_rejected(self) -> None:
        r = ResourceConfig(
            name="bad",
            type="interfaces.virtual_ips",
            provider="opnsense",
            config={"mode": "ipalias", "interface": "lan", "address": "10.0.0.10", "network": "24"},
        )
        # Bypass pydantic — guard the service-side defensive check.
        r.config = "not-a-dict"  # type: ignore[assignment]
        with pytest.raises(ValueError, match="non-dict"):
            virtual_ip_configs_from_resources([r])

    def test_non_bool_lock_rejected(self) -> None:
        r = _resource(
            "bad",
            {
                "mode": "ipalias",
                "interface": "lan",
                "address": "10.0.0.10",
                "network": "24",
                "lock": "yes",
            },
        )
        with pytest.raises(ValueError, match="lock"):
            virtual_ip_configs_from_resources([r])

    def test_non_virtual_ip_resources_ignored(self) -> None:
        v = _resource(
            "ok",
            {"mode": "ipalias", "interface": "lan", "address": "10.0.0.10", "network": "24"},
        )
        other = ResourceConfig(name="x", type="firewall.aliases", provider="opnsense", config={})
        result = virtual_ip_configs_from_resources([v, other])
        assert len(result) == 1
        assert result[0].name == "ok"


# ---------------------------------------------------------------------------
# _row_to_live + _synthesize_name
# ---------------------------------------------------------------------------


class TestRowToLive:
    def test_basic_row(self) -> None:
        row = {
            "uuid": "u1",
            "interface": "lan",
            "mode": "ipalias",
            "address": "10.0.0.10",
            "network": "24",
            "vhid": "",
        }
        live = _row_to_live(row)
        assert live.uuid == "u1"
        assert live.interface == "lan"
        assert live.mode == "ipalias"
        assert live.address == "10.0.0.10"
        assert live.vhid == ""

    def test_missing_keys_default(self) -> None:
        live = _row_to_live({})
        assert live.uuid == ""
        assert live.interface == ""
        assert live.mode == ""
        assert live.address == ""
        assert live.vhid == ""

    def test_option_dict_normalizes(self) -> None:
        row = {
            "uuid": "u1",
            "interface": {"lan": {"value": "LAN", "selected": 1}},
            "mode": {"carp": {"value": "CARP", "selected": 1}},
            "address": "10.0.0.1",
            "vhid": "5",
        }
        live = _row_to_live(row)
        assert live.interface == "lan"
        assert live.mode == "carp"


class TestSynthesizeName:
    def test_ipalias_no_vhid_suffix(self) -> None:
        live = _live("u1", interface="lan", mode="ipalias", address="10.0.0.10")
        name = _synthesize_name(live)
        assert name == "vip-ipalias-lan-10-0-0-10"

    def test_carp_appends_vhid(self) -> None:
        live = _live("u1", interface="lan", mode="carp", address="10.0.0.1", vhid="1")
        name = _synthesize_name(live)
        assert name == "vip-carp-lan-10-0-0-1-vhid1"

    def test_ipv6_address_replaced(self) -> None:
        live = _live("u1", interface="lan", mode="ipalias", address="2001:db8::1")
        name = _synthesize_name(live)
        # ``:`` and ``.`` are replaced with ``-``.
        assert name == "vip-ipalias-lan-2001-db8--1"

    def test_lowercase(self) -> None:
        live = _live("u1", interface="LAN", mode="ipalias", address="10.0.0.1")
        assert _synthesize_name(live).islower()


# ---------------------------------------------------------------------------
# VirtualIPService API methods
# ---------------------------------------------------------------------------


class TestServiceSearch:
    def test_search_calls_correct_endpoint(self) -> None:
        client = MagicMock()
        client.request.return_value = {"rows": []}
        svc = VirtualIPService(client)
        result = svc.search()
        client.request.assert_called_once_with("POST", "interfaces/vip_settings/searchItem")
        assert result == []

    def test_search_normalizes_rows(self) -> None:
        client = MagicMock()
        client.request.return_value = {
            "rows": [
                {"uuid": "u1", "interface": "lan", "mode": "ipalias", "address": "10.0.0.10"},
                "not-a-dict",  # filtered out
                {"uuid": "u2", "interface": "wan", "mode": "carp", "address": "10.0.0.1"},
            ]
        }
        svc = VirtualIPService(client)
        result = svc.search()
        assert len(result) == 2

    def test_search_handles_non_dict_response(self) -> None:
        client = MagicMock()
        client.request.return_value = "not-a-dict"
        svc = VirtualIPService(client)
        assert svc.search() == []

    def test_search_handles_missing_rows_key(self) -> None:
        client = MagicMock()
        client.request.return_value = {}
        svc = VirtualIPService(client)
        assert svc.search() == []


class TestServiceGet:
    def test_get_uses_get_verb(self) -> None:
        client = MagicMock()
        client.request.return_value = {"vip": {"address": "10.0.0.10"}}
        svc = VirtualIPService(client)
        result = svc.get("u1")
        client.request.assert_called_once_with("GET", "interfaces/vip_settings/getItem/u1")
        assert result == {"vip": {"address": "10.0.0.10"}}


class TestServiceWriteOps:
    def test_add_posts_correct_endpoint(self) -> None:
        client = MagicMock()
        client.request.return_value = {"result": "saved", "uuid": "new"}
        svc = VirtualIPService(client)
        v = _vip("foo")
        svc.add(v)
        client.request.assert_called_once_with(
            "POST", "interfaces/vip_settings/addItem", data=v.to_payload()
        )

    def test_update_posts_correct_endpoint(self) -> None:
        client = MagicMock()
        client.request.return_value = {"result": "saved"}
        svc = VirtualIPService(client)
        v = _vip("foo")
        svc.update("uuid-abc", v)
        client.request.assert_called_once_with(
            "POST", "interfaces/vip_settings/setItem/uuid-abc", data=v.to_payload()
        )

    def test_delete_posts_correct_endpoint(self) -> None:
        client = MagicMock()
        svc = VirtualIPService(client)
        svc.delete("u1")
        client.request.assert_called_once_with("POST", "interfaces/vip_settings/delItem/u1")

    def test_reconfigure_posts_correct_endpoint(self) -> None:
        client = MagicMock()
        svc = VirtualIPService(client)
        svc.reconfigure()
        client.request.assert_called_once_with("POST", "interfaces/vip_settings/reconfigure")


# ---------------------------------------------------------------------------
# apply_diff
# ---------------------------------------------------------------------------


class TestApplyDiff:
    def test_empty_diff_is_noop(self) -> None:
        client = MagicMock()
        svc = VirtualIPService(client)
        counts = svc.apply_diff(Diff())
        client.request.assert_not_called()
        assert counts == {"created": 0, "updated": 0, "deleted": 0}

    def test_add_calls_reconfigure_once(self) -> None:
        client = MagicMock()
        client.request.return_value = {"result": "saved"}
        svc = VirtualIPService(client)
        diff = Diff(adds=[_vip("foo"), _vip("bar", address="10.0.0.20")])
        counts = svc.apply_diff(diff)
        endpoints = [c.args[1] for c in client.request.call_args_list]
        assert endpoints.count("interfaces/vip_settings/addItem") == 2
        assert endpoints.count("interfaces/vip_settings/reconfigure") == 1
        assert counts == {"created": 2, "updated": 0, "deleted": 0}

    def test_update_calls_reconfigure_once(self) -> None:
        client = MagicMock()
        client.request.return_value = {"result": "saved"}
        svc = VirtualIPService(client)
        live = _live("u1")
        v = _vip("foo")
        diff = Diff(updates=[(live, v)])
        counts = svc.apply_diff(diff)
        endpoints = [c.args[1] for c in client.request.call_args_list]
        assert "interfaces/vip_settings/setItem/u1" in endpoints
        assert endpoints.count("interfaces/vip_settings/reconfigure") == 1
        assert counts == {"created": 0, "updated": 1, "deleted": 0}

    def test_delete_calls_reconfigure_once(self) -> None:
        client = MagicMock()
        svc = VirtualIPService(client)
        diff = Diff(
            deletes=[
                _live("u1"),
                _live("u2", address="10.0.0.20"),
            ]
        )
        counts = svc.apply_diff(diff)
        endpoints = [c.args[1] for c in client.request.call_args_list]
        assert "interfaces/vip_settings/delItem/u1" in endpoints
        assert "interfaces/vip_settings/delItem/u2" in endpoints
        assert endpoints.count("interfaces/vip_settings/reconfigure") == 1
        assert counts == {"created": 0, "updated": 0, "deleted": 2}

    def test_mixed_diff_single_reconfigure(self) -> None:
        client = MagicMock()
        client.request.return_value = {"result": "saved"}
        svc = VirtualIPService(client)
        live_for_update = _live("u1")
        live_for_delete = _live("u2", address="10.0.0.20")
        new = _vip("new", address="192.168.0.10")
        update_target = _vip("foo", description="changed")
        diff = Diff(
            adds=[new],
            updates=[(live_for_update, update_target)],
            deletes=[live_for_delete],
        )
        counts = svc.apply_diff(diff)
        endpoints = [c.args[1] for c in client.request.call_args_list]
        assert endpoints.count("interfaces/vip_settings/reconfigure") == 1
        assert counts == {"created": 1, "updated": 1, "deleted": 1}


class TestComputeDiffServiceWrapper:
    def test_service_wrapper_delegates(self) -> None:
        client = MagicMock()
        svc = VirtualIPService(client)
        diff = svc.compute_diff([], [_live("u1")], add_only=True)
        assert diff.deletes == []


# ---------------------------------------------------------------------------
# export_to_yaml + _live_to_export_config
# ---------------------------------------------------------------------------


class TestExportToYaml:
    def test_ipalias_exports(self) -> None:
        client = MagicMock()
        client.request.side_effect = [
            {
                "rows": [
                    {
                        "uuid": "u1",
                        "interface": "lan",
                        "mode": "ipalias",
                        "address": "10.0.0.10",
                        "network": "24",
                        "vhid": "",
                    },
                ]
            },
            {
                "vip": {
                    "interface": {"lan": {"value": "LAN", "selected": 1}},
                    "mode": {"ipalias": {"value": "IP Alias", "selected": 1}},
                    "address": "10.0.0.10",
                    "network": "24",
                    "descr": "lan vip",
                    "gateway": "",
                    "noexpand": "0",
                    "nobind": "0",
                }
            },
        ]
        svc = VirtualIPService(client)
        text = svc.export_to_yaml()
        assert "vip-ipalias-lan-10-0-0-10" in text
        assert "mode: ipalias" in text
        assert "address: 10.0.0.10" in text
        assert "interface: lan" in text
        # Password placeholder NOT emitted for ipalias.
        assert "password" not in text

    def test_carp_export_redacts_password(self) -> None:
        client = MagicMock()
        client.request.side_effect = [
            {
                "rows": [
                    {
                        "uuid": "u1",
                        "interface": "lan",
                        "mode": "carp",
                        "address": "10.0.0.1",
                        "network": "24",
                        "vhid": "1",
                    },
                ]
            },
            {
                "vip": {
                    "interface": {"lan": {"value": "LAN", "selected": 1}},
                    "mode": {"carp": {"value": "CARP", "selected": 1}},
                    "address": "10.0.0.1",
                    "network": "24",
                    "vhid": "1",
                    "advbase": "1",
                    "advskew": "0",
                    "descr": "carp vip",
                }
            },
        ]
        svc = VirtualIPService(client)
        text = svc.export_to_yaml()
        # Password redacted as a secret:// URI placeholder so the
        # operator must populate the real secret.
        assert "secret://env_secrets/" in text
        assert "REPLACE_ME" in text
        assert "vhid: '1'" in text or 'vhid: "1"' in text or "vhid: 1" in text

    def test_export_with_no_vips_yields_empty_resources(self) -> None:
        client = MagicMock()
        client.request.return_value = {"rows": []}
        svc = VirtualIPService(client)
        text = svc.export_to_yaml()
        # Nested format: empty leaf list at opnsense.interfaces.virtual_ips.
        assert "virtual_ips: []" in text


class TestLiveToExportConfig:
    def test_ipalias_decoding(self) -> None:
        get_response = {
            "vip": {
                "interface": {"lan": {"value": "LAN", "selected": 1}},
                "mode": {"ipalias": {"value": "IP Alias", "selected": 1}},
                "address": "10.0.0.10",
                "network": "24",
                "descr": "lan",
                "gateway": "my-gw",
                "noexpand": "1",
                "nobind": "0",
            }
        }
        cfg = _live_to_export_config(get_response)
        assert cfg["mode"] == "ipalias"
        assert cfg["interface"] == "lan"
        assert cfg["gateway"] == "my-gw"
        assert cfg["noexpand"] is True
        assert cfg["nobind"] is False

    def test_carp_decoding_password_placeholder(self) -> None:
        get_response = {
            "vip": {
                "interface": {"lan": {"value": "LAN", "selected": 1}},
                "mode": {"carp": {"value": "CARP", "selected": 1}},
                "address": "10.0.0.1",
                "network": "24",
                "vhid": "5",
                "advbase": "1",
                "advskew": "0",
                "peer": "",
                "peer6": "",
                "nosync": "0",
            }
        }
        cfg = _live_to_export_config(get_response)
        assert cfg["mode"] == "carp"
        assert cfg["vhid"] == "5"
        assert "password" in cfg
        assert cfg["password"].startswith("secret://env_secrets/")
        assert cfg["nosync"] is False

    def test_proxyarp_no_extra_fields(self) -> None:
        get_response = {
            "vip": {
                "interface": {"lan": {"value": "LAN", "selected": 1}},
                "mode": {"proxyarp": {"value": "Proxy ARP", "selected": 1}},
                "address": "10.0.0.10",
                "network": "24",
            }
        }
        cfg = _live_to_export_config(get_response)
        assert cfg["mode"] == "proxyarp"
        assert "vhid" not in cfg
        assert "gateway" not in cfg
        assert "password" not in cfg

    def test_missing_envelope_yields_defaults(self) -> None:
        cfg = _live_to_export_config({})
        # mode defaults to ipalias when missing.
        assert cfg["mode"] == "ipalias"
        assert cfg["address"] == ""
        assert cfg["interface"] == ""

    def test_non_dict_envelope_yields_defaults(self) -> None:
        cfg = _live_to_export_config(None)  # type: ignore[arg-type]
        assert cfg["mode"] == "ipalias"
