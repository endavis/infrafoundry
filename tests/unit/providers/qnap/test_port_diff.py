"""QNAP port diff, FEC rule, ordering, lock-out and executor/client plumbing."""

from __future__ import annotations

import pytest

from infrafoundry.providers.qnap.client import QnapClient
from infrafoundry.providers.qnap.components.diff import (
    UPDATE,
    Change,
    QnapPlanError,
    TypeDiff,
    check_port_fec,
    diff_ports,
)
from infrafoundry.providers.qnap.components.executor import execute_steps
from infrafoundry.providers.qnap.components.lockout import check_port_lockout, watched_ports
from infrafoundry.providers.qnap.components.ordering import Step, order_changes
from infrafoundry.providers.qnap.schema import DesiredPort, LivePort

from .config_fake import FakeQnapConfig, lag_row, port_row
from .conftest import settings_for
from .qnap_fake import ServedQnap

pytestmark = pytest.mark.unit


def _rows(count: int = 6, **overrides: dict[str, object]) -> list[LivePort]:
    rows = [LivePort(p, port_row(**overrides.get(str(p), {}))) for p in range(1, count + 1)]
    rows.append(LivePort(9, lag_row()))
    return rows


def _want(port: int, **fields: object) -> DesiredPort:
    return DesiredPort(port, f"p{port}", **fields)  # type: ignore[arg-type]


# -- diff


def test_converged_port_gives_no_change_even_with_a_negotiated_speed() -> None:
    rows = [LivePort(5, port_row(Alias="spare-5", Speed="tenGB"))]
    assert diff_ports([_want(5, alias="spare-5", speed="auto")], rows).is_empty


def test_alias_change_is_one_update_with_the_whole_row() -> None:
    diff = diff_ports([_want(5, alias="spare-5")], _rows())
    [change] = diff.changes
    assert (change.kind, change.key, change.fields) == (UPDATE, (5,), ("alias",))
    assert change.after["Alias"] == "spare-5" and change.after["MediaType"] == "Copper"


def test_notes_carry_field_names_never_alias_text() -> None:
    [change] = diff_ports([_want(5, alias="secret-name", shutdown=True)], _rows()).changes
    assert change.notes == ("set alias, shutdown",)
    assert "secret-name" not in " ".join(change.notes)


def test_undeclared_ports_are_not_reported() -> None:
    diff = diff_ports([_want(5, alias="x")], _rows())
    assert diff.unmanaged == [] and len(diff.changes) == 1


@pytest.mark.parametrize("port", [7, 9])
def test_unknown_port_and_lag_row_raise(port: int) -> None:
    rows = _rows()
    if port == 7:
        with pytest.raises(QnapPlanError, match="does not exist"):
            diff_ports([_want(7, alias="x")], rows)
    else:
        with pytest.raises(QnapPlanError, match="LACP interface"):
            diff_ports([_want(9, alias="x")], rows)


def test_fec_on_a_port_without_fec_raises() -> None:
    with pytest.raises(QnapPlanError, match="no FEC"):
        diff_ports([_want(5, fec="auto")], _rows())


def _fec_rows(on: int) -> list[LivePort]:
    return [LivePort(p, port_row(FEC="auto" if p <= on else "none")) for p in range(1, 5)]


def test_fec_rule_needs_two_enabled_ports_after_a_change() -> None:
    rows = _fec_rows(on=2)
    check_port_fec(diff_ports([_want(3, fec="rs")], rows), rows)  # 3 on: fine
    with pytest.raises(QnapPlanError, match="at least two"):
        check_port_fec(diff_ports([_want(1, fec="none")], rows), rows)


def test_fec_rule_ignores_plans_without_fec_and_switches_without_fec() -> None:
    rows = _fec_rows(on=0)
    check_port_fec(diff_ports([_want(1, alias="x")], rows), rows)
    check_port_fec(None, rows)
    plain = _rows()
    check_port_fec(diff_ports([_want(1, alias="x")], plain), plain)


# -- ordering


def _port_diff(*ports: tuple[int, tuple[str, ...]]) -> TypeDiff:
    return TypeDiff(
        "port",
        [
            Change(UPDATE, "port", (p,), f"p{p}", after={"MTU": 1500}, fields=fields)
            for p, fields in ports
        ],
    )


def test_port_steps_come_last_with_mtu_in_phase_i_and_watched_ports_last() -> None:
    diff = _port_diff((1, ("alias",)), (2, ("alias",)), (3, ("mtu", "alias")), (4, ("alias",)))
    steps = order_changes(None, None, {}, {}, 1, port_diff=diff, last_ports={1})
    assert [(s.phase, s.key[0]) for s in steps] == [("H", 2), ("H", 4), ("H", 1), ("I", 3)]
    for step in steps:
        assert step.method == "PUT" and step.path == "portlist" and step.timeout == 60
        assert isinstance(step.body, list) and len(step.body) == 1
        assert step.body[0]["idx"] == str(step.key[0])


# -- lock-out


def _change(port: int, fields: tuple[str, ...], **after: object) -> Change:
    return Change(UPDATE, "port", (port,), f"p{port}", after=after, fields=fields)


def test_watched_ports_use_protected_then_the_management_vlan() -> None:
    lags = {1: {5, 6}}
    assert watched_ports({9}, {1, 2}, lags, 8) == {5, 6}
    assert watched_ports({3}, {1, 2}, lags, 8) == {3}
    assert watched_ports(set(), {1, 9}, lags, 8) == {1, 5, 6}


@pytest.mark.parametrize(
    "fields, after",
    [(("shutdown",), {"Shutdown": True}), (("speed",), {}), (("duplex",), {}), (("fec",), {})],
)
def test_watched_port_risks_are_refused(fields: tuple[str, ...], after: dict[str, object]) -> None:
    check = check_port_lockout([_change(1, fields, **after)], {1}, False)
    assert len(check.refusals) == 1 and "port 1" in check.refusals[0]
    allowed = check_port_lockout([_change(1, fields, **after)], {1}, True)
    assert not allowed.refusals and allowed.warnings[0].startswith("lock-out risk allowed")


def test_safe_changes_pass_on_watched_ports_and_risks_on_other_ports_pass() -> None:
    changes = [
        _change(1, ("alias", "flow_control")),
        _change(1, ("shutdown",), Shutdown=False),
        _change(2, ("shutdown", "speed", "fec"), Shutdown=True),
    ]
    check = check_port_lockout(changes, {1}, False)
    assert not check.refusals and not check.warnings


def test_any_mtu_change_is_a_risk() -> None:
    check = check_port_lockout([_change(4, ("mtu",))], set(), False)
    assert len(check.refusals) == 1 and "switch-wide" in check.refusals[0]


# -- executor and client


def test_executor_passes_the_timeout_and_the_list_body() -> None:
    fake = FakeQnapConfig()
    body = [{"idx": "5", "data": port_row(Alias="x", AutoMode=False)}]
    step = Step("H", UPDATE, "port", (5,), "p5", "PUT", "portlist", body, timeout=60)
    assert execute_steps(fake, [step]).success
    assert fake.timeouts == [("portlist", 60)] and fake.port_writes() == [body]


def test_executor_refuses_a_list_body_for_post() -> None:
    step = Step("A", "create", "vlan", (1,), "v", "POST", "vlan", [])
    with pytest.raises(ValueError, match="object body"):
        execute_steps(FakeQnapConfig(), [step])


def test_client_sends_a_list_body_unchanged(served_qnap: ServedQnap) -> None:
    served_qnap.state.results["portlist"] = []
    client = QnapClient(settings_for(served_qnap))
    client.login()
    body = [{"idx": "5", "data": {"Alias": "x"}}]
    client.put("portlist", body, timeout=60)
    sent = [r for r in served_qnap.state.requests if r[1] == "/api/v1/portlist"]
    assert [(r[0], r[3]) for r in sent] == [("PUT", body)]
