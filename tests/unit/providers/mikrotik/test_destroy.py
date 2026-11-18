"""Tests for MikroTikManager.plan_destroy and destroy against the in-memory fake device."""

import pytest

from infrafoundry.core.provider import ResourceConfig

from .conftest import FakeRouterOS, converged_wan_edge, manager_for, resource


def _subset(*names: str) -> list[ResourceConfig]:
    return [r for r in converged_wan_edge() if r.name in names]


def test_deletes_run_in_the_planned_order(
    wan_edge: FakeRouterOS, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager = manager_for(wan_edge, monkeypatch)

    result = manager.destroy("test", _subset("p2", "p3", "v10", "v20"))

    assert result.success
    # Ports on the management bridge are management steps and sort last in phase E.
    assert [w[1] for w in wan_edge.writes()] == [
        "interface/bridge/vlan/*20",
        "interface/bridge/vlan/*21",
        "interface/bridge/port/*11",
        "interface/bridge/port/*12",
    ]
    assert [s.phase for s in result.completed] == ["E"] * 4
    assert result.counts == {"create": 0, "update": 0, "delete": 4}
    assert sorted(o.resource_name for o in result.outcomes) == ["p2", "p3", "v10", "v20"]
    assert result.released == []


def test_services_absent_undeclared_builtin_and_dynamic_rows_are_kept(
    wan_edge: FakeRouterOS, monkeypatch: pytest.MonkeyPatch
) -> None:
    wan_edge.tables["interface/vlan"].append(
        {".id": "*8", "name": "vlan5", "interface": "bridge", "vlan-id": "5", "builtin": "true"}
    )
    resources = [
        *_subset("p2", "www-ssl"),
        resource("ip.address", "old", address="192.0.2.2/24", interface="vlan99", absent=True),
        resource("interface.vlan", "vlan5", interface="bridge", **{"vlan-id": 5}),
        resource("interface.bridge.vlan", "dyn", bridge="bridge", **{"vlan-ids": 1}),
    ]
    manager = manager_for(wan_edge, monkeypatch)

    result = manager.destroy("test", resources)

    assert result.success
    assert [w[1] for w in wan_edge.writes()] == ["interface/bridge/port/*11"]
    ports = {r["interface"] for r in wan_edge.tables["interface/bridge/port"]}
    assert ports == {"ether1", "ether3", "ether4"}


def test_destroying_the_management_path_is_refused_before_any_write(
    wan_edge: FakeRouterOS, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager = manager_for(wan_edge, monkeypatch)

    result = manager.destroy("test", converged_wan_edge())

    assert not result.success
    assert result.refusals and "management address" in result.refusals[0]
    assert wan_edge.writes() == []


def test_target_resources_narrow_the_deletes(
    wan_edge: FakeRouterOS, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager = manager_for(wan_edge, monkeypatch)

    result = manager.destroy("test", _subset("p2", "p3", "v10"), target_resources=["v10"])

    assert result.success
    assert [w[1] for w in wan_edge.writes()] == ["interface/bridge/vlan/*20"]


def test_declared_objects_missing_from_the_device_are_not_deleted(
    wan_edge: FakeRouterOS, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager = manager_for(wan_edge, monkeypatch)

    result = manager.destroy(
        "test", [resource("interface.vlan", "vlan7", interface="bridge", **{"vlan-id": 7})]
    )

    assert result.success and result.completed == [] and wan_edge.writes() == []


def test_resource_ids_map_declared_names_to_row_ids(
    wan_edge: FakeRouterOS, monkeypatch: pytest.MonkeyPatch
) -> None:
    resources = [
        *_subset("p2", "v10"),
        resource("interface.vlan", "vlan7", interface="bridge", **{"vlan-id": 7}),
    ]

    ids = manager_for(wan_edge, monkeypatch).resource_ids("test", resources)

    assert ids == {"p2": "*11", "v10": "*20"}


def test_dependents_are_deleted_before_their_parent(
    wan_edge: FakeRouterOS, monkeypatch: pytest.MonkeyPatch
) -> None:
    wan_edge.tables["interface/bridge"].append(
        {".id": "*50", "name": "br2", "vlan-filtering": "false"}
    )
    wan_edge.tables["interface/vlan"].append(
        {".id": "*51", "name": "vlan50", "interface": "br2", "vlan-id": "50"}
    )
    resources = [
        resource("interface.bridge", "br2"),
        resource("interface.vlan", "vlan50", interface="br2", **{"vlan-id": 50}),
    ]

    result = manager_for(wan_edge, monkeypatch).destroy("test", resources)

    assert result.success
    assert [w[1] for w in wan_edge.writes()] == ["interface/vlan/*51", "interface/bridge/*50"]
