"""Unit tests for ``SystemTuningService`` (#1149)."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.services.system_tuning import SystemTuningService

LIVE = {
    "sysctl": {
        "item": {
            "u1": {"tunable": "a.b", "value": "2", "descr": "d", "default_value": "1"},
            "u2": {"tunable": "c.d", "value": "5", "descr": "", "default_value": "5"},
        }
    }
}


@pytest.fixture
def service() -> SystemTuningService:
    svc = SystemTuningService(MagicMock())
    svc.system_client = MagicMock()
    return svc


def _res(items: list[dict[str, object]]) -> ResourceConfig:
    return ResourceConfig(
        name="settings", type="system.tuning", provider="opnsense", config={"items": items}
    )


def test_extract_live_tunables_by_name(service: SystemTuningService) -> None:
    live = service.extract_live_tunables(LIVE)
    assert live["a.b"] == {"uuid": "u1", "value": "2", "descr": "d", "default_value": "1"}
    assert set(live) == {"a.b", "c.d"}


@pytest.mark.parametrize("response", [{}, {"sysctl": []}, {"sysctl": {"item": []}}])
def test_extract_live_tunables_odd_shape(service: SystemTuningService, response: dict) -> None:  # type: ignore[type-arg]
    assert service.extract_live_tunables(response) == {}


def test_duplicate_live_name_keeps_first(
    service: SystemTuningService, caplog: pytest.LogCaptureFixture
) -> None:
    response = {
        "sysctl": {
            "item": {
                "u1": {"tunable": "x", "value": "1"},
                "u2": {"tunable": "x", "value": "2"},
            }
        }
    }
    with caplog.at_level(logging.WARNING):
        live = service.extract_live_tunables(response)
    assert live["x"]["uuid"] == "u1"
    assert "duplicate" in caplog.text


def test_build_desired_normalizes(service: SystemTuningService) -> None:
    desired = service.build_desired_tunables(
        _res(
            [
                {"tunable": "a", "value": True},
                {"tunable": "b", "value": False, "descr": " hi "},
                {"tunable": "c", "value": " 7 "},
            ]
        )
    )
    assert [d["value"] for d in desired] == ["1", "0", "7"]
    assert [d["descr"] for d in desired] == [None, "hi", None]


def test_build_desired_non_list(service: SystemTuningService) -> None:
    resource = ResourceConfig(
        name="settings", type="system.tuning", provider="opnsense", config={"items": "x"}
    )
    assert service.build_desired_tunables(resource) == []


class TestComputeChanges:
    def test_absent_is_add(self, service: SystemTuningService) -> None:
        adds, updates = service.compute_changes(
            [{"tunable": "n", "value": "1", "descr": None}], service.extract_live_tunables(LIVE)
        )
        assert adds == [{"tunable": "n", "value": "1", "descr": ""}]
        assert updates == []

    def test_differing_value_is_update_with_uuid(self, service: SystemTuningService) -> None:
        _, updates = service.compute_changes(
            [{"tunable": "a.b", "value": "9", "descr": None}], service.extract_live_tunables(LIVE)
        )
        assert updates == [{"uuid": "u1", "tunable": "a.b", "value": "9", "descr": "d"}]

    def test_same_value_omitted_descr_is_noop(self, service: SystemTuningService) -> None:
        assert service.compute_changes(
            [{"tunable": "a.b", "value": "2", "descr": None}], service.extract_live_tunables(LIVE)
        ) == ([], [])

    def test_differing_nonempty_descr_is_update(self, service: SystemTuningService) -> None:
        _, updates = service.compute_changes(
            [{"tunable": "a.b", "value": "2", "descr": "new"}], service.extract_live_tunables(LIVE)
        )
        assert updates[0]["descr"] == "new"

    def test_live_only_defaults_ignored(self, service: SystemTuningService) -> None:
        assert service.compute_changes([], service.extract_live_tunables(LIVE)) == ([], [])


def test_export_only_non_default(service: SystemTuningService) -> None:
    service.system_client.get_tunables.return_value = LIVE  # type: ignore[attr-defined]
    out = service.export_to_yaml()
    assert "a.b" in out
    assert "c.d" not in out
    assert "descr" in out


def test_export_empty(service: SystemTuningService) -> None:
    service.system_client.get_tunables.return_value = {}  # type: ignore[attr-defined]
    assert "a.b" not in service.export_to_yaml()


def test_reconfigure_delegates(service: SystemTuningService) -> None:
    service.system_client.reconfigure_tunables.return_value = {"status": "ok"}  # type: ignore[attr-defined]
    assert service.reconfigure() == {"status": "ok"}
