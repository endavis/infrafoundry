"""QNAP ordering: phases A to G, strips before claims, management VLAN last."""

from __future__ import annotations

import pytest

from infrafoundry.providers.qnap.components.diff import (
    DELETE,
    UPDATE,
    Change,
    LagEnd,
    TypeDiff,
    diff_lags,
    diff_vlans,
    end_state,
)
from infrafoundry.providers.qnap.components.ordering import Step, order_changes
from infrafoundry.providers.qnap.schema import DesiredLag, DesiredVlan, LiveLag, LiveVlan

from .config_fake import FakeQnapConfig

pytestmark = pytest.mark.unit

START = 8


def _steps(
    vlans: list[DesiredVlan],
    lags: list[DesiredLag],
    live: FakeQnapConfig,
    *,
    mgmt: int | None = 1,
    managed: set[tuple[int]] | None = None,
) -> list[Step]:
    live_v = [LiveVlan(v, m) for v, m in live.vlans.items()]
    live_l = [
        LiveLag(g, lag["mode"], frozenset(lag["members"]), True) for g, lag in live.lags.items()
    ]
    vd = diff_vlans(vlans, live_v, START, add_only=False, managed_keys=managed)
    ld = diff_lags(lags, live_l, START, add_only=False, managed_keys=managed)
    diffs = {"vlan": vd, "lacp.group": ld}
    lv = {v.id: dict(v.members) for v in live_v}
    ev, _ = end_state(diffs, lv, {g.group: LagEnd(g.mode, g.members) for g in live_l})
    return order_changes(vd, ld, lv, ev, mgmt)


def test_phases_run_a_to_g_in_sequence() -> None:
    fake = FakeQnapConfig()
    fake.add_lag(2, [7, 8])
    fake.vlans = {1: {}, 30: {1: True}, 10: {1: True, 2: True, 5: False}}
    steps = _steps(
        [
            DesiredVlan(40, "new", frozenset({1}), None),
            DesiredVlan(10, "v10", None, frozenset({6})),
            DesiredVlan(30, "gone", None, None, absent=True),
        ],
        [
            DesiredLag(1, "new-lag", "lacp", frozenset({3, 4})),
            DesiredLag(2, "lag2", "lacp", frozenset({7})),
        ],
        fake,
    )
    assert [s.phase for s in steps] == ["A", "C", "D", "E", "F"]
    assert [s.method for s in steps] == ["POST", "POST", "PUT", "PUT", "DELETE"]


def test_lag_delete_is_last_and_vlan_delete_before_it() -> None:
    fake = FakeQnapConfig()
    fake.add_lag(1, [5])
    steps = _steps(
        [DesiredVlan(10, "v10", None, None, absent=True)],
        [DesiredLag(1, "l", None, None, absent=True)],
        fake,
    )
    assert [(s.phase, s.type_name) for s in steps] == [("F", "vlan"), ("G", "lacp.group")]


def test_swap_frees_ports_in_phase_b_before_the_claims_in_d() -> None:
    fake = FakeQnapConfig()
    fake.vlans = {1: {}, 10: {3: False}, 20: {4: False}}
    steps = _steps(
        [DesiredVlan(10, "a", None, frozenset({4})), DesiredVlan(20, "b", None, frozenset({3}))],
        [],
        fake,
        mgmt=1,
    )
    assert [s.phase for s in steps] == ["B", "B", "D", "D"]
    # Applying them in order on the fake never leaves a port untagged twice.
    for step in steps:
        fake.put(step.path, step.body)
    assert fake.vlans == {1: {}, 10: {4: False}, 20: {3: False}}


def test_port_moves_to_a_new_vlan_via_phase_b_then_c() -> None:
    fake = FakeQnapConfig()
    fake.vlans = {1: {5: False, 6: False}}
    steps = _steps([DesiredVlan(30, "new", None, frozenset({5}))], [], fake, mgmt=99)
    assert [s.phase for s in steps] == ["B", "C"]
    assert steps[0].incidental is True
    fake.put(steps[0].path, steps[0].body)
    fake.post(steps[1].path, steps[1].body)
    assert fake.vlans == {1: {6: False}, 30: {5: False}}


def test_deleted_vlan_that_hands_a_port_over_is_freed_first() -> None:
    fake = FakeQnapConfig()
    fake.vlans = {1: {}, 10: {5: False}, 20: {}}
    steps = _steps(
        [
            DesiredVlan(10, "gone", None, None, absent=True),
            DesiredVlan(20, "b", None, frozenset({5})),
        ],
        [],
        fake,
    )
    assert [s.phase for s in steps] == ["B", "D", "F"]


def test_management_vlan_update_is_last_in_phase_d() -> None:
    fake = FakeQnapConfig()
    fake.vlans = {1: {1: True}, 10: {1: True}, 20: {1: True}}
    steps = _steps(
        [
            DesiredVlan(1, "mgmt", frozenset({1, 2}), None),
            DesiredVlan(10, "a", frozenset({1, 2}), None),
            DesiredVlan(20, "b", frozenset({1, 2}), None),
        ],
        [],
        fake,
        mgmt=10,
    )
    assert [s.key[0] for s in steps if s.phase == "D"] == [1, 20, 10]


def test_member_style_is_used_for_lag_bodies() -> None:
    change = Change("create", "lacp.group", (1,), "l", after=LagEnd("lacp", frozenset({6, 5})))
    diff = TypeDiff("lacp.group", [change])
    [as_str] = order_changes(None, diff, {}, {}, None, member_as_str=True)
    [as_int] = order_changes(None, diff, {}, {}, None, member_as_str=False)
    assert as_str.body["data"]["PortMembers"] == ["5", "6"]
    assert as_int.body["data"]["PortMembers"] == [5, 6]


def test_kinds_are_update_and_delete_for_b_and_f() -> None:
    fake = FakeQnapConfig()
    fake.vlans = {1: {}, 10: {5: False}, 20: {}}
    steps = _steps(
        [
            DesiredVlan(10, "gone", None, None, absent=True),
            DesiredVlan(20, "b", None, frozenset({5})),
        ],
        [],
        fake,
    )
    assert [s.kind for s in steps] == [UPDATE, UPDATE, DELETE]
