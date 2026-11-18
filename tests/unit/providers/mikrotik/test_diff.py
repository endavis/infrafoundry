"""Tests for the pure MikroTik diff."""

from typing import Any

from infrafoundry.providers.mikrotik.components.diff import (
    CREATE,
    DELETE,
    UPDATE,
    compute_type_diff,
)
from infrafoundry.providers.mikrotik.schema import SPECS, desired_from_resources

from .conftest import resource


def _diff(
    type_name: str,
    declared: list[Any],
    live: list[dict[str, str]],
    *,
    add_only: bool = False,
    managed: set[Any] | None = None,
) -> Any:
    desired = desired_from_resources(declared)
    return compute_type_diff(
        SPECS[type_name], desired, live, add_only=add_only, managed_keys=managed
    )


def test_bridge_create_when_absent_from_live() -> None:
    diff = _diff("interface.bridge", [resource("interface.bridge", "br1")], [])
    assert [(c.kind, c.key) for c in diff.changes] == [(CREATE, ("br1",))]


def test_converged_bridge_plans_clean() -> None:
    live = [
        {".id": "*1", "name": "br1", "vlan-filtering": "true", "pvid": "1", "disabled": "false"}
    ]
    res = resource("interface.bridge", "br1", **{"vlan-filtering": True, "pvid": 1})
    assert _diff("interface.bridge", [res], live).is_empty


def test_port_pvid_update() -> None:
    live = [{".id": "*1", "interface": "ether1", "bridge": "br1", "pvid": "1"}]
    res = resource("interface.bridge.port", "p", interface="ether1", bridge="br1", pvid=20)
    (change,) = _diff("interface.bridge.port", [res], live).changes
    assert (change.kind, change.changed, change.live_id) == (UPDATE, ("pvid",), "*1")


def test_bridge_vlan_member_change_is_update() -> None:
    live = [{".id": "*1", "bridge": "br1", "vlan-ids": "10", "tagged": "br1", "untagged": ""}]
    res = resource(
        "interface.bridge.vlan",
        "v",
        bridge="br1",
        **{"vlan-ids": "10", "tagged": ["br1", "ether4"]},
    )
    (change,) = _diff("interface.bridge.vlan", [res], live).changes
    assert change.changed == ("tagged",)


def test_bridge_vlan_matched_by_expanded_range() -> None:
    live = [{".id": "*1", "bridge": "br1", "vlan-ids": "10,11,12", "tagged": "br1"}]
    res = resource("interface.bridge.vlan", "v", bridge="br1", **{"vlan-ids": "10-12"})
    assert _diff("interface.bridge.vlan", [res], live).is_empty


def test_interface_vlan_update_and_create() -> None:
    live = [{".id": "*1", "name": "vlan10", "interface": "br1", "vlan-id": "10"}]
    same = resource("interface.vlan", "vlan10", interface="br1", **{"vlan-id": 11})
    new = resource("interface.vlan", "vlan20", interface="br1", **{"vlan-id": 20})
    diff = _diff("interface.vlan", [same, new], live)
    assert [(c.kind, c.key[0]) for c in diff.changes] == [(UPDATE, "vlan10"), (CREATE, "vlan20")]


def test_address_moving_interface_is_update() -> None:
    live = [{".id": "*1", "address": "192.0.2.2/24", "interface": "bridge"}]
    res = resource("ip.address", "a", address="192.0.2.2/24", interface="vlan99")
    (change,) = _diff("ip.address", [res], live).changes
    assert (change.kind, change.changed) == (UPDATE, ("interface",))


def test_dhcp_client_create_and_converged() -> None:
    res = resource("ip.dhcp-client", "wan", interface="ether1", **{"use-peer-dns": False})
    assert [c.kind for c in _diff("ip.dhcp-client", [res], []).changes] == [CREATE]
    live = [{".id": "*1", "interface": "ether1", "use-peer-dns": "no", "disabled": "false"}]
    assert _diff("ip.dhcp-client", [res], live).is_empty


def test_service_update_never_create() -> None:
    res = resource("ip.service", "www", disabled=True)
    live = [{".id": "*1", "name": "www", "port": "80", "disabled": "false"}]
    (change,) = _diff("ip.service", [res], live).changes
    assert change.kind == UPDATE
    missing = _diff("ip.service", [res], [])
    assert missing.is_empty and missing.warnings


def test_dynamic_rows_ignored() -> None:
    live = [{".id": "*1", "address": "192.0.2.9/24", "interface": "ether1", "dynamic": "true"}]
    diff = _diff("ip.address", [], live, managed={("192.0.2.9/24",)})
    assert diff.is_empty and not diff.unmanaged


def test_undeclared_live_row_is_unmanaged_without_managed_set() -> None:
    live = [{".id": "*1", "address": "192.0.2.9/24", "interface": "ether1"}]
    diff = _diff("ip.address", [], live)
    assert diff.is_empty and diff.unmanaged == ["192.0.2.9/24"]


def test_managed_row_removed_from_yaml_is_deleted() -> None:
    live = [{".id": "*1", "address": "192.0.2.9/24", "interface": "ether1"}]
    (change,) = _diff("ip.address", [], live, managed={("192.0.2.9/24",)}).changes
    assert (change.kind, change.live_id) == (DELETE, "*1")


def test_add_only_suppresses_deletes() -> None:
    live = [{".id": "*1", "address": "192.0.2.9/24", "interface": "ether1"}]
    diff = _diff("ip.address", [], live, add_only=True, managed={("192.0.2.9/24",)})
    assert diff.is_empty and diff.unmanaged


def test_absent_true_deletes_factory_address() -> None:
    live = [{".id": "*30", "address": "192.168.88.1/24", "interface": "bridge"}]
    res = resource("ip.address", "factory", address="192.168.88.1/24", absent=True)
    (change,) = _diff("ip.address", [res], live).changes
    assert change.kind == DELETE and change.live_id == "*30"
    assert _diff("ip.address", [res], []).is_empty


def test_absent_is_suppressed_when_add_only() -> None:
    live = [{".id": "*30", "address": "192.168.88.1/24", "interface": "bridge"}]
    res = resource("ip.address", "factory", address="192.168.88.1/24", absent=True)
    assert _diff("ip.address", [res], live, add_only=True).is_empty


def test_builtin_row_never_deleted() -> None:
    live = [{".id": "*1", "name": "br0", "builtin": "true"}]
    assert _diff("interface.bridge", [], live, managed={("br0",)}).is_empty
