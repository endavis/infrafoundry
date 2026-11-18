"""Tests for the MikroTik plan manager against the in-memory fake device."""

import pytest

from infrafoundry.providers.mikrotik.settings import MikroTikSettings

from .conftest import FakeRouterOS, converged_wan_edge, manager_for, resource


def test_converged_device_plans_clean(
    wan_edge: FakeRouterOS, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = manager_for(wan_edge, monkeypatch).plan("test", converged_wan_edge())

    assert not plan.has_changes
    assert plan.steps == [] and plan.refusals == []


def test_each_rest_path_is_read_once(
    factory: FakeRouterOS, monkeypatch: pytest.MonkeyPatch
) -> None:
    resources = [resource("interface.bridge", "bridge", comment="x")]
    manager_for(factory, monkeypatch).plan("test", resources)

    gets = [path for verb, path in factory.calls if verb == "GET"]
    assert len(gets) == len(set(gets))


def test_factory_default_to_wan_edge_layout(
    factory: FakeRouterOS, monkeypatch: pytest.MonkeyPatch
) -> None:
    resources = converged_wan_edge()
    resources.append(resource("ip.address", "factory", address="192.168.88.1/24", absent=True))

    plan = manager_for(factory, monkeypatch).plan("test", resources)

    assert plan.refusals == []
    phases = "".join(s.phase for s in plan.steps)
    assert phases.index("C") > phases.rindex("B")
    assert phases.index("E") > phases.index("C")
    assert phases.endswith("F") or "F" not in phases
    lines = "\n".join(plan.summary_lines())
    assert "interface.bridge.port: 0 to create, 3 to update" in lines
    assert "ip.address: 1 to create, 0 to update, 1 to delete" in lines


def test_lockout_is_refused(wan_edge: FakeRouterOS, monkeypatch: pytest.MonkeyPatch) -> None:
    resources = converged_wan_edge()
    resources = [r for r in resources if r.name != "mgmt"]

    plan = manager_for(wan_edge, monkeypatch).plan(
        "test", resources, managed_resources={"ip.address": [converged_wan_edge()[9]]}
    )

    assert plan.refusals and "management address" in plan.refusals[0]


def test_filtered_run_is_add_only(wan_edge: FakeRouterOS, monkeypatch: pytest.MonkeyPatch) -> None:
    managed = {"ip.address": [resource("ip.address", "old", address="192.0.2.2/24", interface="x")]}
    resources = [resource("ip.address", "new", address="198.51.100.2/24", interface="vlan99")]

    plan = manager_for(wan_edge, monkeypatch).plan(
        "test", resources, managed_resources=managed, target_resources=["new"]
    )

    assert plan.counts == {"create": 1, "update": 0, "delete": 0}
    assert plan.unmanaged == {"ip.address": ["192.0.2.2/24"]}


def test_managed_row_dropped_from_yaml_is_deleted(
    wan_edge: FakeRouterOS, monkeypatch: pytest.MonkeyPatch
) -> None:
    keep = converged_wan_edge()
    managed = {
        "interface.vlan": [
            resource("interface.vlan", "vlan77", interface="bridge", **{"vlan-id": 77})
        ]
    }
    wan_edge.tables["interface/vlan"].append(
        {".id": "*9", "name": "vlan77", "interface": "bridge", "vlan-id": "77"}
    )

    plan = manager_for(wan_edge, monkeypatch).plan("test", keep, managed_resources=managed)

    assert plan.counts["delete"] == 1
    assert [s.phase for s in plan.steps] == ["E"]


def test_unresolvable_host_refuses_structural_plan_only(
    wan_edge: FakeRouterOS, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = MikroTikSettings("https://sw-wan.example.com", "admin", "pw")
    manager = manager_for(wan_edge, monkeypatch, settings)

    structural = manager.plan("test", [resource("interface.bridge", "bridge", comment="x")])
    service_only = manager.plan("test", [resource("ip.service", "www", disabled=False)])

    assert structural.refusals == [
        "cannot resolve the management host 'sw-wan.example.com', "
        "so the plan cannot prove it keeps the management connection"
    ]
    assert service_only.refusals == [] and service_only.has_changes


def test_service_disable_refused_for_connection_service(
    wan_edge: FakeRouterOS, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = manager_for(wan_edge, monkeypatch).plan(
        "test", [resource("ip.service", "www-ssl", disabled=True)]
    )
    assert plan.refusals and "www-ssl" in plan.refusals[0]


def test_summary_reports_unmanaged_objects(
    wan_edge: FakeRouterOS, monkeypatch: pytest.MonkeyPatch
) -> None:
    resources = [r for r in converged_wan_edge() if r.name != "p4"]
    plan = manager_for(wan_edge, monkeypatch).plan("test", resources)
    assert plan.unmanaged == {"interface.bridge.port": ["ether4"]}
    assert "1 unmanaged (kept)" in "\n".join(plan.summary_lines())
