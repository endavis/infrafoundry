"""Unit tests for SDNConfigValidator (#1137)."""

from typing import Any

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationReport
from infrafoundry.providers.proxmox.validators import SDNConfigValidator

PEERS = ["192.168.10.100", "192.168.10.101"]


def _zone(name: str = "nettest", **config: Any) -> ResourceConfig:
    return ResourceConfig(
        name=name, type="sdn_zone", provider="proxmox", config={"peers": PEERS, **config}
    )


def _vnet(name: str = "ntlan", **config: Any) -> ResourceConfig:
    return ResourceConfig(
        name=name,
        type="sdn_vnet",
        provider="proxmox",
        config={"zone": "nettest", "tag": 9900, **config},
    )


def _errors(zones: list[ResourceConfig], vnets: list[ResourceConfig]) -> list[str]:
    report = ValidationReport()
    SDNConfigValidator(report).validate(zones, vnets)
    return [r.check_name for r in report.results if not r.passed]


def test_valid_zone_and_vnet() -> None:
    assert _errors([_zone(mtu=8950)], [_vnet()]) == []


@pytest.mark.parametrize("bad_id", ["NetTest", "1zone", "toolongid", "net-test", ""])
def test_ids_must_be_short_lowercase_alphanumeric(bad_id: str) -> None:
    zone = _zone("z", id=bad_id) if bad_id else _zone("Bad")
    assert _errors([zone], []) == [f"proxmox_sdn_zone_{zone.name}_id"]


def test_config_id_fixes_an_invalid_name() -> None:
    assert _errors([_zone("netapp-test", id="nettest")], []) == []


def test_unsupported_kind() -> None:
    assert _errors([_zone(kind="evpn")], []) == ["proxmox_sdn_zone_nettest_kind"]


@pytest.mark.parametrize("peers", [None, [], "192.168.10.100"])
def test_vxlan_zone_needs_peers(peers: Any) -> None:
    zone = ResourceConfig(name="nettest", type="sdn_zone", provider="proxmox", config={})
    if peers is not None:
        zone.config["peers"] = peers
    assert _errors([zone], []) == ["proxmox_sdn_zone_nettest_peers"]


def test_peers_must_be_ip_addresses() -> None:
    assert _errors([_zone(peers=["pve1.endavis.net"])], []) == [
        "proxmox_sdn_zone_nettest_peer_pve1.endavis.net"
    ]


@pytest.mark.parametrize("mtu", [0, -1, "8950", True])
def test_mtu_must_be_a_positive_integer(mtu: Any) -> None:
    assert _errors([_zone(mtu=mtu)], []) == ["proxmox_sdn_zone_nettest_mtu"]


def test_vnet_zone_must_be_declared() -> None:
    assert _errors([_zone()], [_vnet(zone="other")]) == ["proxmox_sdn_vnet_ntlan_zone"]


def test_vnet_may_name_its_zone_by_id() -> None:
    assert _errors([_zone("netapp", id="nettest")], [_vnet(zone="nettest")]) == []


@pytest.mark.parametrize("tag", [None, 0, 16_777_216, "9900", True])
def test_vxlan_vnet_needs_a_valid_tag(tag: Any) -> None:
    vnet = _vnet()
    if tag is None:
        del vnet.config["tag"]
    else:
        vnet.config["tag"] = tag
    assert _errors([_zone()], [vnet]) == ["proxmox_sdn_vnet_ntlan_tag"]


def test_vxlan_tags_are_unique() -> None:
    assert _errors([_zone()], [_vnet("a"), _vnet("b")]) == ["proxmox_sdn_vnet_b_tag_duplicate"]
