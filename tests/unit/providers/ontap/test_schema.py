"""ONTAP schema: netmask forms, protocols, identity and the field checks."""

from __future__ import annotations

from typing import Any

import pytest

from infrafoundry.providers.ontap.schema import (
    check_resources,
    desired_from_resources,
    live_view,
    normalize_netmask,
    policy_for_protocols,
    to_api_kwargs,
)

from .conftest import lif, record

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("value", [24, "24", "/24", "255.255.255.0"])
def test_netmask_forms_compare_equal(value: Any) -> None:
    assert normalize_netmask(value) == 24


@pytest.mark.parametrize("value", ["255.0.255.0", "abc", True, 129, -1, "1.2.3"])
def test_bad_netmask_is_rejected(value: Any) -> None:
    with pytest.raises(ValueError, match="netmask"):
        normalize_netmask(value)


@pytest.mark.parametrize(
    ("protocols", "policy"),
    [
        (["nfs"], "default-data-files"),
        (["NFS", "cifs"], "default-data-files"),
        (["iscsi"], "default-data-blocks"),
        (["nvme-tcp"], "default-data-blocks"),
    ],
)
def test_protocols_map_to_a_policy(protocols: list[str], policy: str) -> None:
    assert policy_for_protocols(protocols) == policy


def test_mixed_protocols_are_an_error() -> None:
    with pytest.raises(ValueError, match="mixes file"):
        policy_for_protocols(["nfs", "iscsi"])


def test_unknown_and_empty_protocols_are_errors() -> None:
    with pytest.raises(ValueError, match="unknown protocol"):
        policy_for_protocols(["ftp"])
    with pytest.raises(ValueError, match="non-empty"):
        policy_for_protocols([])


def _messages(*resources: Any) -> list[str]:
    return [f.message for f in check_resources(list(resources))]


def test_valid_resource_has_no_findings() -> None:
    assert _messages(lif()) == []


def test_protocols_become_the_service_policy() -> None:
    [obj] = desired_from_resources([lif(service_policy=None, protocols=["nfs", "cifs"])])
    assert obj.fields["service_policy"] == "default-data-files"


def test_both_policy_and_protocols_is_an_error() -> None:
    assert any("not both" in m for m in _messages(lif(protocols=["nfs"])))


def test_mixed_protocols_are_a_finding() -> None:
    mixed = lif(service_policy=None, protocols=["nfs", "iscsi"])
    assert any("mixes" in m for m in _messages(mixed))


def test_unknown_key_is_a_finding() -> None:
    assert any("unknown field(s): vlan" in m for m in _messages(lif(vlan=5)))


@pytest.mark.parametrize("missing", ["svm", "address", "netmask", "home_node", "home_port"])
def test_required_fields_are_checked(missing: str) -> None:
    assert any(missing in m and "missing" in m for m in _messages(lif(**{missing: None})))


def test_name_defaults_to_the_resource_name() -> None:
    [obj] = desired_from_resources([lif("nfs-a")])
    assert obj.name == "nfs-a" and obj.key == ("svm1", "nfs-a")
    [named] = desired_from_resources([lif("nfs-a", name="data1")])
    assert named.key == ("svm1", "data1")


def test_bad_values_are_findings() -> None:
    assert any("not an IP address" in m for m in _messages(lif(address="host")))
    assert any("too long" in m for m in _messages(lif(netmask=64)))
    assert any("auto_revert" in m for m in _messages(lif(auto_revert="yes")))


def test_duplicate_identity_is_a_finding() -> None:
    assert any("duplicate" in m for m in _messages(lif("a", name="x"), lif("b", name="x")))
    assert _messages(lif("a", name="x"), lif("b", name="x", svm="svm2")) == []


def test_absent_carries_only_the_key() -> None:
    absent = lif(
        "old",
        absent=True,
        address=None,
        netmask=None,
        home_node=None,
        home_port=None,
        service_policy=None,
    )
    assert _messages(absent) == []
    assert any("absent" in m for m in _messages(lif("old", absent=True)))


def test_api_kwargs_send_the_port_with_its_node() -> None:
    kwargs = to_api_kwargs(
        {"home_node": "cluster1-01", "home_port": "e0d", "netmask": 24, "auto_revert": True}
    )
    assert kwargs == {
        "location.home_node.name": "cluster1-01",
        "location.home_port.name": "e0d",
        "location.home_port.node.name": "cluster1-01",
        "ip.netmask": "24",
        "location.auto_revert": True,
    }


def test_live_view_normalizes() -> None:
    view = live_view(record(netmask="255.255.255.0", address="192.0.2.010".replace("010", "10")))
    assert view["netmask"] == 24 and view["address"] == "192.0.2.10"
    assert view["svm"] == "svm1" and view["home_port"] == "e0d" and view["is_home"] is True
    assert live_view({})["netmask"] is None
