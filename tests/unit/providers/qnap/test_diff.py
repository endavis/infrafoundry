"""QNAP diff: membership semantics, untag moves, deletes and plan-time errors."""

from __future__ import annotations

from typing import Any

import pytest

from infrafoundry.providers.qnap.components.diff import (
    CREATE,
    DELETE,
    UPDATE,
    LagEnd,
    QnapPlanError,
    check_end_state,
    diff_lags,
    diff_vlans,
    end_state,
    untag_warnings,
)
from infrafoundry.providers.qnap.schema import (
    DesiredLag,
    DesiredVlan,
    LacpInfo,
    LiveLag,
    LiveVlan,
)

pytestmark = pytest.mark.unit

START = 8
INFO = LacpInfo(start_index=START, max_channels=4, max_ports=4)


def dv(
    vid: int,
    tagged: Any = None,
    untagged: Any = None,
    absent: bool = False,
    name: str | None = None,
) -> DesiredVlan:
    return DesiredVlan(
        vid,
        name or f"v{vid}",
        None if tagged is None else frozenset(tagged),
        None if untagged is None else frozenset(untagged),
        absent,
    )


def lv(vid: int, **members: bool) -> LiveVlan:
    return LiveVlan(vid, {int(k[1:]): v for k, v in members.items()})


def live_default() -> list[LiveVlan]:
    return [
        LiveVlan(1, dict.fromkeys(range(1, 9), False)),
        LiveVlan(10, {1: True, 2: True}),
    ]


def run(desired: list[DesiredVlan], live: list[LiveVlan] | None = None, **kw: Any) -> Any:
    kw.setdefault("add_only", False)
    kw.setdefault("managed_keys", None)
    return diff_vlans(desired, live if live is not None else live_default(), START, **kw)


def test_converged_switch_plans_clean() -> None:
    assert run([dv(10, tagged=[1, 2])]).is_empty


def test_declared_tagged_replaces_and_omitted_untagged_is_kept() -> None:
    live = [LiveVlan(10, {1: True, 2: True, 3: False})]
    diff = run([dv(10, tagged=[1])], live)
    [change] = diff.changes
    assert change.kind == UPDATE and change.after == {1: True, 3: False}


def test_declared_untagged_replaces_and_omitted_tagged_is_kept() -> None:
    live = [LiveVlan(10, {1: True, 2: True, 3: False})]
    [change] = run([dv(10, untagged=[4])], live).changes
    assert change.after == {1: True, 2: True, 4: False}


def test_port_moves_from_untagged_to_tagged() -> None:
    live = [LiveVlan(10, {3: False})]
    [change] = run([dv(10, tagged=[3])], live).changes
    assert change.after == {3: True}


def test_port_moves_from_tagged_to_untagged() -> None:
    live = [LiveVlan(10, {3: True})]
    [change] = run([dv(10, untagged=[3])], live).changes
    assert change.after == {3: False}


def test_create_with_and_without_members() -> None:
    diff = run([dv(30, tagged=[1], name="a"), dv(40, name="b")])
    kinds = {c.key: (c.kind, c.after) for c in diff.changes}
    assert kinds[(30,)] == (CREATE, {1: True})
    assert kinds[(40,)] == (CREATE, {})


def test_lag_port_resolves_with_the_start_index() -> None:
    [change] = run([dv(10, tagged=[1, 2, "lag1"])]).changes
    assert change.after[9] is True


def test_undeclared_vlan_is_unmanaged_and_vlan_1_is_ignored() -> None:
    diff = run([dv(20, tagged=[1])], [*live_default()])
    assert diff.unmanaged == ["10"]


def test_managed_vlan_no_longer_declared_is_deleted_unless_add_only() -> None:
    diff = run([], managed_keys={(10,), (1,)})
    assert [(c.kind, c.key) for c in diff.changes] == [(DELETE, (10,))]
    diff = run([], managed_keys={(10,)}, add_only=True)
    assert diff.is_empty and diff.unmanaged == ["10"]


def test_absent_deletes_and_add_only_skips() -> None:
    diff = run([dv(10, absent=True)])
    assert [c.kind for c in diff.changes] == [DELETE]
    diff = run([dv(10, absent=True)], add_only=True)
    assert diff.is_empty and "absent: true, skipped: add-only" in diff.unmanaged[0]
    assert run([dv(99, absent=True)]).is_empty
    assert run([dv(1, absent=True)]).is_empty  # VLAN 1 is never deleted


def test_untagged_port_moves_and_strips_the_old_vlan() -> None:
    live = [LiveVlan(1, {5: False, 6: False}), LiveVlan(10, {1: True})]
    diff = run([dv(10, untagged=[5])], live)
    by = {c.key[0]: c for c in diff.changes}
    assert by[10].after == {1: True, 5: False}
    assert by[1].after == {6: False}
    assert by[1].incidental is True
    assert by[1].notes == ("untag port 5 (moves to vlan 10)",)


def test_strip_of_a_declared_vlan_is_not_incidental() -> None:
    live = [LiveVlan(10, {5: False}), LiveVlan(20, {})]
    diff = run([dv(10, tagged=[1]), dv(20, untagged=[5])], live)
    by = {c.key[0]: c for c in diff.changes}
    assert by[10].after == {1: True}
    assert by[10].incidental is False
    assert by[20].after == {5: False}


def test_two_vlans_swap_untagged_ports() -> None:
    live = [LiveVlan(10, {3: False}), LiveVlan(20, {4: False})]
    diff = run([dv(10, untagged=[4]), dv(20, untagged=[3])], live)
    by = {c.key[0]: c.after for c in diff.changes}
    assert by == {10: {4: False}, 20: {3: False}}


def test_two_vlans_claiming_one_port_is_an_error() -> None:
    with pytest.raises(QnapPlanError, match="declared untagged"):
        run([dv(10, untagged=[5]), dv(20, untagged=[5])], [LiveVlan(10, {}), LiveVlan(20, {})])


def test_tagged_and_untagged_resolving_to_one_port_is_an_error() -> None:
    with pytest.raises(QnapPlanError):
        run([dv(10, tagged=[9], untagged=["lag1"])], [LiveVlan(10, {})])


def test_port_losing_its_only_untagged_vlan_warns() -> None:
    live = {1: {5: False}, 10: {1: True}}
    assert untag_warnings({1: {}, 10: {1: True}}, live, START) == [
        "port 5 will have no untagged VLAN"
    ]
    assert untag_warnings(live, live, START) == []


# -- lacp


def ll(group: int, mode: str, members: list[int]) -> LiveLag:
    return LiveLag(group, mode, frozenset(members), True)


def run_lags(desired: list[DesiredLag], live: list[LiveLag], **kw: Any) -> Any:
    kw.setdefault("add_only", False)
    kw.setdefault("managed_keys", None)
    return diff_lags(desired, live, START, **kw)


def dl(group: int, mode: Any, members: Any, absent: bool = False) -> DesiredLag:
    return DesiredLag(
        group, f"g{group}", mode, None if members is None else frozenset(members), absent
    )


def test_lag_create_update_and_clean() -> None:
    live = [ll(1, "lacp", [5, 6])]
    assert run_lags([dl(1, "lacp", [5, 6])], live).is_empty
    [change] = run_lags([dl(1, "lacp", [5, 6, 7])], live).changes
    assert change.kind == UPDATE and change.after == LagEnd("lacp", frozenset({5, 6, 7}))
    [change] = run_lags([dl(1, "static", [5, 6])], live).changes
    assert change.after.mode == "static"
    [change] = run_lags([dl(2, "lacp", [1])], live).changes
    assert change.kind == CREATE


def test_omitted_mode_is_kept() -> None:
    live = [ll(1, "lacp", [5])]
    [change] = run_lags([dl(1, None, [5, 6])], live).changes
    assert change.after == LagEnd("lacp", frozenset({5, 6}))


def test_new_lag_needs_mode_and_members() -> None:
    with pytest.raises(QnapPlanError):
        run_lags([dl(2, None, [1])], [])


def test_lag_member_above_start_index_is_an_error() -> None:
    with pytest.raises(QnapPlanError, match="physical"):
        run_lags([dl(2, "lacp", ["lag1"])], [])


def test_lag_deletes() -> None:
    live = [ll(1, "lacp", [5]), ll(2, "lacp", [6])]
    diff = run_lags([dl(1, None, None, absent=True)], live, managed_keys={(2,)})
    assert sorted(c.key for c in diff.changes) == [(1,), (2,)]
    diff = run_lags([dl(1, None, None, absent=True)], live, managed_keys={(2,)}, add_only=True)
    assert diff.is_empty and len(diff.unmanaged) == 2
    diff = run_lags([], live)
    assert diff.unmanaged == ["1", "2"]


# -- end state and checks


def _check(
    desired_vlans: list[DesiredVlan],
    desired_lags: list[DesiredLag] | None = None,
    *,
    ports: int = 8,
) -> None:
    live_v = live_default()
    vd = diff_vlans(desired_vlans, live_v, START, add_only=False, managed_keys=None)
    ld = diff_lags(desired_lags or [], [], START, add_only=False, managed_keys=None)
    diffs = {"vlan": vd, "lacp.group": ld}
    ev, el = end_state(diffs, {v.id: dict(v.members) for v in live_v}, {})
    check_end_state(diffs, ev, el, port_count=ports, info=INFO)


def test_end_state_applies_creates_updates_and_deletes() -> None:
    live_v = live_default()
    diff = diff_vlans(
        [dv(30, tagged=[1], name="n"), dv(10, absent=True)],
        live_v,
        START,
        add_only=False,
        managed_keys=None,
    )
    ev, _ = end_state({"vlan": diff}, {v.id: dict(v.members) for v in live_v}, {})
    assert 30 in ev and 10 not in ev and 1 in ev


def test_unknown_physical_port() -> None:
    with pytest.raises(QnapPlanError, match="not a LACP group"):
        _check([dv(30, tagged=[7, 9])], ports=8)
    with pytest.raises(QnapPlanError, match="does not exist"):
        _check([dv(30, tagged=[3])], [DesiredLag(1, "g", "lacp", frozenset({3, 7}))], ports=6)


def test_unknown_lag() -> None:
    with pytest.raises(QnapPlanError, match="not a LACP group"):
        _check([dv(30, tagged=["lag1"])])


def test_known_lag_is_fine() -> None:
    _check([dv(30, tagged=["lag1"])], [DesiredLag(1, "g", "lacp", frozenset({5, 6}))])


def test_vlan_lists_a_port_that_belongs_to_a_lag() -> None:
    with pytest.raises(QnapPlanError, match="member of lag1"):
        _check([dv(30, tagged=[5])], [DesiredLag(1, "g", "lacp", frozenset({5, 6}))])


def test_too_many_lag_members_and_group_number() -> None:
    with pytest.raises(QnapPlanError, match="allows 4"):
        _check([], [DesiredLag(1, "g", "lacp", frozenset({1, 2, 3, 4, 5}))])
    with pytest.raises(QnapPlanError, match="above"):
        _check([], [DesiredLag(9, "g", "lacp", frozenset({1}))])
