"""QNAP executor: ordered writes, first error stops, no body in logs."""

from __future__ import annotations

import logging

import pytest

from infrafoundry.providers.qnap.client import QnapApiDriftError, QnapApiError, QnapUnreachableError
from infrafoundry.providers.qnap.components.executor import execute_steps
from infrafoundry.providers.qnap.components.ordering import Step

from .config_fake import FakeQnapConfig

pytestmark = pytest.mark.unit


def _vlan_step(vid: int, method: str = "POST", name: str = "v") -> Step:
    body = {"data": [{"key": str(vid), "val": [{"Port": "1", "Tagged": True}]}]}
    return Step("C", "create", "vlan", (vid,), name, method, "vlan", body)


def test_runs_every_step_in_order() -> None:
    fake = FakeQnapConfig()
    result = execute_steps(
        fake,
        [
            _vlan_step(30),
            _vlan_step(40),
            _vlan_step(30, "PUT"),
            Step("F", "delete", "vlan", (40,), "d", "DELETE", "vlan", {"idx": ["40"]}),
        ],
    )
    assert result.success and len(result.completed) == 4
    assert [m for m, *_ in fake.writes()] == ["POST", "POST", "PUT", "DELETE"]
    assert 40 not in fake.vlans


def test_stops_at_the_first_api_error_and_records_what_ran() -> None:
    fake = FakeQnapConfig()
    fake.fail_write[1] = QnapApiError("vlan", 400)
    result = execute_steps(fake, [_vlan_step(30), _vlan_step(40), _vlan_step(50)])
    assert not result.success and not result.connection_lost
    assert [s.key for s in result.completed] == [(30,)]
    assert result.failed is not None and result.failed.key == (40,)
    assert "error code 400" in (result.error or "")
    assert len(fake.writes()) == 2


def test_drift_error_stops_the_run() -> None:
    fake = FakeQnapConfig()
    fake.fail_write[0] = QnapApiDriftError("shape")
    result = execute_steps(fake, [_vlan_step(30), _vlan_step(40)])
    assert not result.success and not result.completed


def test_unreachable_switch_sets_connection_lost() -> None:
    fake = FakeQnapConfig()
    fake.fail_write[0] = QnapUnreachableError("gone")
    result = execute_steps(fake, [_vlan_step(30)])
    assert result.connection_lost and result.failed is not None


def test_unknown_method_is_a_programming_error() -> None:
    with pytest.raises(ValueError):
        execute_steps(FakeQnapConfig(), [_vlan_step(30, "PATCH")])


def test_log_lines_carry_no_body(caplog: pytest.LogCaptureFixture) -> None:
    fake = FakeQnapConfig()
    with caplog.at_level(logging.INFO, logger="infrafoundry.providers.qnap.components.executor"):
        execute_steps(fake, [_vlan_step(30, name="my-vlan")])
    assert "my-vlan" in caplog.text
    assert "Tagged" not in caplog.text and '"Port"' not in caplog.text
