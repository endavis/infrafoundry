"""Unit tests for ``InterfacesSettingsService`` (#1092)."""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import MagicMock

import pytest
import yaml

from infrafoundry.core.exceptions import APIError, InvalidConfigurationError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense import endpoints
from infrafoundry.providers.opnsense.services.interfaces_settings import (
    DEFAULTS,
    FIELD_MAP,
    InterfacesSettingsService,
    _flatten,
)


def _vlan(selected: str) -> dict[str, Any]:
    return {
        key: {"value": label, "selected": 1 if key == selected else 0}
        for key, label in (("0", "Enable"), ("1", "Disable"), ("2", "Leave default"))
    }


def _live(**overrides: Any) -> dict[str, Any]:
    """Live settings object holding the model defaults."""
    live: dict[str, Any] = {
        "disablechecksumoffloading": "1",
        "disablesegmentationoffloading": "1",
        "disablelargereceiveoffloading": "1",
        "disablevlanhwfilter": _vlan("2"),
        "disableipv6": "0",
        "dhcp6_norelease": "0",
        "dhcp6_debug": "0",
        "dhcp6_duid": "",
        "dhcp6_ratimeout": "10",
    }
    live.update(overrides)
    return live


def _svc(response: Any = None) -> InterfacesSettingsService:
    service = InterfacesSettingsService(MagicMock())
    service.client = MagicMock()
    service.client.request.return_value = response
    return service


def _req(svc: InterfacesSettingsService) -> MagicMock:
    mock: MagicMock = svc.client.request  # type: ignore[assignment]
    return mock


def _res(config: dict[str, Any]) -> ResourceConfig:
    return ResourceConfig(
        name="interfaces.settings",
        type="interfaces.settings",
        provider="opnsense",
        config=config,
    )


def test_defaults_cover_every_field() -> None:
    assert set(DEFAULTS) == set(FIELD_MAP)


def test_build_desired_maps_each_type() -> None:
    desired = _svc().build_desired(
        _res(
            {
                "disable_checksum_offloading": False,
                "dhcp6_debug": True,
                "vlan_hardware_filtering": "disable",
                "dhcp6_duid": "  00:01  ",
                "dhcp6_ra_timeout": 20,
            }
        )
    )
    assert desired == {
        "disable_checksum_offloading": "0",
        "vlan_hardware_filtering": "1",
        "dhcp6_debug": "1",
        "dhcp6_duid": "00:01",
        "dhcp6_ra_timeout": "20",
    }


@pytest.mark.parametrize(("value", "wire"), [("enable", "0"), ("disable", "1"), ("default", "2")])
def test_build_desired_vlan_filter_values(value: str, wire: str) -> None:
    desired = _svc().build_desired(_res({"vlan_hardware_filtering": value}))
    assert desired == {"vlan_hardware_filtering": wire}


def test_build_desired_empty_config_is_empty() -> None:
    assert _svc().build_desired(_res({})) == {}


@pytest.mark.parametrize(
    "config",
    [
        {"nope": True},
        {"dhcp6_debug": "yes"},
        {"dhcp6_debug": 1},
        {"vlan_hardware_filtering": "maybe"},
        {"vlan_hardware_filtering": 1},
        {"dhcp6_duid": 5},
        {"dhcp6_ra_timeout": "10"},
        {"dhcp6_ra_timeout": True},
        {"dhcp6_ra_timeout": -1},
    ],
)
def test_build_desired_rejects_bad_input(config: dict[str, Any]) -> None:
    with pytest.raises(InvalidConfigurationError):
        _svc().build_desired(_res(config))


def test_flatten() -> None:
    assert _flatten(_vlan("1")) == "1"
    assert _flatten("1") == "1"
    assert _flatten(None) == ""
    assert _flatten([]) == ""
    assert _flatten(10) == "10"


def test_extract_live_flattens_options_and_passes_strings() -> None:
    live = _svc().extract_live(
        _live(disablevlanhwfilter=_vlan("1")), ["vlan_hardware_filtering", "dhcp6_ra_timeout"]
    )
    assert live == {"vlan_hardware_filtering": "1", "dhcp6_ra_timeout": "10"}


def test_extract_live_missing_declared_field_raises() -> None:
    settings = _live()
    del settings["dhcp6_debug"]
    with pytest.raises(APIError, match="dhcp6_debug"):
        _svc().extract_live(settings, ["dhcp6_debug"])


def test_live_settings_missing_envelope_raises() -> None:
    with pytest.raises(APIError):
        _svc().live_settings({"other": {}})
    with pytest.raises(APIError):
        _svc().live_settings(None)
    assert _svc().live_settings({"settings": {"a": "1"}}) == {"a": "1"}


def test_drift_equal_declared_difference_and_undeclared_ignored() -> None:
    svc = _svc()
    live = svc.extract_live(_live(), list(FIELD_MAP))
    assert svc.drift(live, {"dhcp6_debug": "0"}) is None
    assert svc.drift(live, {}) is None
    desired = {"dhcp6_debug": "1"}
    assert svc.drift(live, desired) == desired
    # an undeclared difference does not count
    live["disable_ipv6"] = "1"
    assert svc.drift(live, {"dhcp6_debug": "0"}) is None


def test_build_set_payload_keeps_live_keys_and_overwrites_declared() -> None:
    payload = _svc().build_set_payload(
        _live(extra="x"), {"vlan_hardware_filtering": "1", "dhcp6_debug": "1"}
    )
    flat = payload["settings"]
    assert flat["disablevlanhwfilter"] == "1"
    assert flat["dhcp6_debug"] == "1"
    assert flat["disablechecksumoffloading"] == "1"
    assert flat["dhcp6_ratimeout"] == "10"
    assert flat["extra"] == "x"
    assert set(payload) == {"settings"}


def test_get_settings_uses_the_get_endpoint() -> None:
    svc = _svc({"settings": {}})
    assert svc.get_settings() == {"settings": {}}
    _req(svc).assert_called_once_with(
        endpoints.INTERFACES_SETTINGS_GET.method, endpoints.INTERFACES_SETTINGS_GET.path()
    )


def test_set_settings_posts_payload_and_raises_on_failure() -> None:
    svc = _svc({"result": "saved"})
    svc.set_settings({"settings": {"a": "1"}})
    _req(svc).assert_called_once_with(
        endpoints.INTERFACES_SETTINGS_SET.method,
        endpoints.INTERFACES_SETTINGS_SET.path(),
        data={"settings": {"a": "1"}},
    )
    with pytest.raises(APIError):
        _svc({"result": "failed", "validations": {"x": "bad"}}).set_settings({})


def test_reconfigure_posts_and_raises_on_failure() -> None:
    svc = _svc({"status": "ok"})
    svc.reconfigure()
    _req(svc).assert_called_once_with(
        endpoints.INTERFACES_SETTINGS_RECONFIGURE.method,
        endpoints.INTERFACES_SETTINGS_RECONFIGURE.path(),
    )
    with pytest.raises(APIError):
        _svc({"result": "failed"}).reconfigure()


def _export(settings: dict[str, Any]) -> dict[str, Any]:
    text = _svc({"settings": settings}).export_to_yaml()
    return yaml.safe_load(text)  # type: ignore[no-any-return]


def test_export_emits_only_non_default_fields() -> None:
    doc = _export(_live(disablevlanhwfilter=_vlan("1"), dhcp6_debug="1"))
    assert doc == {
        "opnsense": {
            "interfaces": {"settings": {"vlan_hardware_filtering": "disable", "dhcp6_debug": True}}
        }
    }


def test_export_all_default_emits_empty_mapping() -> None:
    doc = _export(_live())
    assert doc["opnsense"]["interfaces"]["settings"] == {}


def test_export_unknown_vlan_option_is_skipped_with_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        doc = _export(_live(disablevlanhwfilter="7", dhcp6_ratimeout="30"))
    assert doc["opnsense"]["interfaces"]["settings"] == {"dhcp6_ra_timeout": 30}
    assert "disablevlanhwfilter" in caplog.text


def test_export_skips_non_integer_timeout_and_keeps_text_fields(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        doc = _export(_live(dhcp6_ratimeout="abc", dhcp6_duid="00:01"))
    assert doc["opnsense"]["interfaces"]["settings"] == {"dhcp6_duid": "00:01"}
    assert "dhcp6_ra_timeout" in caplog.text
