"""QNAP schema: ports, declared objects, resource checks, live parsers and write bodies."""

from __future__ import annotations

from typing import Any

import pytest

from infrafoundry.providers.qnap.client import QnapApiDriftError
from infrafoundry.providers.qnap.schema import (
    check_resources,
    desired_from_resources,
    lag_body,
    lag_delete_body,
    member_style,
    parse_lacp_info,
    parse_lags,
    parse_port,
    parse_vlans,
    port_label,
    resolve_port,
    vlan_body,
    vlan_delete_body,
)

from .conftest import lag, vlan

pytestmark = pytest.mark.unit


def _messages(*resources: Any) -> list[str]:
    return [f.message for f in check_resources(list(resources))]


@pytest.mark.parametrize("value", [1, 8, "lag1", "lag12"])
def test_parse_port_accepts(value: Any) -> None:
    assert parse_port(value) == value


@pytest.mark.parametrize("value", [0, -1, True, False, "lag", "lagx", "lag0", "5", 1.5, None])
def test_parse_port_rejects(value: Any) -> None:
    with pytest.raises(ValueError):
        parse_port(value)


def test_lag_port_numbers_round_trip_with_the_start_index() -> None:
    assert resolve_port("lag2", 8) == 10
    assert resolve_port(5, 8) == 5
    assert port_label(10, 8) == "lag2"
    assert port_label(8, 8) == "8"


def test_valid_vlan_and_lag_have_no_findings() -> None:
    assert not _messages(
        vlan(id=10, tagged=[1, "lag1"], untagged=[2]),
        vlan("v20", id=20, untagged=[3]),
        lag(group=1, mode="lacp", members=[5, 6]),
    )


def test_name_in_config_is_ignored() -> None:
    assert not _messages(vlan(id=10, name="v10"))


@pytest.mark.parametrize("vlan_id", [0, 4001, "10", True])
def test_vlan_id_range(vlan_id: Any) -> None:
    assert any("'id' must be an integer within 1-4000" in m for m in _messages(vlan(id=vlan_id)))


def test_vlan_1_is_declarable_but_not_absent() -> None:
    assert not _messages(vlan("default", id=1, tagged=[1]))
    assert any("VLAN 1" in m for m in _messages(vlan("default", id=1, absent=True)))


def test_missing_id_and_unknown_field() -> None:
    messages = _messages(vlan(tagged=[1], bogus=1))
    assert any("unknown field(s): bogus" in m for m in messages)
    assert any("missing required field(s): id" in m for m in messages)


def test_port_both_tagged_and_untagged() -> None:
    assert any(
        "both tagged and untagged" in m for m in _messages(vlan(id=10, tagged=[1], untagged=[1]))
    )


def test_port_untagged_in_two_declared_vlans() -> None:
    messages = _messages(vlan("a", id=10, untagged=[3]), vlan("b", id=20, untagged=[3]))
    assert any("untagged in VLAN 10 and VLAN 20" in m for m in messages)


@pytest.mark.parametrize("bad", [0, "lag", "lagx", True, "5"])
def test_bad_port_tokens(bad: Any) -> None:
    assert any("'tagged'" in m for m in _messages(vlan(id=10, tagged=[bad])))


def test_ports_must_be_a_list() -> None:
    assert any("must be a list of ports" in m for m in _messages(vlan(id=10, tagged=5)))


def test_absent_with_extra_fields() -> None:
    assert any("only key fields" in m for m in _messages(vlan(id=10, absent=True, tagged=[1])))
    assert any("only key fields" in m for m in _messages(lag(group=1, absent=True, mode="x")))
    assert not _messages(vlan(id=10, absent=True), lag(group=1, absent=True))


def test_duplicate_keys() -> None:
    assert any("duplicate" in m for m in _messages(vlan("a", id=10), vlan("b", id=10)))
    assert any(
        "duplicate" in m
        for m in _messages(
            lag("a", group=1, mode="x", members=[1]), lag("b", group=1, mode="x", members=[2])
        )
    )


def test_lag_member_as_lag_and_in_two_groups() -> None:
    assert any("physical ports" in m for m in _messages(lag(group=1, mode="x", members=["lag2"])))
    messages = _messages(
        lag("a", group=1, mode="x", members=[1, 2]), lag("b", group=2, mode="x", members=[2, 3])
    )
    assert any("member of group 1 and group 2" in m for m in messages)


def test_lag_requires_mode_and_members_unless_absent() -> None:
    assert any("missing required field(s): mode, members" in m for m in _messages(lag(group=1)))
    assert not _messages(lag(group=1, mode="x", members=[]))


def test_desired_from_resources_keeps_undeclared_lists_none() -> None:
    [only, both, group] = desired_from_resources(
        [
            vlan("a", id=10, tagged=[1]),
            vlan("b", id=20, tagged=[], untagged=[2]),
            lag(group=3, mode="m", members=[1]),
        ]
    )
    assert only.key == (10,) and only.untagged is None  # type: ignore[union-attr]
    assert both.tagged == frozenset()  # type: ignore[union-attr]
    assert group.key == (3,) and group.mode == "m"  # type: ignore[union-attr]


def test_desired_from_resources_raises_without_a_key() -> None:
    with pytest.raises(ValueError):
        desired_from_resources([vlan(tagged=[1])])


def test_parse_vlans_and_lags() -> None:
    [parsed] = parse_vlans([{"key": "10", "val": [{"Port": "1", "Tagged": True}]}])
    assert parsed.id == 10 and parsed.members == {1: True}
    [group] = parse_lags([{"key": "1", "val": {"AggrMode": "lacp", "PortMembers": ["5", "6"]}}])
    assert group.members == frozenset({5, 6}) and group.member_as_str is True
    [empty] = parse_lags([{"key": "2", "val": {"AggrMode": "lacp", "PortMembers": []}}])
    assert empty.member_as_str is None
    assert member_style([empty, group]) is True
    assert member_style([]) is True
    [ints] = parse_lags([{"key": "1", "val": {"AggrMode": "lacp", "PortMembers": [5]}}])
    assert member_style([ints]) is False
    info = parse_lacp_info({"StartIndex": 8, "MaxPortChannels": 8, "MaxPortsPerPortChannel": 8})
    assert (info.start_index, info.max_channels, info.max_ports) == (8, 8, 8)


def test_parse_vlans_reads_null_val_as_no_members() -> None:
    """A VLAN with no member ports comes back as ``"val": null`` on a real switch."""
    [parsed] = parse_vlans([{"key": "3999", "val": None}])
    assert parsed.id == 3999 and parsed.members == {}


@pytest.mark.parametrize(
    "parser, reply",
    [
        (parse_vlans, {"not": "a list"}),
        (parse_vlans, [{"key": "1"}]),
        (parse_vlans, [{"key": "1", "val": "x"}]),
        (parse_vlans, [{"key": "1", "val": [{"Port": "1"}]}]),
        (parse_vlans, [{"key": "x", "val": []}]),
        (parse_lags, [{"key": "1", "val": {"AggrMode": "x"}}]),
        (parse_lags, "nope"),
        (parse_lacp_info, {"StartIndex": 8}),
        (parse_lacp_info, []),
    ],
)
def test_wrong_shape_raises_drift(parser: Any, reply: Any) -> None:
    with pytest.raises(QnapApiDriftError):
        parser(reply)


def test_write_bodies() -> None:
    assert vlan_body(10, {2: False, 1: True}) == {
        "data": [
            {"key": "10", "val": [{"Port": "1", "Tagged": True}, {"Port": "2", "Tagged": False}]}
        ]
    }
    assert vlan_delete_body(10) == {"idx": ["10"]}
    assert lag_body(1, "lacp", {6, 5}, True) == {
        "idx": "1",
        "data": {"AggrMode": "lacp", "PortMembers": ["5", "6"]},
    }
    assert lag_body(1, "lacp", {6, 5}, False)["data"]["PortMembers"] == [5, 6]
    assert lag_delete_body(1) == {"idx": ["1"]}
