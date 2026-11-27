"""OntapManager against the in-memory fake: plan, apply, destroy and resource ids."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.ontap.components.interface import CREATE, DELETE, UPDATE

from .conftest import HOST_IP, FakeOntapService, lif, manager_for, record

pytestmark = pytest.mark.unit


def _absent(name: str) -> ResourceConfig:
    return lif(
        name,
        absent=True,
        address=None,
        netmask=None,
        home_node=None,
        home_port=None,
        service_policy=None,
    )


def _apply(manager: Any, resources: list[ResourceConfig], **kwargs: Any) -> Any:
    return manager.apply("test", manager.plan("test", resources, **kwargs))


def test_create_is_a_single_post_carrying_auto_revert(tmp_path: Path) -> None:
    fake = FakeOntapService()
    manager = manager_for(fake, tmp_path)
    result = _apply(manager, [lif("new", address="192.0.2.30", auto_revert=True)])
    assert result.success and result.counts == {CREATE: 1, UPDATE: 0, DELETE: 0}
    [(kind, _uuid, fields)] = fake.calls
    assert kind == "create"
    assert fields == {
        "svm.name": "svm1",
        "name": "new",
        "ip.address": "192.0.2.30",
        "ip.netmask": "24",
        "location.home_node.name": "cluster1-01",
        "location.home_port.name": "e0d",
        "location.home_port.node.name": "cluster1-01",
        "service_policy.name": "default-data-files",
        "location.auto_revert": True,
    }
    assert [o.address for o in result.outcomes] == ["ontap_network_ip_interface.new"]


def test_update_sends_one_patch_per_group(fake: FakeOntapService, tmp_path: Path) -> None:
    manager = manager_for(fake, tmp_path)
    resource = lif(
        address="192.0.2.11",
        netmask="25",
        home_node="cluster1-02",
        home_port="e0e",
        auto_revert=True,
        service_policy="default-data-blocks",
    )
    result = _apply(manager, [resource])
    assert result.success and result.counts == {CREATE: 0, UPDATE: 1, DELETE: 0}
    bodies = [c[2] for c in fake.calls]
    assert bodies == [
        {"service_policy.name": "default-data-blocks", "location.auto_revert": True},
        {"ip.address": "192.0.2.11", "ip.netmask": "25"},
        {
            "location.home_node.name": "cluster1-02",
            "location.home_port.name": "e0e",
            "location.home_port.node.name": "cluster1-02",
        },
    ]
    assert {c[1] for c in fake.calls} == {"uuid-svm1-lif1"}


def test_auto_revert_only_update_is_one_small_patch(fake: FakeOntapService, tmp_path: Path) -> None:
    result = _apply(manager_for(fake, tmp_path), [lif(auto_revert=True)])
    assert result.success
    assert fake.calls == [("update", "uuid-svm1-lif1", {"location.auto_revert": True})]


def test_address_change_sends_the_live_netmask_along(
    fake: FakeOntapService, tmp_path: Path
) -> None:
    _apply(manager_for(fake, tmp_path), [lif(address="192.0.2.12", netmask=None)])
    assert fake.calls[0][2] == {"ip.address": "192.0.2.12", "ip.netmask": "24"}


def test_home_port_change_sends_the_port_with_the_live_node(
    fake: FakeOntapService, tmp_path: Path
) -> None:
    _apply(manager_for(fake, tmp_path), [lif(home_port="e0e", home_node=None)])
    assert fake.calls[0][2]["location.home_port.node.name"] == "cluster1-01"


def test_converged_cluster_makes_no_writes_and_a_second_apply_is_a_no_op(
    tmp_path: Path,
) -> None:
    fake = FakeOntapService()
    manager = manager_for(fake, tmp_path)
    resources = [lif("a", address="192.0.2.30"), lif("b", address="192.0.2.31", auto_revert=True)]
    first = _apply(manager, resources)
    assert first.success and len(first.completed) == 2
    fake.calls.clear()
    plan = manager.plan("test", resources)
    second = manager.apply("test", plan)
    assert not plan.has_changes and plan.summary_lines() == []
    assert second.success and fake.calls == [] and second.completed == []


def test_one_service_is_built_per_manager(fake: FakeOntapService, tmp_path: Path) -> None:
    built: list[object] = []

    def factory(settings: Any) -> FakeOntapService:
        built.append(settings)
        return fake

    from infrafoundry.providers.ontap.components.manager import OntapManager

    manager = OntapManager(tmp_path, factory, lambda _h: "192.0.2.250")
    _apply(manager, [lif(auto_revert=True)])
    assert len(built) == 1


def test_absent_deletes_and_is_reported_as_a_delete(fake: FakeOntapService, tmp_path: Path) -> None:
    result = _apply(manager_for(fake, tmp_path), [_absent("lif1")])
    assert result.success and result.counts[DELETE] == 1
    assert fake.rows == [] and fake.writes == ["delete"]


def test_managed_lif_dropped_from_the_yaml_is_deleted_and_released(
    tmp_path: Path,
) -> None:
    fake = FakeOntapService([record(), record("old", address="192.0.2.20")])
    manager = manager_for(fake, tmp_path)
    managed = {"network.ip.interface": [lif("old-row", name="old", address="192.0.2.20")]}
    result = _apply(manager, [lif()], managed_resources=managed)
    assert result.success and fake.writes == ["delete"]
    assert [o.resource_name for o in result.outcomes] == ["old-row"]
    assert result.released == [{"resource_type": "network.ip.interface", "name": "old-row"}]
    assert [r["name"] for r in fake.rows] == ["lif1"]


def test_unparsable_managed_row_is_never_deleted_or_released(tmp_path: Path) -> None:
    fake = FakeOntapService([record(), record("old", address="192.0.2.20")])
    broken = ResourceConfig(name="broken", type="network.ip.interface", provider="ontap", config={})
    result = _apply(
        manager_for(fake, tmp_path), [lif()], managed_resources={"network.ip.interface": [broken]}
    )
    assert result.success and fake.calls == [] and result.released == []


def test_unmanaged_lifs_are_kept_and_reported(tmp_path: Path) -> None:
    fake = FakeOntapService([record(), record("other", address="192.0.2.20")])
    plan = manager_for(fake, tmp_path).plan("test", [lif()])
    assert plan.unmanaged == {"network.ip.interface": ["svm1/other"]}
    assert plan.summary_lines() == [
        "network.ip.interface: 0 to create, 0 to update, 0 to delete, 1 unmanaged (kept)"
    ]


def test_only_the_svms_the_yaml_mentions_are_read(tmp_path: Path) -> None:
    fake = FakeOntapService([record(), record("other", svm="svm2")])
    plan = manager_for(fake, tmp_path).plan("test", [lif()])
    assert fake.reads == [["svm1"]] and plan.unmanaged == {}


def test_nothing_is_read_without_resources(tmp_path: Path) -> None:
    fake = FakeOntapService([record()])
    plan = manager_for(fake, tmp_path).plan("test", [])
    assert fake.reads == [] and not plan.has_changes


def test_drift_and_target_runs_are_add_only(tmp_path: Path) -> None:
    fake = FakeOntapService([record(), record("old", address="192.0.2.20")])
    manager = manager_for(fake, tmp_path)
    managed = {"network.ip.interface": [lif("old", address="192.0.2.20")]}
    drift = manager.plan("test", [lif()], add_only=True, managed_resources=managed)
    assert not drift.has_changes and drift.add_only
    targeted = manager.plan(
        "test",
        [lif("lif1", auto_revert=True), lif("lif2", address="192.0.2.40")],
        target_resources=["lif2"],
        managed_resources=managed,
    )
    assert targeted.add_only and [c.resource_name for c in targeted.diff.changes] == ["lif2"]
    assert manager.apply("test", drift).released == []


def test_lockout_refusal_makes_no_writes(tmp_path: Path) -> None:
    fake = FakeOntapService([record(address=HOST_IP)])
    manager = manager_for(fake, tmp_path)
    plan = manager.plan("test", [lif(address=HOST_IP, auto_revert=True)])
    assert plan.refusals
    result = manager.apply("test", plan)
    assert not result.success and result.refusals == plan.refusals and fake.calls == []


def test_failure_stops_the_run_and_reports_the_completed_steps(tmp_path: Path) -> None:
    fake = FakeOntapService(fail_on=lambda kind, fields: fields.get("name") == "b")
    manager = manager_for(fake, tmp_path)
    resources = [lif("a", address="192.0.2.30"), lif("b", address="192.0.2.31"), lif("c")]
    result = _apply(manager, resources)
    assert not result.success and result.failed is not None
    assert result.failed.resource_name == "b"
    assert "failed at step 2 of 3" in (result.error or "")
    assert "1 step(s) completed before it" in (result.error or "")
    assert "boom" in (result.error or "")
    assert fake.writes == ["create"]
    assert result.released == [] and result.counts[CREATE] == 1


def test_destroy_deletes_declared_lifs_that_exist(tmp_path: Path) -> None:
    fake = FakeOntapService([record(), record("other", address="192.0.2.20")])
    manager = manager_for(fake, tmp_path)
    result = manager.destroy("test", [lif(), lif("absent-one", name="nope"), _absent("other")])
    assert result.success and result.counts[DELETE] == 1
    assert [r["name"] for r in fake.rows] == ["other"]


def test_destroy_honours_targets_and_refuses_the_management_lif(tmp_path: Path) -> None:
    fake = FakeOntapService([record(), record("mgmt-data", address=HOST_IP)])
    manager = manager_for(fake, tmp_path)
    refused = manager.destroy("test", [lif("mgmt-data", address=HOST_IP)])
    assert not refused.success and "refusing to delete" in refused.refusals[0]
    assert fake.calls == []
    targeted = manager.destroy("test", [lif(), lif("mgmt-data")], target_resources=["lif1"])
    assert targeted.success and [r["name"] for r in fake.rows] == ["mgmt-data"]


def test_resource_ids_map_declared_live_lifs(tmp_path: Path) -> None:
    fake = FakeOntapService([record()])
    manager = manager_for(fake, tmp_path)
    ids = manager.resource_ids("test", [lif(), lif("missing"), _absent("lif1")])
    assert ids == {"lif1": "uuid-svm1-lif1"}
    assert manager.resource_ids("test", []) == {}


def test_off_home_warning_reaches_the_plan_and_the_apply(tmp_path: Path) -> None:
    fake = FakeOntapService([record(is_home=False)])
    manager = manager_for(fake, tmp_path)
    plan = manager.plan("test", [lif()])
    assert "not on its home port" in plan.warnings[0]
    assert "not on its home port" in manager.apply("test", plan).warnings[0]
