"""Tests for MikroTikManager.apply against the in-memory fake device."""

from typing import Any

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.mikrotik.client import RouterOSAPIError, RouterOSConnectionError

from .conftest import FakeRouterOS, converged_wan_edge, manager_for, resource

BVLAN = "interface.bridge.vlan"


def _named(name: str) -> ResourceConfig:
    return next(r for r in converged_wan_edge() if r.name == name)


def _without(*names: str) -> list[ResourceConfig]:
    return [r for r in converged_wan_edge() if r.name not in names]


def test_factory_default_to_wan_edge_layout(
    factory: FakeRouterOS, monkeypatch: pytest.MonkeyPatch
) -> None:
    resources = converged_wan_edge()
    resources.append(resource("ip.address", "factory", address="192.168.88.1/24", absent=True))
    manager = manager_for(factory, monkeypatch)

    result = manager.apply("test", manager.plan("test", resources))

    assert result.success and result.failed is None
    writes = factory.writes()
    paths = [w[1] for w in writes]
    last_b = max(i for i, p in enumerate(paths) if w_phase(writes[i]) == "B")
    first_c = next(i for i, w in enumerate(writes) if w_phase(w) == "C")
    assert last_b < first_c
    assert paths[-1] != "ip/service"
    assert all(a["address"] != "192.168.88.1/24" for a in factory.tables["ip/address"])
    assert not manager.plan("test", resources).has_changes


def w_phase(write: tuple[Any, ...]) -> str:
    """Classify a write: ``C`` is the PATCH that turns bridge filtering on."""
    if write[0] == "PATCH" and write[2] == {"vlan-filtering": "yes"}:
        return "C"
    return "B" if write[0] == "PUT" or write[1].startswith("interface/bridge/port") else "other"


def test_refused_plan_writes_nothing(
    wan_edge: FakeRouterOS, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager = manager_for(wan_edge, monkeypatch)
    plan = manager.plan(
        "test", _without("mgmt"), managed_resources={"ip.address": [_named("mgmt")]}
    )
    assert plan.refusals

    result = manager.apply("test", plan)

    assert not result.success
    assert result.refusals == plan.refusals
    assert wan_edge.writes() == []


def test_managed_row_left_out_of_yaml_is_deleted_and_released(
    wan_edge: FakeRouterOS, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager = manager_for(wan_edge, monkeypatch)
    plan = manager.plan("test", _without("v10", "v20"), managed_resources={BVLAN: [_named("v10")]})

    result = manager.apply("test", plan)

    assert result.success
    assert wan_edge.writes() == [("DELETE", "interface/bridge/vlan/*20")]
    assert [(o.action, o.resource_name) for o in result.outcomes] == [("delete", "v10")]
    assert result.outcomes[0].address == "mikrotik_interface_bridge_vlan.v10"
    assert result.released == [{"resource_type": BVLAN, "name": "v10"}]
    assert any(r[".id"] == "*21" for r in wan_edge.tables["interface/bridge/vlan"])


def test_add_only_run_deletes_and_releases_nothing(
    wan_edge: FakeRouterOS, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager = manager_for(wan_edge, monkeypatch)
    plan = manager.plan(
        "test", _without("v10"), add_only=True, managed_resources={BVLAN: [_named("v10")]}
    )

    result = manager.apply("test", plan)

    assert result.success and result.released == []
    assert wan_edge.writes() == []


def test_targeted_run_deletes_and_releases_nothing(
    wan_edge: FakeRouterOS, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager = manager_for(wan_edge, monkeypatch)
    plan = manager.plan(
        "test",
        _without("v10"),
        target_resources=["p2"],
        managed_resources={BVLAN: [_named("v10")]},
    )

    result = manager.apply("test", plan)

    assert result.success and result.released == []
    assert not [w for w in wan_edge.writes() if w[0] == "DELETE"]


def test_unparseable_managed_row_is_neither_deleted_nor_released(
    wan_edge: FakeRouterOS, monkeypatch: pytest.MonkeyPatch
) -> None:
    broken = resource(BVLAN, "old", bridge="bridge")
    manager = manager_for(wan_edge, monkeypatch)
    plan = manager.plan("test", converged_wan_edge(), managed_resources={BVLAN: [broken]})

    result = manager.apply("test", plan)

    assert result.success and result.released == []
    assert wan_edge.writes() == []


def test_created_filtering_bridge_is_one_create_outcome(
    wan_edge: FakeRouterOS, monkeypatch: pytest.MonkeyPatch
) -> None:
    resources = [
        *converged_wan_edge(),
        resource("interface.bridge", "br2", **{"vlan-filtering": True}),
    ]
    manager = manager_for(wan_edge, monkeypatch)

    result = manager.apply("test", manager.plan("test", resources))

    assert result.success
    assert [(o.action, o.address) for o in result.outcomes] == [
        ("create", "mikrotik_interface_bridge.br2")
    ]
    assert result.counts == {"create": 1, "update": 0, "delete": 0}
    assert [w[:2] for w in wan_edge.writes()] == [
        ("PUT", "interface/bridge"),
        ("PATCH", "interface/bridge/*100"),
    ]
    assert wan_edge.tables["interface/bridge"][-1]["vlan-filtering"] == "yes"


def test_bridge_vlan_widen_and_narrow_is_one_update_outcome(
    wan_edge: FakeRouterOS, monkeypatch: pytest.MonkeyPatch
) -> None:
    moved = resource(
        BVLAN,
        "v10",
        bridge="bridge",
        **{"vlan-ids": 10, "tagged": ["bridge", "ether3"], "untagged": ["ether2"]},
    )
    resources = [r for r in converged_wan_edge() if r.name != "v10"] + [moved]
    manager = manager_for(wan_edge, monkeypatch)

    result = manager.apply("test", manager.plan("test", resources))

    assert result.success
    assert len(wan_edge.writes()) == 2
    assert [(o.action, o.resource_name) for o in result.outcomes] == [("update", "v10")]
    assert result.counts == {"create": 0, "update": 1, "delete": 0}
    assert not manager.plan("test", resources).has_changes


@pytest.mark.parametrize(
    ("error", "lost"),
    [
        (RouterOSAPIError("failure: already have such entry", 400), False),
        (RouterOSConnectionError("Could not reach RouterOS"), True),
    ],
)
def test_step_failure_names_the_step_and_keeps_completed_outcomes(
    wan_edge: FakeRouterOS,
    monkeypatch: pytest.MonkeyPatch,
    error: RouterOSAPIError | RouterOSConnectionError,
    lost: bool,
) -> None:
    resources = [
        *converged_wan_edge(),
        resource("interface.bridge", "br2"),
        resource("interface.vlan", "vlan50", interface="br2", **{"vlan-id": 50}),
    ]
    wan_edge.errors[("PUT", "interface/vlan")] = error
    manager = manager_for(wan_edge, monkeypatch)

    result = manager.apply("test", manager.plan("test", resources))

    assert not result.success and result.failed is not None
    assert result.failed.resource_name == "vlan50"
    assert result.error is not None
    assert "step 2 of 2" in result.error
    assert "already have such entry" in result.error or "Could not reach" in result.error
    assert "create interface.bridge 'br2'" in result.error
    assert ("stopped answering after step 1" in result.error) is lost
    assert [o.resource_name for o in result.outcomes] == ["br2"]
    assert result.released == []
    assert "pw-example" not in result.error


def test_update_resource_is_never_applied_or_destroyed(
    wan_edge: FakeRouterOS, monkeypatch: pytest.MonkeyPatch
) -> None:
    resources = [*converged_wan_edge(), resource("system.package.update", "ros")]
    manager = manager_for(wan_edge, monkeypatch)
    plan = manager.plan("test", resources)
    assert not plan.has_changes
    assert manager.apply("test", plan).success
    only = [resource("system.package.update", "ros")]
    assert manager.apply("test", manager.plan("test", only)).success
    assert manager.destroy("test", only).success
    assert wan_edge.writes() == []
    assert not any(c[0] in ("POST", "EXECUTE") for c in wan_edge.calls)
