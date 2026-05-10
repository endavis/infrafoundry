"""Unit tests for ``SystemWebguiManager`` (#806)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from infrafoundry.core.exceptions import InvalidConfigurationError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.components.system_webgui import (
    SystemWebguiManager,
)

SERVICE_PATH = "infrafoundry.providers.opnsense.components.system_webgui.SystemWebguiService"


def _resource(
    *,
    protocol: str = "https",
    port: str = "443",
    ssl_certref: str = "abc123",
) -> ResourceConfig:
    return ResourceConfig(
        name="settings",
        type="system.webgui",
        provider="opnsense",
        config={
            "protocol": protocol,
            "port": port,
            "ssl_certref": ssl_certref,
        },
    )


def _make_service_mock(*, live_fields: dict[str, Any] | None = None) -> MagicMock:
    live = live_fields or {}
    service = MagicMock()
    service.get_settings.return_value = {"webgui": live}
    service.extract_webgui_fields.side_effect = lambda response: {
        "protocol": response.get("webgui", {}).get("protocol", ""),
        "port": response.get("webgui", {}).get("port", ""),
        "ssl_certref": response.get("webgui", {}).get("ssl_certref", ""),
    }
    service.build_desired_webgui_fields.side_effect = lambda resource: {
        "protocol": resource.config.get("protocol", ""),
        "port": resource.config.get("port", ""),
        "ssl_certref": resource.config.get("ssl_certref", ""),
    }
    service.set_settings.return_value = {"result": "saved"}
    return service


class TestPlan:
    def test_plan_no_change(self, tmp_path: Path) -> None:
        manager = SystemWebguiManager(tmp_path)
        service = _make_service_mock(
            live_fields={"protocol": "https", "port": "443", "ssl_certref": "abc123"}
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            diff = manager.plan("test-env", [_resource()])
        assert diff.is_empty

    def test_plan_update(self, tmp_path: Path) -> None:
        manager = SystemWebguiManager(tmp_path)
        service = _make_service_mock(
            live_fields={"protocol": "http", "port": "443", "ssl_certref": "abc123"}
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            diff = manager.plan("test-env", [_resource()])
        assert len(diff.updates) == 1
        assert diff.updates[0]["protocol"] == "https"

    def test_plan_raises_on_multiple_resources(self, tmp_path: Path) -> None:
        manager = SystemWebguiManager(tmp_path)
        with pytest.raises(InvalidConfigurationError):
            manager.plan("test-env", [_resource(), _resource()])


class TestApply:
    def test_apply_no_change(self, tmp_path: Path) -> None:
        manager = SystemWebguiManager(tmp_path)
        service = _make_service_mock(
            live_fields={"protocol": "https", "port": "443", "ssl_certref": "abc123"}
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            result = manager.apply("test-env", [_resource()])
        service.set_settings.assert_not_called()
        assert result["resources_updated"] == 0

    def test_apply_update(self, tmp_path: Path) -> None:
        manager = SystemWebguiManager(tmp_path)
        service = _make_service_mock(
            live_fields={"protocol": "http", "port": "443", "ssl_certref": "abc123"}
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            result = manager.apply("test-env", [_resource()])
        service.set_settings.assert_called_once()
        payload = service.set_settings.call_args.args[0]
        assert "webgui" in payload
        assert payload["webgui"]["protocol"] == "https"
        assert result["resources_updated"] == 1


class TestDestroy:
    def test_destroy_noop(self, tmp_path: Path) -> None:
        manager = SystemWebguiManager(tmp_path)
        result = manager.destroy("test-env", [_resource()])
        assert result["resources_destroyed"] == 0


class TestGetResourceIds:
    def test_get_resource_ids(self, tmp_path: Path) -> None:
        manager = SystemWebguiManager(tmp_path)
        result = manager.get_resource_ids("test-env", [_resource()])
        assert result == {"settings": "global"}
