"""Unit tests for ``SystemTuningManager`` (#806)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from infrafoundry.core.exceptions import InvalidConfigurationError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.components.system_tuning import (
    SystemTuningManager,
)

SERVICE_PATH = "infrafoundry.providers.opnsense.components.system_tuning.SystemTuningService"


def _resource(*, items: list[dict[str, str]] | None = None) -> ResourceConfig:
    return ResourceConfig(
        name="settings",
        type="system.tuning",
        provider="opnsense",
        config={"items": items or []},
    )


def _make_service_mock(*, live_items: list[dict[str, str]] | None = None) -> MagicMock:
    service = MagicMock()
    service.get_settings.return_value = {"sysctl": {"items": live_items or []}}
    service.extract_tuning_fields.side_effect = lambda response: {
        "items": response.get("sysctl", {}).get("items", []),
    }
    service.build_desired_tuning_fields.side_effect = lambda resource: {
        "items": resource.config.get("items", []),
    }
    service.set_settings.return_value = {"result": "saved"}
    return service


class TestPlan:
    def test_plan_no_change(self, tmp_path: Path) -> None:
        manager = SystemTuningManager(tmp_path)
        items = [{"tunable": "kern.maxfiles", "value": "20000", "descr": ""}]
        service = _make_service_mock(live_items=items)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            diff = manager.plan("test-env", [_resource(items=items)])
        assert diff.is_empty

    def test_plan_update(self, tmp_path: Path) -> None:
        manager = SystemTuningManager(tmp_path)
        live_items: list[dict[str, str]] = []
        new_items = [{"tunable": "kern.maxfiles", "value": "20000", "descr": ""}]
        service = _make_service_mock(live_items=live_items)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            diff = manager.plan("test-env", [_resource(items=new_items)])
        assert len(diff.updates) == 1

    def test_plan_raises_on_multiple_resources(self, tmp_path: Path) -> None:
        manager = SystemTuningManager(tmp_path)
        with pytest.raises(InvalidConfigurationError):
            manager.plan("test-env", [_resource(), _resource()])


class TestApply:
    def test_apply_no_change(self, tmp_path: Path) -> None:
        manager = SystemTuningManager(tmp_path)
        items = [{"tunable": "kern.maxfiles", "value": "20000", "descr": ""}]
        service = _make_service_mock(live_items=items)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            result = manager.apply("test-env", [_resource(items=items)])
        service.set_settings.assert_not_called()
        assert result["resources_updated"] == 0

    def test_apply_update(self, tmp_path: Path) -> None:
        manager = SystemTuningManager(tmp_path)
        new_items = [{"tunable": "kern.maxfiles", "value": "20000", "descr": ""}]
        service = _make_service_mock(live_items=[])
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            result = manager.apply("test-env", [_resource(items=new_items)])
        service.set_settings.assert_called_once()
        payload = service.set_settings.call_args.args[0]
        assert "sysctl" in payload
        assert result["resources_updated"] == 1


class TestDestroy:
    def test_destroy_noop(self, tmp_path: Path) -> None:
        manager = SystemTuningManager(tmp_path)
        result = manager.destroy("test-env", [_resource()])
        assert result["resources_destroyed"] == 0


class TestGetResourceIds:
    def test_get_resource_ids(self, tmp_path: Path) -> None:
        manager = SystemTuningManager(tmp_path)
        result = manager.get_resource_ids("test-env", [_resource()])
        assert result == {"settings": "global"}
