"""Unit tests for the Kea DHCPv4 HA services (#1392)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
import yaml

from infrafoundry.core.config.package_loader import PackageLoader
from infrafoundry.core.exceptions import APIError, InvalidConfigurationError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.services._identity import OpnsenseDriftError
from infrafoundry.providers.opnsense.services.kea_dhcp4_ha import (
    KeaHAPeerConfig,
    KeaHAPeerService,
    KeaHASettingsService,
    LiveKeaHAPeer,
    compute_diff,
    peer_configs_from_resources,
    serialize_ha_setting,
)

# -- settings ---------------------------------------------------------------------


def _ha_response(**overrides: Any) -> dict[str, Any]:
    ha: dict[str, Any] = {
        "enabled": "0",
        "this_server_name": "",
        "%this_server_name": "fw-a",
        "max_unacked_clients": "2",
    }
    ha.update(overrides)
    return {"dhcpv4": {"general": {"enabled": "1"}, "lexpire": {"x": "1"}, "ha": ha}}


def _settings_service(*responses: Any) -> KeaHASettingsService:
    client = MagicMock()
    client.request.side_effect = list(responses)
    return KeaHASettingsService(client)


def _ha_res(**config: Any) -> ResourceConfig:
    return ResourceConfig(
        name="kea.dhcp4.ha", type="kea.dhcp4.ha", provider="opnsense", config=config
    )


def test_serialize_ha_setting() -> None:
    assert serialize_ha_setting("enabled", True) == "1"
    assert serialize_ha_setting("enabled", False) == "0"
    assert serialize_ha_setting("this_server_name", "") == ""
    assert serialize_ha_setting("this_server_name", "fw-a") == "fw-a"
    assert serialize_ha_setting("max_unacked_clients", 0) == "0"
    assert serialize_ha_setting("max_unacked_clients", 5) == "5"


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("enabled", "yes"),
        ("this_server_name", 3),
        ("max_unacked_clients", -1),
        ("max_unacked_clients", "2"),
        ("max_unacked_clients", True),
    ],
)
def test_serialize_ha_setting_rejects(key: str, value: Any) -> None:
    with pytest.raises(InvalidConfigurationError):
        serialize_ha_setting(key, value)


def test_build_desired_serializes_declared_keys_only() -> None:
    svc = _settings_service()
    desired = svc.build_desired(_ha_res(enabled=True, max_unacked_clients=4))
    assert desired == {"enabled": "1", "max_unacked_clients": "4"}


def test_build_desired_unknown_key_raises() -> None:
    with pytest.raises(InvalidConfigurationError, match="unknown key"):
        _settings_service().build_desired(_ha_res(bogus=1))


def test_live_ha_and_extract_live() -> None:
    svc = _settings_service()
    ha = svc.live_ha(_ha_response(enabled="1"))
    assert svc.extract_live(ha, ["enabled", "max_unacked_clients"]) == {
        "enabled": "1",
        "max_unacked_clients": "2",
    }
    with pytest.raises(APIError):
        svc.extract_live({"enabled": "1"}, ["max_unacked_clients"])


@pytest.mark.parametrize("response", [{}, {"dhcpv4": {}}, {"dhcpv4": {"ha": "x"}}, "junk"])
def test_live_ha_missing_section_raises(response: Any) -> None:
    with pytest.raises(APIError):
        _settings_service().live_ha(response)


def test_drift() -> None:
    svc = _settings_service()
    assert svc.drift({"enabled": "1"}, {"enabled": "1"}) is None
    assert svc.drift({"enabled": "0"}, {"enabled": "1"}) == {"enabled": "1"}


def test_build_set_payload_wraps_drops_display_and_overlays() -> None:
    svc = _settings_service()
    ha = svc.live_ha(_ha_response())
    payload = svc.build_set_payload(ha, {"enabled": "1"})
    assert payload == {
        "dhcpv4": {
            "ha": {"enabled": "1", "this_server_name": "", "max_unacked_clients": "2"},
        }
    }
    assert "general" not in payload["dhcpv4"]
    assert "lexpire" not in payload["dhcpv4"]


def test_set_settings_posts_and_raises_on_failure() -> None:
    svc = _settings_service({"result": "saved"}, {"result": "failed", "validations": {}})
    svc.set_settings({"dhcpv4": {"ha": {}}})
    call = svc.client.request.call_args_list[0]  # type: ignore[attr-defined]
    assert (call.args[0], call.args[1]) == ("POST", "kea/dhcpv4/set")
    with pytest.raises(APIError):
        svc.set_settings({"dhcpv4": {"ha": {}}})


def test_settings_export_emits_nested_singleton(tmp_path: Path) -> None:
    svc = _settings_service(_ha_response(enabled="1", this_server_name="fw-a"))
    text = svc.export_to_yaml()
    leaf = yaml.safe_load(text)["opnsense"]["kea"]["dhcp4"]["ha"]
    assert leaf == {"enabled": True, "this_server_name": "fw-a", "max_unacked_clients": 2}
    parsed = PackageLoader(tmp_path)._parse_nested_provider_format(
        yaml.safe_load(text)["opnsense"], "opnsense", "s.yaml"
    )
    assert [r.type for r in parsed] == ["kea.dhcp4.ha"]


# -- peers ------------------------------------------------------------------------


def _want(name: str, role: str = "primary", url: str = "http://192.0.2.1:8001/", **kw: Any) -> Any:
    return KeaHAPeerConfig(name=name, role=role, url=url, **kw)


def _live(uuid: str, name: str, role: str = "primary", url: str = "http://192.0.2.1:8001/") -> Any:
    return LiveKeaHAPeer(uuid=uuid, name=name, role=role, url=url)


def _peer_service(*responses: Any) -> KeaHAPeerService:
    client = MagicMock()
    client.request.side_effect = list(responses)
    return KeaHAPeerService(client)


def _peer_res(name: str, /, **config: Any) -> ResourceConfig:
    return ResourceConfig(name=name, type="kea.dhcp4.ha_peers", provider="opnsense", config=config)


def test_peer_payload_envelope() -> None:
    assert _want("fw-a").to_payload() == {
        "peer": {"name": "fw-a", "role": "primary", "url": "http://192.0.2.1:8001/"}
    }


def test_parser_accepts_and_rejects() -> None:
    (cfg,) = peer_configs_from_resources(
        [_peer_res("a", name="fw-a", role="standby", url="http://192.0.2.2:8001/", lock=True)]
    )
    assert (cfg.name, cfg.role, cfg.lock, cfg.diff_key) == ("fw-a", "standby", True, "fw-a")
    good = {"role": "primary", "url": "http://192.0.2.1:8001/"}
    for bad in (
        {**good, "uuid": "u"},
        {"url": "http://192.0.2.1:8001/"},
        {"role": "primary"},
        {**good, "role": "master"},
        {**good, "lock": "yes"},
        {**good, "name": ""},
    ):
        with pytest.raises(ValueError, match="kea ha peer 'a'"):
            peer_configs_from_resources([_peer_res("a", **bad)])


def test_parser_falls_back_to_resource_name() -> None:
    (cfg,) = peer_configs_from_resources(
        [_peer_res("fw-a", role="primary", url="http://192.0.2.1:8001/")]
    )
    assert cfg.name == "fw-a"


def test_search_flattens_option_role_from_get_peer() -> None:
    svc = _peer_service(
        {"rows": [{"uuid": "u1", "name": "fw-a", "role": "Primary"}, "junk"]},
        {
            "peer": {
                "name": "fw-a",
                "role": {"primary": {"value": "Primary", "selected": 1}, "standby": {}},
                "url": "http://192.0.2.1:8001/",
            }
        },
    )
    (row,) = svc.search()
    assert (row.uuid, row.name, row.role, row.url) == (
        "u1",
        "fw-a",
        "primary",
        "http://192.0.2.1:8001/",
    )
    calls = [(c.args[0], c.args[1]) for c in svc.client.request.call_args_list]  # type: ignore[attr-defined]
    assert calls == [("GET", "kea/dhcpv4/searchPeer"), ("GET", "kea/dhcpv4/getPeer/u1")]
    assert _peer_service({"unexpected": 1}).search() == []


def test_diff_add_update_noop() -> None:
    diff = compute_diff(
        [
            _want("new"),
            _want("same", "standby", "http://192.0.2.2:8001/"),
            _want("moved", "primary", "http://192.0.2.9:8001/"),
            _want("flip", "standby"),
        ],
        [
            _live("u1", "same", "standby", "http://192.0.2.2:8001/"),
            _live("u2", "moved"),
            _live("u3", "flip", "primary"),
        ],
    )
    assert [a.name for a in diff.adds] == ["new"]
    assert sorted(h.uuid for h, _ in diff.updates) == ["u2", "u3"]
    assert diff.deletes == []


def test_diff_deletes_managed_only() -> None:
    live = [_live("u1", "a"), _live("u2", "b")]
    diff = compute_diff([], live, managed_keys={"a"})
    assert [d.uuid for d in diff.deletes] == ["u1"]
    assert [d.uuid for d in diff.unmanaged] == ["u2"]


def test_diff_add_only_and_lock() -> None:
    live = [_live("u1", "a")]
    assert compute_diff([], live, add_only=True).deletes == []
    diff = compute_diff([_want("a", "standby", lock=True)], live)
    assert diff.is_empty
    assert len(diff.locked) == 1
    assert compute_diff([_want("a", lock=True)], [], managed_keys=set()).adds == []


def test_duplicate_live_names_raise() -> None:
    live = [_live("u1", "a"), _live("u2", "a")]
    with pytest.raises(OpnsenseDriftError):
        compute_diff([_want("a")], live)
    assert compute_diff([], live, managed_keys={"zzz"}).deletes == []


def test_calls_use_the_peer_endpoints() -> None:
    svc = _peer_service({"result": "saved"}, {"result": "saved"}, {"result": "deleted"})
    svc.add(_want("a"))
    svc.update("u1", _want("a"))
    svc.delete(_live("u1", "a"))
    calls = [(c.args[0], c.args[1]) for c in svc.client.request.call_args_list]  # type: ignore[attr-defined]
    assert calls == [
        ("POST", "kea/dhcpv4/addPeer"),
        ("POST", "kea/dhcpv4/setPeer/u1"),
        ("POST", "kea/dhcpv4/delPeer/u1"),
    ]


def test_delete_unexpected_reply_raises() -> None:
    with pytest.raises(APIError):
        _peer_service({"result": "nope"}).delete(_live("u1", "a"))


def test_add_failed_write_raises() -> None:
    with pytest.raises(APIError):
        _peer_service({"result": "failed", "validations": {}}).add(_want("a"))


def test_reconfigure_posts() -> None:
    svc = _peer_service({"status": "ok"})
    svc.reconfigure()
    call = svc.client.request.call_args_list[0]  # type: ignore[attr-defined]
    assert (call.args[0], call.args[1]) == ("POST", "kea/service/reconfigure")


def test_apply_diff_counts() -> None:
    svc = _peer_service({"result": "saved"}, {"result": "saved"}, {"result": "deleted"})
    diff = compute_diff(
        [_want("new"), _want("old", "standby")],
        [_live("u1", "old"), _live("u3", "gone")],
    )
    assert svc.apply_diff(diff) == {"created": 1, "updated": 1, "deleted": 1}


def test_export_handles_and_round_trip(tmp_path: Path) -> None:
    detail = {"peer": {"name": "FW A", "role": "primary", "url": "http://192.0.2.1:8001/"}}
    svc = _peer_service(
        {
            "rows": [
                {"uuid": "1", "name": "FW A"},
                {"uuid": "2", "name": "fw-a"},
                {"uuid": "3", "name": "taken"},
            ]
        },
        detail,
        {"peer": {"name": "fw-a", "role": "standby", "url": "http://192.0.2.2:8001/"}},
        {"peer": {"name": "taken", "role": "standby", "url": "http://192.0.2.3:8001/"}},
    )
    text = svc.export_to_yaml(reserved={"taken"})
    leaf = yaml.safe_load(text)["opnsense"]["kea"]["dhcp4"]["ha_peers"]
    assert [e["name"] for e in leaf] == ["fw-a", "fw-a-2", "taken-2"]
    assert leaf[0]["config"] == {
        "name": "FW A",
        "role": "primary",
        "url": "http://192.0.2.1:8001/",
    }
    parsed = PackageLoader(tmp_path)._parse_nested_provider_format(
        yaml.safe_load(text)["opnsense"], "opnsense", "s.yaml"
    )
    assert len(parsed) == 3
