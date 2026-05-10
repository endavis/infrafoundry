"""Unit tests for ``SystemDnsManager`` (#806).

Coverage:
    - plan emits an empty diff when live matches desired.
    - plan emits one update entry when a single field changes.
    - apply skips set_general_settings when the singleton is in sync.
    - apply calls set_general_settings with the desired payload on drift.
    - destroy is a no-op.
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
from infrafoundry.providers.opnsense.components.system_dns import SystemDnsManager

SERVICE_PATH = "infrafoundry.providers.opnsense.components.system_dns.SystemDnsService"


def _resource(
    *,
    dns_servers: list[str] | None = None,
    dns_allow_override: str = "1",
    dns_allow_override_exclude: list[str] | None = None,
    dns_gateways: dict[str, str] | None = None,
) -> ResourceConfig:
    return ResourceConfig(
        name="settings",
        type="system.dns",
        provider="opnsense",
        config={
            "dns_servers": dns_servers if dns_servers is not None else ["9.9.9.9", "1.1.1.1"],
            "dns_allow_override": dns_allow_override,
            "dns_allow_override_exclude": dns_allow_override_exclude or [],
            "dns_gateways": dns_gateways or {},
        },
    )


def _make_service_mock(*, live_fields: dict[str, Any] | None = None) -> MagicMock:
    service = MagicMock()
    service.get_settings.return_value = {"general": live_fields or {}}
    service.extract_dns_fields.side_effect = lambda response: {
        "dns_servers": response.get("general", {}).get("dns_servers", []),
        "dns_allow_override": response.get("general", {}).get("dns_allow_override", ""),
        "dns_allow_override_exclude": response.get("general", {}).get(
            "dns_allow_override_exclude", []
        ),
        "dns_gateways": response.get("general", {}).get("dns_gateways", {}),
    }
    service.build_desired_dns_fields.side_effect = lambda resource: {
        "dns_servers": resource.config.get("dns_servers", []),
        "dns_allow_override": resource.config.get("dns_allow_override", ""),
        "dns_allow_override_exclude": resource.config.get("dns_allow_override_exclude", []),
        "dns_gateways": resource.config.get("dns_gateways", {}),
    }
    service.set_settings.return_value = {"result": "saved"}
    return service


class TestPlan:
    def test_plan_no_change(self, tmp_path: Path) -> None:
        manager = SystemDnsManager(tmp_path)
        live = {
            "dns_servers": ["9.9.9.9", "1.1.1.1"],
            "dns_allow_override": "1",
            "dns_allow_override_exclude": [],
            "dns_gateways": {},
        }
        service = _make_service_mock(live_fields=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            diff = manager.plan("test-env", [_resource()])
        assert diff.is_empty

    def test_plan_update(self, tmp_path: Path) -> None:
        manager = SystemDnsManager(tmp_path)
        live = {
            "dns_servers": ["8.8.8.8"],
            "dns_allow_override": "1",
            "dns_allow_override_exclude": [],
            "dns_gateways": {},
        }
        service = _make_service_mock(live_fields=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            diff = manager.plan("test-env", [_resource()])
        assert len(diff.updates) == 1
        update = diff.updates[0]
        assert update["dns_servers"] == ["9.9.9.9", "1.1.1.1"]

    def test_plan_raises_on_multiple_resources(self, tmp_path: Path) -> None:
        manager = SystemDnsManager(tmp_path)
        with pytest.raises(InvalidConfigurationError):
            manager.plan("test-env", [_resource(), _resource()])


class TestApply:
    def test_apply_no_change(self, tmp_path: Path) -> None:
        manager = SystemDnsManager(tmp_path)
        live = {
            "dns_servers": ["9.9.9.9", "1.1.1.1"],
            "dns_allow_override": "1",
            "dns_allow_override_exclude": [],
            "dns_gateways": {},
        }
        service = _make_service_mock(live_fields=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            result = manager.apply("test-env", [_resource()])
        service.set_settings.assert_not_called()
        assert result["resources_updated"] == 0

    def test_apply_update(self, tmp_path: Path) -> None:
        manager = SystemDnsManager(tmp_path)
        live = {
            "dns_servers": ["8.8.8.8"],
            "dns_allow_override": "1",
            "dns_allow_override_exclude": [],
            "dns_gateways": {},
        }
        service = _make_service_mock(live_fields=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            result = manager.apply("test-env", [_resource()])
        service.set_settings.assert_called_once()
        assert result["resources_updated"] == 1
        outcome = result["resource_outcomes"][0]
        assert outcome.action == "update"
        assert outcome.resource_name == "settings"


class TestDestroy:
    def test_destroy_noop(self, tmp_path: Path) -> None:
        manager = SystemDnsManager(tmp_path)
        result = manager.destroy("test-env", [_resource()])
        assert result["resources_destroyed"] == 0


class TestGetResourceIds:
    def test_get_resource_ids(self, tmp_path: Path) -> None:
        manager = SystemDnsManager(tmp_path)
        result = manager.get_resource_ids("test-env", [_resource()])
        assert result == {"settings": "global"}
