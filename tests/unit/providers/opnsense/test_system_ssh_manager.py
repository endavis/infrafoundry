"""Unit tests for ``SystemSshManager`` (#806)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from infrafoundry.core.exceptions import InvalidConfigurationError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.components.system_ssh import SystemSshManager

SERVICE_PATH = "infrafoundry.providers.opnsense.components.system_ssh.SystemSshService"


def _resource(
    *,
    enabled: str = "enabled",
    group: str = "admins",
    interfaces: list[str] | None = None,
) -> ResourceConfig:
    return ResourceConfig(
        name="settings",
        type="system.ssh",
        provider="opnsense",
        config={
            "enabled": enabled,
            "group": group,
            "interfaces": interfaces or ["lan"],
        },
    )


def _make_service_mock(*, live_fields: dict[str, Any] | None = None) -> MagicMock:
    live = live_fields or {}
    service = MagicMock()
    service.get_settings.return_value = {"ssh": live}
    service.extract_ssh_fields.side_effect = lambda response: {
        "enabled": response.get("ssh", {}).get("enabled", ""),
        "group": response.get("ssh", {}).get("group", ""),
        "interfaces": response.get("ssh", {}).get("interfaces", []),
    }
    service.build_desired_ssh_fields.side_effect = lambda resource: {
        "enabled": resource.config.get("enabled", ""),
        "group": resource.config.get("group", ""),
        "interfaces": resource.config.get("interfaces", []),
    }
    service.set_settings.return_value = {"result": "saved"}
    return service


class TestPlan:
    def test_plan_no_change(self, tmp_path: Path) -> None:
        manager = SystemSshManager(tmp_path)
        service = _make_service_mock(
            live_fields={"enabled": "enabled", "group": "admins", "interfaces": ["lan"]}
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            diff = manager.plan("test-env", [_resource()])
        assert diff.is_empty

    def test_plan_update(self, tmp_path: Path) -> None:
        manager = SystemSshManager(tmp_path)
        service = _make_service_mock(
            live_fields={"enabled": "", "group": "admins", "interfaces": ["lan"]}
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            diff = manager.plan("test-env", [_resource()])
        assert len(diff.updates) == 1
        assert diff.updates[0]["enabled"] == "enabled"

    def test_plan_raises_on_multiple_resources(self, tmp_path: Path) -> None:
        manager = SystemSshManager(tmp_path)
        with pytest.raises(InvalidConfigurationError):
            manager.plan("test-env", [_resource(), _resource()])


class TestApply:
    def test_apply_no_change(self, tmp_path: Path) -> None:
        manager = SystemSshManager(tmp_path)
        service = _make_service_mock(
            live_fields={"enabled": "enabled", "group": "admins", "interfaces": ["lan"]}
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            result = manager.apply("test-env", [_resource()])
        service.set_settings.assert_not_called()
        assert result["resources_updated"] == 0

    def test_apply_update(self, tmp_path: Path) -> None:
        manager = SystemSshManager(tmp_path)
        service = _make_service_mock(
            live_fields={"enabled": "", "group": "admins", "interfaces": ["lan"]}
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            result = manager.apply("test-env", [_resource()])
        service.set_settings.assert_called_once()
        payload = service.set_settings.call_args.args[0]
        assert "ssh" in payload
        assert payload["ssh"]["enabled"] == "enabled"
        assert result["resources_updated"] == 1
        outcome = result["resource_outcomes"][0]
        assert outcome.action == "update"


class TestDestroy:
    def test_destroy_noop(self, tmp_path: Path) -> None:
        manager = SystemSshManager(tmp_path)
        result = manager.destroy("test-env", [_resource()])
        assert result["resources_destroyed"] == 0


class TestGetResourceIds:
    def test_get_resource_ids(self, tmp_path: Path) -> None:
        manager = SystemSshManager(tmp_path)
        result = manager.get_resource_ids("test-env", [_resource()])
        assert result == {"settings": "global"}
