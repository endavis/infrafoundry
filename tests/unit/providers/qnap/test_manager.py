"""QnapConfigManager: plan, apply, destroy and scope against a fake switch."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.qnap.client import QnapApiError, QnapUnreachableError
from infrafoundry.providers.qnap.components.diff import QnapPlanError
from infrafoundry.providers.qnap.components.manager import QnapConfigManager

from .config_fake import FakeQnapConfig
from .conftest import firmware, lag, manager_for, vlan

pytestmark = pytest.mark.unit


def _mgr(
    fake: FakeQnapConfig, mp: pytest.MonkeyPatch, tmp_path: Path, **s: Any
) -> QnapConfigManager:
    return manager_for(fake, mp, tmp_path, **s)


def _managed(*rows: ResourceConfig) -> dict[str, list[ResourceConfig]]:
    out: dict[str, list[ResourceConfig]] = {}
    for row in rows:
        out.setdefault(row.type, []).append(row)
    return out


# -- scope


def test_firmware_only_environment_makes_no_device_call(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = FakeQnapConfig()
    plan = _mgr(fake, monkeypatch, tmp_path).plan("test", [firmware()])
    assert not plan.has_changes and fake.calls == [] and fake.sessions == 0


def test_targets_imply_add_only_and_skip_non_targets(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = FakeQnapConfig()
    mgr = _mgr(fake, monkeypatch, tmp_path)
    resources = [vlan("a", id=30, tagged=[1]), vlan("b", id=40, tagged=[1])]
    plan = mgr.plan(
        "test",
        resources,
        managed_resources=_managed(vlan("old", id=10)),
        target_resources=["a"],
    )
    assert plan.add_only
    assert [c.key for c in plan.diffs["vlan"].changes] == [(30,)]
    assert plan.diffs["vlan"].unmanaged == ["10", "20"]
    # A target that names no config resource makes no device call.
    other = FakeQnapConfig()
    _mgr(other, monkeypatch, tmp_path).plan("test", resources, target_resources=["zzz"])
    assert other.calls == []


def test_reads_ports_and_management_only_when_there_are_writes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = FakeQnapConfig()
    _mgr(fake, monkeypatch, tmp_path).plan("test", [vlan(id=10, tagged=[1, 2])])
    paths = [p for _, p, _ in fake.calls]
    assert "ports" not in paths and "ip/ipv4/interface" not in paths
    fake.calls.clear()
    _mgr(fake, monkeypatch, tmp_path).plan("test", [vlan(id=30, tagged=[1])])
    assert "ports" in [p for _, p, _ in fake.calls]


# -- plan


def test_plan_orders_steps_and_summarises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake = FakeQnapConfig()
    plan = _mgr(fake, monkeypatch, tmp_path).plan(
        "test",
        [
            vlan("new", id=30, tagged=[1, "lag1"]),
            lag("up", group=1, mode="lacp", members=[5, 6]),
        ],
    )
    assert [s.phase for s in plan.steps] == ["A", "C"]
    assert plan.counts == {"create": 2, "update": 0, "delete": 0}
    lines = plan.summary_lines()
    assert any(line.startswith("vlan: 1 to create") for line in lines)
    assert any("phase A (create LACP groups): 1 step(s)" in line for line in lines)
    assert plan.unmanaged == {"vlan": ["10", "20"]}


def test_plan_states_untag_moves(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake = FakeQnapConfig()
    plan = _mgr(fake, monkeypatch, tmp_path, management_vlan=20).plan(
        "test", [vlan(id=10, untagged=[5])]
    )
    assert "vlan 1 (unmanaged): untag port 5 (moves to vlan 10)" in plan.summary_lines()
    assert not plan.refusals


def test_stripping_a_management_vlan_member_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    plan = _mgr(FakeQnapConfig(), monkeypatch, tmp_path).plan("test", [vlan(id=10, untagged=[5])])
    assert any("removes 5 from the management VLAN 1" in r for r in plan.refusals)


def test_unmanaged_untag_strip_is_labelled(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake = FakeQnapConfig()
    fake.vlans = {1: {}, 10: {1: True}, 30: {5: False}}
    plan = _mgr(fake, monkeypatch, tmp_path).plan("test", [vlan(id=10, untagged=[5])])
    assert "vlan 30 (unmanaged): untag port 5 (moves to vlan 10)" in plan.summary_lines()


def test_losing_the_only_untagged_vlan_warns(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = FakeQnapConfig()
    fake.vlans[10] = {7: False}
    fake.vlans[1] = {}
    plan = _mgr(fake, monkeypatch, tmp_path).plan("test", [vlan(id=10, untagged=[])])
    assert "port 7 will have no untagged VLAN" in plan.warnings


def test_unknown_port_raises_a_plan_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    with pytest.raises(QnapPlanError):
        _mgr(FakeQnapConfig(), monkeypatch, tmp_path).plan("test", [vlan(id=30, tagged=[3, 7, 9])])


def test_management_vlan_is_inferred_with_a_warning(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = FakeQnapConfig()
    plan = _mgr(fake, monkeypatch, tmp_path, management_vlan=None).plan(
        "test", [vlan(id=30, tagged=[1])]
    )
    assert any("inferred" in w for w in plan.warnings) and not plan.refusals


def test_undeterminable_management_vlan_refuses_only_when_there_are_writes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = FakeQnapConfig(mgmt_key="not-a-vlan")
    mgr = _mgr(fake, monkeypatch, tmp_path, management_vlan=None)
    assert not mgr.plan("test", [vlan(id=10, tagged=[1, 2])]).refusals
    plan = mgr.plan("test", [vlan(id=30, tagged=[1])])
    assert any("management VLAN" in r for r in plan.refusals)


def test_lockout_refusal_and_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake = FakeQnapConfig()
    resources = [vlan("def", id=1, untagged=[1, 2])]
    plan = _mgr(fake, monkeypatch, tmp_path).plan("test", resources)
    assert any("removes 3 from the management VLAN 1" in r for r in plan.refusals)
    plan = _mgr(fake, monkeypatch, tmp_path, allow_lockout_risk=True).plan("test", resources)
    assert not plan.refusals
    assert any("allow_lockout_risk is set" in w for w in plan.warnings)
    assert any(w.startswith("lock-out risk allowed:") for w in plan.warnings)


def test_protected_ports_resolve_lag_tokens(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = FakeQnapConfig()
    fake.add_lag(1, [5, 6])
    fake.vlans[1][9] = True
    resources = [lag("up", group=1, mode="lacp", members=[5])]
    plan = _mgr(fake, monkeypatch, tmp_path, protected_ports=("lag1",)).plan("test", resources)
    assert any("removes members of LACP group 1" in r for r in plan.refusals)


# -- apply


def test_apply_writes_the_exact_bodies(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake = FakeQnapConfig()
    fake.vlans[1] = {}
    fake.add_lag(2, [7, 8])
    mgr = _mgr(fake, monkeypatch, tmp_path)
    resources = [
        lag("new", group=1, mode="lacp", members=[5, 6]),
        lag("l2", group=2, mode="lacp", members=[7]),
        vlan("created", id=30, tagged=["lag1"], untagged=[3]),
        vlan("updated", id=10, tagged=[1, 2, 4]),
    ]
    managed = _managed(vlan("gone", id=20, tagged=[1]))
    plan = mgr.plan("test", resources, managed_resources=managed)
    result = mgr.apply("test", plan)
    assert result.success, result.error
    writes = {(m, p, str(b)) for m, p, b in fake.writes()}
    assert (
        "POST",
        "lacp/group",
        str({"idx": "1", "data": {"AggrMode": "lacp", "PortMembers": ["5", "6"]}}),
    ) in writes
    assert (
        "PUT",
        "lacp/group",
        str({"idx": "2", "data": {"AggrMode": "lacp", "PortMembers": ["7"]}}),
    ) in writes
    assert (
        "POST",
        "vlan",
        str(
            {
                "data": [
                    {
                        "key": "30",
                        "val": [{"Port": "3", "Tagged": False}, {"Port": "9", "Tagged": True}],
                    }
                ]
            }
        ),
    ) in writes
    assert ("DELETE", "vlan", str({"idx": ["20"]})) in writes
    assert fake.vlans[10] == {1: True, 2: True, 4: True}
    assert 20 not in fake.vlans and fake.lags[1]["members"] == [5, 6]
    names = {(o.address, o.action) for o in result.outcomes}
    assert ("qnap_vlan.created", "create") in names
    assert ("qnap_vlan.updated", "update") in names
    assert ("qnap_vlan.gone", "delete") in names
    assert ("qnap_lacp_group.new", "create") in names
    assert result.counts == {"create": 2, "update": 2, "delete": 1}
    assert {"resource_type": "vlan", "name": "gone"} in result.released


def test_lag_members_keep_the_live_element_type(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = FakeQnapConfig(member_as_str=False)
    fake.add_lag(2, [7, 8])
    mgr = _mgr(fake, monkeypatch, tmp_path)
    plan = mgr.plan("test", [lag("new", group=1, mode="lacp", members=[5, 6])])
    assert mgr.apply("test", plan).success
    [(_, _, body)] = fake.writes()
    assert body["data"]["PortMembers"] == [5, 6]


def test_refused_plan_writes_nothing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake = FakeQnapConfig()
    mgr = _mgr(fake, monkeypatch, tmp_path)
    plan = mgr.plan("test", [vlan("def", id=1, untagged=[1])])
    result = mgr.apply("test", plan)
    assert not result.success and result.refusals and fake.writes() == []


def test_swap_of_untagged_ports_ends_correct(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = FakeQnapConfig()
    fake.vlans = {1: {}, 10: {3: False}, 20: {4: False}}
    mgr = _mgr(fake, monkeypatch, tmp_path)
    plan = mgr.plan("test", [vlan("a", id=10, untagged=[4]), vlan("b", id=20, untagged=[3])])
    result = mgr.apply("test", plan)
    assert result.success, result.error
    assert fake.vlans == {1: {}, 10: {4: False}, 20: {3: False}}
    assert {o.address for o in result.outcomes} == {"qnap_vlan.a", "qnap_vlan.b"}


def test_unmanaged_strip_is_not_an_outcome(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake = FakeQnapConfig()
    fake.vlans = {1: {}, 10: {1: True}, 30: {5: False}}
    mgr = _mgr(fake, monkeypatch, tmp_path)
    result = mgr.apply("test", mgr.plan("test", [vlan(id=10, untagged=[5])]))
    assert result.success, result.error
    assert fake.vlans[30] == {} and fake.vlans[10][5] is False
    assert [o.address for o in result.outcomes] == ["qnap_vlan.v10"]


def test_stops_at_the_first_error_naming_completed_steps(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = FakeQnapConfig()
    fake.fail_write[1] = QnapApiError("vlan", 400)
    mgr = _mgr(fake, monkeypatch, tmp_path)
    plan = mgr.plan(
        "test",
        [vlan("a", id=30, tagged=[1]), vlan("b", id=40, tagged=[1]), vlan("c", id=50, tagged=[1])],
    )
    result = mgr.apply("test", plan)
    assert not result.success and result.failed is not None
    assert "failed at step 2 of 3" in (result.error or "")
    assert "- create vlan 'a'" in (result.error or "")
    assert [o.resource_name for o in result.outcomes] == ["a"]
    assert result.released == []


def test_stopped_answering_error_names_steps_and_collect(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = FakeQnapConfig()
    fake.live_always_down = True
    mgr = _mgr(fake, monkeypatch, tmp_path, liveness_timeout=20)
    result = mgr.apply("test", mgr.plan("test", [vlan(id=30, tagged=[1])]))
    assert not result.success
    assert "the switch stopped answering on https://192.0.2.10" in (result.error or "")
    assert "1 completed step(s)" in (result.error or "") and "infra collect" in (result.error or "")
    assert fake.clock is not None and fake.clock.now >= 20


def test_liveness_wait_succeeds_when_the_switch_comes_back(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = FakeQnapConfig()
    fake.live_answers = [False, False, True]
    mgr = _mgr(fake, monkeypatch, tmp_path)
    result = mgr.apply("test", mgr.plan("test", [vlan(id=30, tagged=[1])]))
    assert result.success, result.error
    assert fake.clock is not None and fake.clock.now == 4.0


def test_connection_loss_during_a_write_is_reported(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = FakeQnapConfig()
    fake.fail_write[0] = QnapUnreachableError("gone")
    mgr = _mgr(fake, monkeypatch, tmp_path)
    result = mgr.apply("test", mgr.plan("test", [vlan(id=30, tagged=[1])]))
    assert not result.success and "gone" in (result.error or "")


def test_a_reread_that_differs_fails_and_names_the_object(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = FakeQnapConfig()
    fake.ignore_writes = {("POST", "vlan")}
    mgr = _mgr(fake, monkeypatch, tmp_path)
    result = mgr.apply("test", mgr.plan("test", [vlan("lost", id=30, tagged=[1])]))
    assert not result.success
    assert "differs from the plan for vlan 'lost'" in (result.error or "")
    assert fake.sessions == 3  # plan read, write session, fresh read-back session


def test_a_lag_reread_that_differs_fails(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake = FakeQnapConfig()
    fake.ignore_writes = {("POST", "lacp/group")}
    mgr = _mgr(fake, monkeypatch, tmp_path)
    result = mgr.apply("test", mgr.plan("test", [lag("up", group=1, mode="lacp", members=[5])]))
    assert "lacp.group 'up'" in (result.error or "")


def test_released_only_in_full_mode(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake = FakeQnapConfig()
    mgr = _mgr(fake, monkeypatch, tmp_path)
    managed = _managed(vlan("gone", id=20, tagged=[1]), vlan("kept", id=10, tagged=[1, 2]))
    resources = [vlan("kept", id=10, tagged=[1, 2])]
    plan = mgr.plan("test", resources, managed_resources=managed, add_only=True)
    assert mgr.apply("test", plan).released == []
    plan = mgr.plan("test", resources, managed_resources=managed)
    result = mgr.apply("test", plan)
    assert result.released == [{"resource_type": "vlan", "name": "gone"}]


def test_a_converged_plan_applies_without_writes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = FakeQnapConfig()
    mgr = _mgr(fake, monkeypatch, tmp_path)
    result = mgr.apply("test", mgr.plan("test", [vlan(id=10, tagged=[1, 2])]))
    assert result.success and fake.writes() == [] and result.counts == {}


# -- destroy


def test_destroy_deletes_only_declared_existing_objects(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = FakeQnapConfig()
    fake.add_lag(1, [5, 6])
    mgr = _mgr(fake, monkeypatch, tmp_path)
    resources = [
        vlan("a", id=20, tagged=[1]),
        vlan("missing", id=99, tagged=[1]),
        lag("up", group=1, mode="lacp", members=[5, 6]),
        vlan("abs", id=10, absent=True),
    ]
    result = mgr.destroy("test", resources)
    assert result.success, result.error
    assert fake.vlan_ids() == [1, 10] and fake.lags == {}
    assert [o.resource_name for o in result.outcomes] == ["a", "up"]
    assert [s.phase for s in result.completed] == ["F", "G"]


def test_destroy_never_deletes_vlan_1(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake = FakeQnapConfig()
    result = _mgr(fake, monkeypatch, tmp_path).destroy("test", [vlan("def", id=1, tagged=[1])])
    assert result.success and fake.writes() == []


def test_destroy_refuses_to_delete_the_management_vlan(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = FakeQnapConfig()
    result = _mgr(fake, monkeypatch, tmp_path, management_vlan=10).destroy(
        "test", [vlan("a", id=10, tagged=[1])]
    )
    assert not result.success and result.refusals and fake.writes() == []


def test_destroy_refuses_a_lag_that_a_remaining_vlan_lists(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = FakeQnapConfig()
    fake.add_lag(1, [5, 6])
    fake.vlans[10][9] = True
    result = _mgr(fake, monkeypatch, tmp_path).destroy(
        "test", [lag("up", group=1, mode="lacp", members=[5, 6])]
    )
    assert any("still lists lag1" in r for r in result.refusals) and fake.writes() == []


def test_destroy_honours_targets(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake = FakeQnapConfig()
    mgr = _mgr(fake, monkeypatch, tmp_path)
    result = mgr.destroy(
        "test", [vlan("a", id=20, tagged=[1]), vlan("b", id=10, tagged=[1])], target_resources=["a"]
    )
    assert result.success and fake.vlan_ids() == [1, 10]


# -- resource ids


def test_resource_ids(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake = FakeQnapConfig()
    fake.add_lag(1, [5])
    mgr = _mgr(fake, monkeypatch, tmp_path)
    ids = mgr.resource_ids(
        "test",
        [vlan("a", id=10), vlan("b", id=99), lag("up", group=1, mode="x", members=[5]), firmware()],
    )
    assert ids == {"a": "10", "up": "1"}
    assert mgr.resource_ids("test", [firmware()]) == {}
