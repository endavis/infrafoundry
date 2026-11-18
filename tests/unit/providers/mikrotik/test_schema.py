"""Tests for MikroTik schema checks and value normalization."""

from typing import Any

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.mikrotik.schema import (
    SPECS,
    check_resources,
    desired_from_resources,
    normalize_value,
    parse_vlan_ids,
    to_rest_value,
)

from .conftest import resource

VALID: list[ResourceConfig] = [
    resource("interface.bridge", "bridge", **{"vlan-filtering": True}),
    resource("interface.bridge.port", "p1", interface="ether1", bridge="bridge", pvid=10),
    resource(
        "interface.bridge.vlan",
        "v10",
        bridge="bridge",
        **{"vlan-ids": "10-12", "tagged": ["bridge", "ether4"]},
    ),
    resource("interface.vlan", "vlan99", interface="bridge", **{"vlan-id": 99}),
    resource("ip.address", "mgmt", address="192.0.2.2/24", interface="vlan99"),
    resource("ip.dhcp-client", "wan", interface="ether1"),
    resource("ip.service", "www-ssl", port=443),
]


def _messages(resources: list[ResourceConfig]) -> str:
    return "\n".join(f.message for f in check_resources(resources))


def test_all_seven_types_have_a_spec() -> None:
    assert set(SPECS) == {r.type for r in VALID}


@pytest.mark.parametrize("res", VALID, ids=lambda r: r.type)
def test_valid_config_accepted(res: ResourceConfig) -> None:
    assert check_resources([res]) == []


def test_name_defaults_to_resource_name() -> None:
    (obj,) = desired_from_resources([resource("interface.bridge", "bridge")])
    assert obj.key == ("bridge",)


@pytest.mark.parametrize(
    ("res", "needle"),
    [
        (resource("interface.bridge.port", "p", interface="ether1"), "bridge"),
        (resource("interface.vlan", "v", interface="bridge"), "vlan-id"),
        (resource("ip.address", "a", address="192.0.2.2/24"), "interface"),
        (resource("interface.bridge.vlan", "v", bridge="bridge"), "vlan-ids"),
    ],
)
def test_missing_required_field_rejected(res: ResourceConfig, needle: str) -> None:
    assert "missing required" in _messages([res])
    assert needle in _messages([res])


def test_unknown_field_rejected() -> None:
    assert "unknown field" in _messages([resource("interface.bridge", "b", bogus=1)])


@pytest.mark.parametrize("ids", ["0", "4095", "10-5000", "abc"])
def test_vlan_ids_out_of_range_rejected(ids: str) -> None:
    res = resource("interface.bridge.vlan", "v", bridge="bridge", **{"vlan-ids": ids})
    assert check_resources([res])


@pytest.mark.parametrize("pvid", [0, 4095])
def test_pvid_out_of_range_rejected(pvid: int) -> None:
    res = resource("interface.bridge.port", "p", interface="ether1", bridge="bridge", pvid=pvid)
    assert "pvid" in _messages([res])


def test_service_absent_rejected() -> None:
    assert "absent" in _messages([resource("ip.service", "www", absent=True)])


def test_absent_only_with_key_fields() -> None:
    ok = resource("ip.address", "old", address="192.168.88.1/24", absent=True)
    bad = resource("ip.address", "old", address="192.168.88.1/24", interface="bridge", absent=True)
    assert check_resources([ok]) == []
    assert "absent" in _messages([bad])


def test_duplicate_keys_rejected() -> None:
    a = resource("ip.address", "a", address="192.0.2.2/24", interface="x")
    b = resource("ip.address", "b", address="192.0.2.2/24", interface="y")
    assert "duplicate" in _messages([a, b])


def test_other_providers_types_are_skipped() -> None:
    other = ResourceConfig(name="x", type="vm", provider="proxmox", config={"junk": 1})
    assert check_resources([other]) == []
    assert desired_from_resources([other]) == []


def test_parse_vlan_ids() -> None:
    assert parse_vlan_ids("10,20-22") == {10, 20, 21, 22}
    assert parse_vlan_ids(10) == {10}
    assert parse_vlan_ids(["10", "12-13"]) == {10, 12, 13}


def test_bridge_vlan_key_expands_ranges() -> None:
    (a,) = desired_from_resources(
        [resource("interface.bridge.vlan", "a", bridge="b", **{"vlan-ids": "10-12"})]
    )
    (b,) = desired_from_resources(
        [resource("interface.bridge.vlan", "b", bridge="b", **{"vlan-ids": [10, 11, 12]})]
    )
    assert a.key == b.key


@pytest.mark.parametrize("raw", ["true", "yes", True, "True"])
def test_truthy_values_normalize_equal(raw: Any) -> None:
    assert normalize_value("bool", raw) is True


@pytest.mark.parametrize("raw", ["false", "no", False])
def test_falsy_values_normalize_equal(raw: Any) -> None:
    assert normalize_value("bool", raw) is False


def test_list_normalization_ignores_order() -> None:
    assert normalize_value("list", "b,a") == normalize_value("list", ["a", "b"])


def test_to_rest_value() -> None:
    assert to_rest_value("bool", True) == "yes"
    assert to_rest_value("list", ["b", "a"]) == "a,b"
    assert to_rest_value("int", 10) == "10"


def test_loader_copied_name_is_not_an_unknown_field() -> None:
    port = ResourceConfig(
        name="p1",
        type="interface.bridge.port",
        provider="mikrotik",
        config={"name": "p1", "interface": "ether1", "bridge": "b"},
    )
    assert check_resources([port]) == []
    (obj,) = desired_from_resources([port])
    assert "name" not in obj.fields
