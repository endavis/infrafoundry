"""Unit tests for ``SystemHostnameManager`` (#806).

Coverage:
    - plan emits an empty diff when live matches desired.
    - plan emits one update entry when a single field changes.
    - apply skips set_general_settings when the singleton is in sync.
    - apply calls set_general_settings with the desired payload on drift.
    - destroy is a no-op (returns ``resources_destroyed=0``).
    - get_resource_ids returns ``{"settings": "global"}``.
    - plan raises ``InvalidConfigurationError`` if not exactly one resource.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from infrafoundry.core.exceptions import InvalidConfigurationError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.components.system_hostname import (
    SystemHostnameManager,
)

SERVICE_PATH = "infrafoundry.providers.opnsense.components.system_hostname.SystemHostnameService"


def _resource(
    *,
    hostname: str = "opnsense-a",
    domain: str = "endavis.net",
    timezone: str = "Etc/UTC",
    language: str = "en_US",
) -> ResourceConfig:
    return ResourceConfig(
        name="settings",
        type="system.hostname",
        provider="opnsense",
        config={
            "hostname": hostname,
            "domain": domain,
            "timezone": timezone,
            "language": language,
        },
    )


def _make_service_mock(*, live_fields: dict[str, Any] | None = None) -> MagicMock:
    service = MagicMock()
    service.get_settings.return_value = {"general": live_fields or {}}
    service.extract_hostname_fields.side_effect = lambda response: response.get("general", {})
    service.build_desired_hostname_fields.side_effect = lambda resource: {
        "hostname": resource.config.get("hostname", ""),
        "domain": resource.config.get("domain", ""),
        "timezone": resource.config.get("timezone", ""),
        "language": resource.config.get("language", ""),
    }
    service.set_settings.return_value = {"result": "saved"}
    return service


class TestPlan:
    def test_plan_no_change(self, tmp_path: Path) -> None:
        manager = SystemHostnameManager(tmp_path)
        live = {
            "hostname": "opnsense-a",
            "domain": "endavis.net",
            "timezone": "Etc/UTC",
            "language": "en_US",
        }
        service = _make_service_mock(live_fields=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            diff = manager.plan("test-env", [_resource()])
        assert diff.is_empty
        assert diff.updates == []

    def test_plan_update(self, tmp_path: Path) -> None:
        manager = SystemHostnameManager(tmp_path)
        live = {
            "hostname": "old-host",
            "domain": "endavis.net",
            "timezone": "Etc/UTC",
            "language": "en_US",
        }
        service = _make_service_mock(live_fields=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            diff = manager.plan("test-env", [_resource()])
        assert not diff.is_empty
        assert len(diff.updates) == 1
        update = diff.updates[0]
        assert update["hostname"] == "opnsense-a"

    def test_plan_raises_on_multiple_resources(self, tmp_path: Path) -> None:
        manager = SystemHostnameManager(tmp_path)
        with pytest.raises(InvalidConfigurationError):
            manager.plan("test-env", [_resource(), _resource()])

    def test_plan_raises_on_no_resources(self, tmp_path: Path) -> None:
        manager = SystemHostnameManager(tmp_path)
        with pytest.raises(InvalidConfigurationError):
            manager.plan("test-env", [])


class TestApply:
    def test_apply_no_change(self, tmp_path: Path) -> None:
        manager = SystemHostnameManager(tmp_path)
        live = {
            "hostname": "opnsense-a",
            "domain": "endavis.net",
            "timezone": "Etc/UTC",
            "language": "en_US",
        }
        service = _make_service_mock(live_fields=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            result = manager.apply("test-env", [_resource()])
        service.set_settings.assert_not_called()
        assert result["resources_updated"] == 0

    def test_apply_update(self, tmp_path: Path) -> None:
        manager = SystemHostnameManager(tmp_path)
        live = {
            "hostname": "old-host",
            "domain": "endavis.net",
            "timezone": "Etc/UTC",
            "language": "en_US",
        }
        service = _make_service_mock(live_fields=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            result = manager.apply("test-env", [_resource()])
        service.set_settings.assert_called_once()
        payload = service.set_settings.call_args.args[0]
        assert "general" in payload
        assert payload["general"]["hostname"] == "opnsense-a"
        assert result["resources_updated"] == 1
        outcome = result["resource_outcomes"][0]
        assert outcome.action == "update"
        assert outcome.resource_name == "settings"


class TestDestroy:
    def test_destroy_noop(self, tmp_path: Path) -> None:
        manager = SystemHostnameManager(tmp_path)
        result = manager.destroy("test-env", [_resource()])
        assert result["resources_destroyed"] == 0
        assert result["resource_outcomes"] == []


class TestGetResourceIds:
    def test_get_resource_ids(self, tmp_path: Path) -> None:
        manager = SystemHostnameManager(tmp_path)
        result = manager.get_resource_ids("test-env", [_resource()])
        assert result == {"settings": "global"}
