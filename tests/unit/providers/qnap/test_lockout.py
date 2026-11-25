"""QNAP lock-out rules: management VLAN, protected ports and the override."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest

from infrafoundry.providers.qnap.components.lockout import check_lockout, management_vlan

from .conftest import SETTINGS

pytestmark = pytest.mark.unit

START = 8
LIVE_VLANS = {1: {1: False, 2: True, 3: True}, 10: {1: True}}
LIVE_LAGS: dict[int, frozenset[int]] = {1: frozenset({5, 6})}


def check(
    end_vlans: Any = None,
    end_lags: Any = None,
    *,
    protected: set[int] | None = None,
    allow: bool = False,
    live_vlans: Any = None,
    live_lags: Any = None,
) -> Any:
    return check_lockout(
        end_vlans if end_vlans is not None else {v: dict(m) for v, m in LIVE_VLANS.items()},
        end_lags if end_lags is not None else dict(LIVE_LAGS),
        live_vlans if live_vlans is not None else LIVE_VLANS,
        live_lags if live_lags is not None else LIVE_LAGS,
        1,
        protected or set(),
        START,
        allow,
    )


def test_management_vlan_from_settings_wins() -> None:
    assert management_vlan(replace(SETTINGS, management_vlan=7), []) == (7, [])


def test_management_vlan_is_inferred_from_a_single_enabled_interface() -> None:
    vlan, warnings = management_vlan(SETTINGS, [{"key": "5", "val": {"enableInterface": True}}])
    assert vlan == 5 and "inferred" in warnings[0] and "unverified" in warnings[0]


@pytest.mark.parametrize(
    "reply",
    [
        [],
        "x",
        [{"key": "1", "val": {"enableInterface": False}}],
        [
            {"key": "1", "val": {"enableInterface": True}},
            {"key": "2", "val": {"enableInterface": True}},
        ],
        [{"key": "abc", "val": {"enableInterface": True}}],
        [{"key": "4095", "val": {"enableInterface": True}}],
    ],
)
def test_management_vlan_undeterminable(reply: Any) -> None:
    assert management_vlan(SETTINGS, reply) == (None, [])


def test_unchanged_end_state_is_clean() -> None:
    result = check()
    assert not result.refusals and not result.warnings


def test_rule_a_deleting_the_management_vlan() -> None:
    result = check({10: {1: True}})
    assert any("deletes the management VLAN 1" in r for r in result.refusals)


def test_rule_b_protected_port_dropped_or_flipped() -> None:
    result = check({1: {1: False, 3: True}, 10: {1: True}}, protected={2})
    assert any("removes 2 from the management VLAN" in r for r in result.refusals)
    result = check({1: {1: True, 2: True, 3: True}, 10: {1: True}}, protected={1})
    assert any("flips the Tagged flag of 1" in r for r in result.refusals)
    # An unprotected member may go when a protected list is set.
    assert not check({1: {1: False, 2: True}, 10: {1: True}}, protected={1}).refusals


def test_protected_port_outside_the_management_vlan_only_warns() -> None:
    result = check(protected={7})
    assert not result.refusals
    assert any("protected port 7 is not a member" in w for w in result.warnings)


def test_rule_c_without_protected_ports_any_member_is_kept() -> None:
    result = check({1: {1: False, 2: True}, 10: {1: True}})
    assert any("removes 3 from the management VLAN" in r for r in result.refusals)
    result = check({1: {1: False, 2: False, 3: True}, 10: {1: True}})
    assert any("flips the Tagged flag of 2" in r for r in result.refusals)


def test_adding_members_to_the_management_vlan_is_allowed() -> None:
    result = check({1: {1: False, 2: True, 3: True, 4: True}, 10: {1: True}})
    assert not result.refusals


def test_rule_d_protected_port_into_a_lag() -> None:
    result = check(end_lags={1: frozenset({5, 6}), 2: frozenset({1, 4})}, protected={1})
    assert any("puts protected port 1 into LACP group 2" in r for r in result.refusals)
    # A protected port already in the group is not "put" there.
    result = check(end_lags={1: frozenset({5, 6})}, live_lags={1: frozenset({5, 6})}, protected={5})
    assert not result.refusals


def test_rule_e_deleting_or_shrinking_a_protected_lag() -> None:
    result = check(end_lags={}, protected={9})
    assert any("deletes LACP group 1, whose interface is protected" in r for r in result.refusals)
    result = check(end_lags={1: frozenset({5})}, protected={9})
    assert any("removes members of LACP group 1" in r for r in result.refusals)
    assert not check(end_lags={1: frozenset({5, 6, 7})}, protected={9}).refusals


def test_rule_f_deleting_a_lag_a_vlan_still_lists() -> None:
    end = {1: dict(LIVE_VLANS[1]), 10: {1: True, 9: True}}
    result = check(end, end_lags={})
    assert any("VLAN 10 still lists lag1" in r for r in result.refusals)


def test_override_downgrades_a_to_e_to_warnings_but_not_f() -> None:
    result = check({10: {1: True}}, allow=True)
    assert not result.refusals
    assert any(w.startswith("lock-out risk allowed:") for w in result.warnings)
    end = {1: dict(LIVE_VLANS[1]), 10: {1: True, 9: True}}
    assert check(end, end_lags={}, allow=True).refusals
