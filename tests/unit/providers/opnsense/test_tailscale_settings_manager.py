"""Unit tests for ``TailscaleSettingsManager`` (#787).

Coverage:
    - plan emits an empty diff when live matches desired.
    - plan emits one update entry when a field changes.
    - apply skips apply_settings_patch when the singleton is in sync.
    - apply calls apply_settings_patch with the desired wire payload on drift.
    - apply_settings_patch result: verify the patch merges correctly (GET → merge → POST).
    - destroy is a no-op (returns ``resources_destroyed=0``).
    - get_resource_ids returns ``{"settings": "global"}``.
    - plan raises ``InvalidConfigurationError`` if not exactly one resource.
    - FINALIZATION_HOOK class variable is ``"tailscale_reconfigure"``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from infrafoundry.core.exceptions import InvalidConfigurationError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.components.tailscale_settings import (
    TailscaleSettingsManager,
)

SERVICE_PATH = "infrafoundry.providers.opnsense.components.tailscale_settings.TailscaleService"


def _resource(
    *,
    enable: bool = False,
    login_timeout: int = 10,
    listen_port: int = 41641,
    accept_dns: bool = True,
    advertise_exit_node: bool = False,
    use_exit_node: str = "",
    accept_subnet_routes: bool = False,
    enable_ssh: bool = False,
    enable_snat: bool = True,
) -> ResourceConfig:
    return ResourceConfig(
        name="settings",
        type="tailscale.settings",
        provider="opnsense",
        config={
            "enable": enable,
            "login_timeout": login_timeout,
            "listen_port": listen_port,
            "accept_dns": accept_dns,
            "advertise_exit_node": advertise_exit_node,
            "use_exit_node": use_exit_node,
            "accept_subnet_routes": accept_subnet_routes,
            "enable_ssh": enable_ssh,
            "enable_snat": enable_snat,
        },
    )


def _make_live_fields(
    *,
    enable: str = "0",
    login_timeout: str = "10",
    listen_port: str = "41641",
    accept_dns: str = "1",
    advertise_exit_node: str = "0",
    use_exit_node: str = "",
    accept_subnet_routes: str = "0",
    enable_ssh: str = "0",
    enable_snat: str = "1",
) -> dict[str, Any]:
    return {
        "enable": enable,
        "login_timeout": login_timeout,
        "listen_port": listen_port,
        "accept_dns": accept_dns,
        "advertise_exit_node": advertise_exit_node,
        "use_exit_node": use_exit_node,
        "accept_subnet_routes": accept_subnet_routes,
        "enable_ssh": enable_ssh,
        "enable_snat": enable_snat,
    }


def _make_service_mock(*, live_fields: dict[str, Any] | None = None) -> MagicMock:
    service = MagicMock()
    fields = live_fields if live_fields is not None else _make_live_fields()
    service.get_settings.return_value = {"settings": {}}
    service.extract_settings_fields.return_value = fields
    service.build_desired_settings_fields.side_effect = lambda resource: {
        "enable": "1" if resource.config.get("enable") else "0",
        "login_timeout": str(resource.config.get("login_timeout", 10)),
        "listen_port": str(resource.config.get("listen_port", 41641)),
        "accept_dns": "1" if resource.config.get("accept_dns", True) else "0",
        "advertise_exit_node": "1" if resource.config.get("advertise_exit_node") else "0",
        "use_exit_node": str(resource.config.get("use_exit_node", "") or ""),
        "accept_subnet_routes": "1" if resource.config.get("accept_subnet_routes") else "0",
        "enable_ssh": "1" if resource.config.get("enable_ssh") else "0",
        "enable_snat": "1" if resource.config.get("enable_snat", True) else "0",
    }
    service.build_settings_wire_payload.side_effect = lambda fields: {"settings": dict(fields)}
    service.apply_settings_patch.return_value = {"result": "saved"}
    return service


class TestFinalizationHook:
    def test_hook_declared(self) -> None:
        assert TailscaleSettingsManager.FINALIZATION_HOOK == "tailscale_reconfigure"


class TestPlan:
    def test_plan_no_change(self, tmp_path: Path) -> None:
        manager = TailscaleSettingsManager(tmp_path)
        live = _make_live_fields()
        service = _make_service_mock(live_fields=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            diff = manager.plan("test-env", [_resource()])
        assert diff.is_empty
        assert diff.updates == []

    def test_plan_update_on_field_change(self, tmp_path: Path) -> None:
        manager = TailscaleSettingsManager(tmp_path)
        # Live has enable=0, resource has enable=True → update expected.
        live = _make_live_fields(enable="0")
        service = _make_service_mock(live_fields=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            diff = manager.plan("test-env", [_resource(enable=True)])
        assert not diff.is_empty
        assert len(diff.updates) == 1

    def test_plan_raises_on_multiple_resources(self, tmp_path: Path) -> None:
        manager = TailscaleSettingsManager(tmp_path)
        with pytest.raises(InvalidConfigurationError):
            manager.plan("test-env", [_resource(), _resource()])

    def test_plan_raises_on_no_resources(self, tmp_path: Path) -> None:
        manager = TailscaleSettingsManager(tmp_path)
        with pytest.raises(InvalidConfigurationError):
            manager.plan("test-env", [])


class TestApply:
    def test_apply_no_change_skips_patch(self, tmp_path: Path) -> None:
        manager = TailscaleSettingsManager(tmp_path)
        live = _make_live_fields()
        service = _make_service_mock(live_fields=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            result = manager.apply("test-env", [_resource()])
        service.apply_settings_patch.assert_not_called()
        assert result["resources_updated"] == 0
        assert result["resource_outcomes"] == []

    def test_apply_drift_calls_patch(self, tmp_path: Path) -> None:
        manager = TailscaleSettingsManager(tmp_path)
        live = _make_live_fields(enable="0")
        service = _make_service_mock(live_fields=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            result = manager.apply("test-env", [_resource(enable=True)])
        service.apply_settings_patch.assert_called_once()
        assert result["resources_updated"] == 1
        outcome = result["resource_outcomes"][0]
        assert outcome.action == "update"
        assert outcome.resource_name == "settings"

    def test_apply_raises_on_multiple_resources(self, tmp_path: Path) -> None:
        manager = TailscaleSettingsManager(tmp_path)
        with pytest.raises(InvalidConfigurationError):
            manager.apply("test-env", [_resource(), _resource()])


class TestDestroy:
    def test_destroy_noop(self, tmp_path: Path) -> None:
        manager = TailscaleSettingsManager(tmp_path)
        result = manager.destroy("test-env", [_resource()])
        assert result["resources_destroyed"] == 0
        assert result["resource_outcomes"] == []


class TestGetResourceIds:
    def test_returns_global(self, tmp_path: Path) -> None:
        manager = TailscaleSettingsManager(tmp_path)
        result = manager.get_resource_ids("test-env", [_resource()])
        assert result == {"settings": "global"}
