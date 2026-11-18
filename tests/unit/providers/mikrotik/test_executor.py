"""Tests for the step executor against the in-memory fake device."""

import pytest

from infrafoundry.providers.mikrotik.client import RouterOSAPIError, RouterOSConnectionError
from infrafoundry.providers.mikrotik.components.executor import execute_steps
from infrafoundry.providers.mikrotik.components.ordering import Step

from .conftest import FakeRouterOS


def _step(kind: str, type_name: str, res: str, live_id: str | None = None, **body: str) -> Step:
    return Step("B", kind, type_name, (res,), res, live_id, body)


def test_calls_follow_step_order(wan_edge: FakeRouterOS) -> None:
    steps = [
        _step("create", "interface.bridge", "br2", name="br2"),
        _step("update", "interface.bridge", "bridge", "*6", comment="x"),
        _step("delete", "interface.vlan", "vlan99", "*7"),
    ]

    result = execute_steps(wan_edge, steps)

    assert result.success and result.completed == steps
    assert [c[:2] for c in wan_edge.writes()] == [
        ("PUT", "interface/bridge"),
        ("PATCH", "interface/bridge/*6"),
        ("DELETE", "interface/vlan/*7"),
    ]


def test_update_of_a_created_row_uses_the_put_id(factory: FakeRouterOS) -> None:
    steps = [
        _step("create", "interface.bridge", "br2", name="br2"),
        _step("update", "interface.bridge", "br2", None, **{"vlan-filtering": "yes"}),
    ]

    result = execute_steps(factory, steps)

    assert result.success
    assert factory.writes()[1][:2] == ("PATCH", "interface/bridge/*100")


def test_put_without_id_falls_back_to_a_re_read(factory: FakeRouterOS) -> None:
    factory.put_returns_id = False
    steps = [
        _step("create", "interface.bridge", "br2", name="br2"),
        _step("update", "interface.bridge", "br2", None, **{"vlan-filtering": "yes"}),
    ]

    result = execute_steps(factory, steps)

    assert result.success
    assert factory.writes()[1][:2] == ("PATCH", "interface/bridge/*100")
    assert factory.calls.count(("GET", "interface/bridge")) == 1


def test_unresolvable_id_fails_the_step(factory: FakeRouterOS) -> None:
    step = _step("update", "interface.bridge", "missing", None, comment="x")

    result = execute_steps(factory, [step])

    assert result.failed == step and result.completed == []
    assert result.error is not None and "missing" in result.error
    assert factory.writes() == []


@pytest.mark.parametrize(
    ("error", "lost"),
    [(RouterOSAPIError("no such item", 400), False), (RouterOSConnectionError("gone"), True)],
)
def test_stops_at_the_first_error(
    factory: FakeRouterOS, error: RouterOSAPIError | RouterOSConnectionError, lost: bool
) -> None:
    steps = [
        _step("create", "interface.bridge", "a", name="a"),
        _step("create", "interface.vlan", "b", name="b"),
        _step("create", "ip.address", "c", address="198.51.100.1/24"),
    ]
    factory.errors[("PUT", "interface/vlan")] = error

    result = execute_steps(factory, steps)

    assert result.completed == steps[:1]
    assert result.failed == steps[1]
    assert result.connection_lost is lost
    assert [c[1] for c in factory.writes()] == ["interface/bridge", "interface/vlan"]
