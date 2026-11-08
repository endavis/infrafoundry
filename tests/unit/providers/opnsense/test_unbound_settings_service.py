"""Unit tests for ``UnboundSettingsService`` (#1091)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
import yaml

from infrafoundry.core.config.package_loader import PackageLoader
from infrafoundry.core.exceptions import APIError, InvalidConfigurationError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.services.unbound_advanced import FIELD_MAP
from infrafoundry.providers.opnsense.services.unbound_settings import (
    SECTIONS,
    UnboundSettingsService,
    check_config,
)

DOCS_EXAMPLE = """\
opnsense:
  unbound:
    settings:
      general:
        enabled: true
        regdhcp: true
        regdhcpstatic: true
        local_zone_type: transparent
      advanced:
        hideidentity: true
        prefetch: true
"""

LIVE: dict[str, Any] = {
    "unbound": {
        "general": {
            "enabled": "1",
            "port": "53",
            "dns64prefix": "",
            "regdhcpdomain": "",
            "local_zone_type": {
                "transparent": {"value": "transparent", "selected": 1},
                "deny": {"value": "deny", "selected": 0},
            },
            "active_interface": {
                "lan": {"value": "LAN", "selected": 1},
                "opt1": {"value": "OPT", "selected": 1},
                "wan": {"value": "WAN", "selected": 0},
            },
            "outgoing_interface": {"": {"value": "All", "selected": 1}},
        },
        "advanced": {
            "hideidentity": "0",
            "logverbosity": [
                {"value": "Level 0", "selected": 0},
                {"value": "Level 1", "selected": 1},
            ],
            "cachemaxttl": "86400",
            "privateaddress": {"10.0.0.0/8": {"selected": 1}},
        },
    }
}


def _resource(config: dict[str, Any]) -> ResourceConfig:
    return ResourceConfig(
        name="unbound.settings", type="unbound.settings", provider="opnsense", config=config
    )


def _service(response: Any = None) -> UnboundSettingsService:
    service = UnboundSettingsService(MagicMock())
    client = MagicMock()
    client.request.return_value = response
    service.client = client
    return service


@pytest.mark.parametrize(
    "config",
    [
        {"bogus": {}},
        {"general": ["enabled"]},
        {"general": {"nope": True}},
        {"advanced": {"privatedomain": ["a.example"]}},
        {"advanced": {"private_addresses": ["10.0.0.0/8"]}},
        {"advanced": {"insecure_domains": []}},
        {"general": {"enabled": "yes"}},
        {"general": {"enabled": 1}},
        {"general": {"port": 0}},
        {"general": {"port": 70000}},
        {"general": {"port": True}},
        {"general": {"local_zone_type": "bogus"}},
        {"advanced": {"logverbosity": 6}},
        {"advanced": {"valloglevel": -1}},
        {"general": {"active_interface": "lan"}},
        {"general": {"active_interface": ["lan wan"]}},
        {"general": {"outgoing_interface": [""]}},
        {"general": {"dns64prefix": "not-a-prefix"}},
        {"general": {"regdhcpdomain": "has space"}},
        {"advanced": {"cachemaxttl": -1}},
        {"advanced": {"cachemaxttl": True}},
        {"advanced": {"msgcachesize": "4 MB"}},
        {"advanced": {"msgcachesize": "4,5"}},
    ],
)
def test_invalid_configs_are_rejected(config: dict[str, Any]) -> None:
    assert check_config(config)
    with pytest.raises(InvalidConfigurationError):
        _service().build_desired(_resource(config))


def test_owned_field_error_names_the_advanced_key() -> None:
    (_, message), *_ = check_config({"advanced": {"privateaddress": []}})
    assert "unbound.advanced" in message
    assert "private_addresses" in message


def test_owned_fields_are_not_in_sections() -> None:
    all_wires = {wire for fields in SECTIONS.values() for wire in fields}
    assert not all_wires & set(FIELD_MAP.values())


def test_valid_config_has_no_problems() -> None:
    config = {
        "general": {
            "enabled": True,
            "port": 5353,
            "local_zone_type": "static",
            "active_interface": ["lan"],
            "dns64prefix": "64:ff9b::/96",
            "regdhcpdomain": "lan.example.com",
        },
        "advanced": {"logverbosity": 5, "valloglevel": 0, "cachemaxttl": 10, "msgcachesize": "4m"},
    }
    assert check_config(config) == []


def test_build_desired_maps_values() -> None:
    desired = _service().build_desired(
        _resource(
            {
                "general": {
                    "enabled": False,
                    "port": 5353,
                    "active_interface": ["lan", "opt1", "lan"],
                },
                "advanced": {"logverbosity": 2, "msgcachesize": "4m"},
            }
        )
    )
    assert desired == {
        "general": {
            "enabled": "0",
            "port": "5353",
            "active_interface": frozenset({"lan", "opt1"}),
        },
        "advanced": {"logverbosity": "2", "msgcachesize": "4m"},
    }


def test_build_desired_empty_section_yields_nothing() -> None:
    assert _service().build_desired(_resource({"general": {}, "advanced": {}})) == {}
    assert _service().build_desired(_resource({})) == {}


def test_live_sections_missing_section_raises() -> None:
    with pytest.raises(APIError):
        _service().live_sections({"unbound": {"general": {}}}, ["advanced"])
    with pytest.raises(APIError):
        _service().live_sections("nope", ["general"])


def test_extract_live_flattens_each_kind() -> None:
    desired: Any = {
        "general": {
            "enabled": "1",
            "local_zone_type": "x",
            "active_interface": frozenset(),
            "outgoing_interface": frozenset(),
        },
        "advanced": {"logverbosity": "1"},
    }
    live = _service().extract_live(LIVE["unbound"], desired)
    assert live == {
        "general": {
            "enabled": "1",
            "local_zone_type": "transparent",
            "active_interface": frozenset({"lan", "opt1"}),
            "outgoing_interface": frozenset(),
        },
        "advanced": {"logverbosity": "1"},
    }


def test_extract_live_absent_field_raises() -> None:
    with pytest.raises(APIError):
        _service().extract_live(LIVE["unbound"], {"advanced": {"prefetch": "1"}})


def test_drift_in_sync_is_none_and_ignores_list_order() -> None:
    service = _service()
    desired = service.build_desired(
        _resource({"general": {"enabled": True, "active_interface": ["opt1", "lan"]}})
    )
    live = service.extract_live(LIVE["unbound"], desired)
    assert service.drift(live, desired) is None


def test_drift_single_change_returns_desired() -> None:
    service = _service()
    desired = service.build_desired(_resource({"advanced": {"hideidentity": True}}))
    live = service.extract_live(LIVE["unbound"], desired)
    assert service.drift(live, desired) == desired


def test_build_set_payload_echoes_live_and_overwrites_declared() -> None:
    service = _service()
    desired = service.build_desired(
        _resource({"advanced": {"hideidentity": True, "cachemaxttl": 3600}})
    )
    payload = service.build_set_payload(LIVE["unbound"], desired)
    assert set(payload["unbound"]) == {"advanced"}
    flat = payload["unbound"]["advanced"]
    assert flat["hideidentity"] == "1"
    assert flat["cachemaxttl"] == "3600"
    assert flat["logverbosity"] == "1"
    assert flat["privateaddress"] == "10.0.0.0/8"


def test_build_set_payload_writes_multi_select_as_sorted_csv() -> None:
    service = _service()
    desired = service.build_desired(_resource({"general": {"active_interface": ["wan", "lan"]}}))
    payload = service.build_set_payload(LIVE["unbound"], desired)
    assert payload["unbound"]["general"]["active_interface"] == "lan,wan"
    assert payload["unbound"]["general"]["port"] == "53"


def test_set_settings_raises_on_failure() -> None:
    service = _service({"result": "failed"})
    with pytest.raises(APIError):
        service.set_settings({"unbound": {}})


def test_export_to_yaml_shape_and_round_trip(tmp_path: Path) -> None:
    service = _service(LIVE)
    text = service.export_to_yaml()
    config = yaml.safe_load(text)["opnsense"]["unbound"]["settings"]
    assert config == {
        "general": {
            "enabled": True,
            "port": 53,
            "local_zone_type": "transparent",
            "active_interface": ["lan", "opt1"],
        },
        "advanced": {"hideidentity": False, "logverbosity": 1, "cachemaxttl": 86400},
    }
    assert "privateaddress" not in text
    resources = PackageLoader(tmp_path)._parse_resources_from_data(
        yaml.safe_load(text), "x.yaml", "opnsense"
    )
    assert check_config(resources[0].config) == []


def test_export_with_nothing_present_is_empty_mapping() -> None:
    service = _service({"unbound": {"general": {}, "advanced": {}}})
    assert yaml.safe_load(service.export_to_yaml())["opnsense"]["unbound"]["settings"] == {}


def test_docs_example_parses_through_the_real_loader(tmp_path: Path) -> None:
    resources = PackageLoader(tmp_path)._parse_resources_from_data(
        yaml.safe_load(DOCS_EXAMPLE), "doc.yaml", "opnsense"
    )
    (resource,) = resources
    assert resource.type == "unbound.settings"
    assert check_config(resource.config) == []
    assert _service().build_desired(resource)["general"]["local_zone_type"] == "transparent"
