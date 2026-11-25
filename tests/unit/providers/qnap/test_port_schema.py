"""QNAP port settings: schema checks, the live parser, write data and the count_ports fix."""

from __future__ import annotations

from typing import Any

import pytest

from infrafoundry.providers.qnap.client import QnapApiDriftError
from infrafoundry.providers.qnap.schema import (
    DesiredPort,
    LivePort,
    check_resources,
    count_ports,
    desired_ports,
    parse_ports,
    port_body,
    port_changed_fields,
    port_matches,
    port_write_data,
)

from .config_fake import lag_row, port_row
from .conftest import port

pytestmark = pytest.mark.unit


def _errors(*resources: Any) -> list[str]:
    return [f.message for f in check_resources(list(resources))]


def _live(**overrides: Any) -> LivePort:
    return LivePort(5, port_row(**overrides))


def _want(**fields: Any) -> DesiredPort:
    return DesiredPort(5, "p5", **fields)


# -- schema


def test_valid_port_has_no_findings() -> None:
    resource = port(
        port=5,
        alias="spare-5",
        shutdown=False,
        speed="1G",
        duplex="full",
        flow_control=True,
        fec="auto",
        mtu=9000,
    )
    assert _errors(resource) == []
    [desired] = desired_ports([resource])
    assert desired == DesiredPort(5, "p5", "spare-5", False, "1G", "full", True, "auto", 9000)
    assert desired.key == (5,) and desired.type_name == "port"


@pytest.mark.parametrize(
    "config, text",
    [
        ({}, "missing required field(s): port"),
        ({"port": "lag1"}, "lagN is not supported"),
        ({"port": 0}, "'port' must be"),
        ({"port": True}, "'port' must be"),
        ({"port": 5, "absent": True}, "never created or deleted"),
        ({"port": 5, "colour": "red"}, "unknown field(s): colour"),
        ({"port": 5, "alias": 7}, "'alias' must be a string"),
        ({"port": 5, "shutdown": "no"}, "'shutdown' must be true or false"),
        ({"port": 5, "flow_control": 1}, "'flow_control' must be true or false"),
        ({"port": 5, "speed": "3G"}, "'speed' must be one of"),
        ({"port": 5, "fec": "x"}, "'fec' must be one of"),
        ({"port": 5, "mtu": 0}, "'mtu' must be a positive integer"),
        ({"port": 5, "mtu": "9000"}, "'mtu' must be a positive integer"),
        ({"port": 5, "duplex": "full"}, "needs a fixed 'speed'"),
        ({"port": 5, "duplex": "full", "speed": "auto"}, "needs a fixed 'speed'"),
        ({"port": 5, "duplex": "half", "speed": "1G"}, "only at speed 10M or 100M"),
        ({"port": 5, "duplex": "both", "speed": "10M"}, "'duplex' must be"),
    ],
)
def test_invalid_port_fields(config: dict[str, Any], text: str) -> None:
    [message] = _errors(port(**config))
    assert text in message


def test_half_duplex_is_allowed_at_100m() -> None:
    assert _errors(port(port=5, speed="100M", duplex="half")) == []


def test_duplicate_port_keys_are_an_error() -> None:
    messages = _errors(port("a", port=5, alias="x"), port("b", port=5, alias="y"))
    assert any("duplicate identity key (5,)" in m for m in messages)


def test_mixed_mtu_values_are_an_error() -> None:
    messages = _errors(port("a", port=1, mtu=9000), port("b", port=2, mtu=9000))
    assert messages == []
    [message] = _errors(port("a", port=1, mtu=9000), port("b", port=2, mtu=1500))
    assert "switch-wide" in message


def test_desired_ports_needs_a_key() -> None:
    with pytest.raises(ValueError, match="no usable port"):
        desired_ports([port(alias="x")])


# -- live parser and count_ports


def test_parse_ports_keeps_the_whole_row_and_lag_rows() -> None:
    reply = [
        {"key": "1", "val": port_row(Alias="a")},
        {"key": "9", "val": lag_row()},
    ]
    rows = parse_ports(reply)
    assert [r.key for r in rows] == [1, 9]
    assert not rows[0].is_lag and rows[1].is_lag
    assert rows[0].raw["MediaType"] == "Copper"


@pytest.mark.parametrize(
    "reply",
    [
        "x",
        [{"key": "1"}],
        [{"key": "x", "val": port_row()}],
        [{"key": "1", "val": port_row(Alias=3)}],
        [{"key": "1", "val": port_row(MTU="1500")}],
        [{"key": "1", "val": port_row(MTU=True)}],
        [{"key": "1", "val": {"Alias": ""}}],
    ],
)
def test_parse_ports_rejects_drift(reply: Any) -> None:
    with pytest.raises(QnapApiDriftError):
        parse_ports(reply)


def test_count_ports_ignores_lag_interface_rows() -> None:
    """Regression: LACP interface rows were counted as physical ports."""
    reply = [{"key": str(p), "val": port_row()} for p in range(1, 5)]
    reply += [{"key": "9", "val": lag_row()}, {"key": "10", "val": lag_row()}]
    assert count_ports(reply) == 4


def test_count_ports_rejects_a_non_list() -> None:
    with pytest.raises(QnapApiDriftError):
        count_ports({})


# -- matcher


def test_speed_auto_matches_on_auto_mode_not_on_speed() -> None:
    assert port_matches(_live(Speed="tenGB"), _want(speed="auto"))
    assert port_changed_fields(_live(AutoMode=False), _want(speed="auto")) == ("speed",)


def test_fixed_speed_needs_auto_mode_off_and_the_same_speed() -> None:
    fixed = _live(AutoMode=False, Speed="oneGB")
    assert port_matches(fixed, _want(speed="1G"))
    assert not port_matches(_live(AutoMode=True, Speed="oneGB"), _want(speed="1G"))
    assert not port_matches(fixed, _want(speed="10G"))


def test_only_declared_fields_are_compared() -> None:
    assert port_matches(_live(Alias="whatever", MTU=9000, Shutdown=True), _want())


def test_changed_fields_come_in_a_fixed_order() -> None:
    fields = port_changed_fields(
        _live(AutoMode=False, Speed="oneGB", FEC="auto"),
        _want(
            alias="x", shutdown=True, speed="10G", duplex="half", flow_control=True, fec="rs", mtu=9
        ),
    )
    assert fields == ("alias", "shutdown", "speed", "duplex", "flow_control", "fec", "mtu")


# -- write data


def test_alias_change_echoes_the_whole_row_and_keeps_auto_mode() -> None:
    live = _live(Speed="tenGB")
    data = port_write_data(live, _want(alias="spare-5"))
    assert data == {**live.raw, "Alias": "spare-5", "Speed": "autoNegMode", "AutoMode": True}


def test_speed_auto_sends_auto_neg_mode() -> None:
    data = port_write_data(_live(AutoMode=False, Speed="oneGB"), _want(speed="auto"))
    assert data["Speed"] == "autoNegMode" and data["AutoMode"] is True


def test_fixed_speed_from_auto_writes_full_duplex() -> None:
    data = port_write_data(_live(Fdx=False), _want(speed="10G"))
    assert data["Speed"] == "tenGB" and data["AutoMode"] is False and data["Fdx"] is True


def test_fixed_to_fixed_keeps_the_live_duplex_at_a_half_capable_speed() -> None:
    live = _live(AutoMode=False, Speed="tenMBPS", Fdx=False)
    assert port_write_data(live, _want(speed="100M"))["Fdx"] is False
    assert port_write_data(live, _want(speed="1G"))["Fdx"] is True


def test_declared_duplex_wins() -> None:
    live = _live(AutoMode=False, Speed="hundredMBPS", Fdx=True)
    assert port_write_data(live, _want(speed="100M", duplex="half"))["Fdx"] is False


def test_other_fields_use_the_wire_names_and_the_live_mtu_is_kept() -> None:
    live = _live(MTU=1500, FEC="auto")
    data = port_write_data(live, _want(shutdown=True, flow_control=True, fec="rs"))
    assert data["Shutdown"] is True and data["FC"] is True and data["FEC"] == "RS_FEC"
    assert data["MTU"] == 1500
    assert port_write_data(live, _want(mtu=9000))["MTU"] == 9000


def test_port_body_is_a_top_level_array() -> None:
    body = port_body([(5, {"Alias": "a"}), (6, {"Alias": "b"})])
    assert body == [{"idx": "5", "data": {"Alias": "a"}}, {"idx": "6", "data": {"Alias": "b"}}]
