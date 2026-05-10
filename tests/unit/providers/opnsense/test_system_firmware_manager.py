"""Unit tests for ``SystemFirmwareManager`` (#806 keystone).

Coverage:
    - Standard 8-test singleton template (plan/apply no-change/update,
      destroy noop, get_resource_ids, plan-raises-on-multiple).
    - Plus 3 firmware-specific tests:
      - test_plan_install_missing_plugins: 3 desired, 1 live -> 2 install entries
      - test_apply_install_calls_per_plugin: install_plugin called once per
        missing plugin
      - test_plan_warns_on_extras: extras detected, warning logged, no remove
        call
"""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from infrafoundry.core.exceptions import InvalidConfigurationError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.components.system_firmware import (
    SystemFirmwareManager,
)

SERVICE_PATH = "infrafoundry.providers.opnsense.components.system_firmware.SystemFirmwareService"


def _resource(*, plugins: list[str] | None = None) -> ResourceConfig:
    return ResourceConfig(
        name="settings",
        type="system.firmware",
        provider="opnsense",
        config={
            "plugins": plugins if plugins is not None else ["os-tailscale"],
        },
    )


def _make_service_mock(
    *,
    installed: list[str] | None = None,
    settings: dict[str, str] | None = None,
) -> MagicMock:
    """Build a SystemFirmwareService mock.

    The real service uses ``desired_vs_installed_plugins`` to compute
    install_missing/extras, so the mock implements the same set algebra.
    """
    installed_list = installed or []
    settings_dict = settings or {"mirror": "", "flavour": ""}
    service = MagicMock()
    service.get_firmware_info.return_value = {
        "plugin": [{"name": p, "installed": "1"} for p in installed_list]
    }
    service.extract_installed_plugins.return_value = sorted(installed_list)
    service.build_desired_plugin_list.side_effect = lambda r: sorted(
        set(r.config.get("plugins", []))
    )
    service.extract_firmware_settings_fields.return_value = settings_dict
    service.build_desired_firmware_settings_fields.side_effect = lambda r: {
        "mirror": r.config.get("mirror", ""),
        "flavour": r.config.get("flavour", ""),
    }

    def _diff_plugins(desired: list[str], installed: list[str]) -> tuple[list[str], list[str]]:
        return sorted(set(desired) - set(installed)), sorted(set(installed) - set(desired))

    service.desired_vs_installed_plugins.side_effect = _diff_plugins
    service.install_plugin.return_value = {"status": "ok"}
    return service


# ---------------------------------------------------------------------------
# Standard 8-test template
# ---------------------------------------------------------------------------


class TestPlan:
    def test_plan_no_change(self, tmp_path: Path) -> None:
        manager = SystemFirmwareManager(tmp_path)
        service = _make_service_mock(installed=["os-tailscale"])
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            diff = manager.plan("test-env", [_resource(plugins=["os-tailscale"])])
        assert diff.is_empty

    def test_plan_update(self, tmp_path: Path) -> None:
        """A single missing plugin should produce one update entry."""
        manager = SystemFirmwareManager(tmp_path)
        service = _make_service_mock(installed=[])
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            diff = manager.plan("test-env", [_resource(plugins=["os-acme-client"])])
        assert len(diff.updates) == 1
        assert diff.updates[0]["install_missing"] == ["os-acme-client"]

    def test_plan_raises_on_multiple_resources(self, tmp_path: Path) -> None:
        manager = SystemFirmwareManager(tmp_path)
        with pytest.raises(InvalidConfigurationError):
            manager.plan("test-env", [_resource(), _resource()])


class TestApply:
    def test_apply_no_change(self, tmp_path: Path) -> None:
        manager = SystemFirmwareManager(tmp_path)
        service = _make_service_mock(installed=["os-tailscale"])
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            result = manager.apply("test-env", [_resource(plugins=["os-tailscale"])])
        service.install_plugin.assert_not_called()
        assert result["resources_created"] == 0
        assert result["resources_updated"] == 0

    def test_apply_update(self, tmp_path: Path) -> None:
        manager = SystemFirmwareManager(tmp_path)
        service = _make_service_mock(installed=[])
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            result = manager.apply("test-env", [_resource(plugins=["os-acme-client"])])
        service.install_plugin.assert_called_once_with("os-acme-client")
        assert result["resources_created"] == 1
        outcome = result["resource_outcomes"][0]
        assert outcome.action == "add"
        assert outcome.resource_name == "os-acme-client"


class TestDestroy:
    def test_destroy_noop(self, tmp_path: Path) -> None:
        """Firmware destroy never auto-uninstalls plugins."""
        manager = SystemFirmwareManager(tmp_path)
        result = manager.destroy("test-env", [_resource()])
        assert result["resources_destroyed"] == 0


class TestGetResourceIds:
    def test_get_resource_ids(self, tmp_path: Path) -> None:
        manager = SystemFirmwareManager(tmp_path)
        result = manager.get_resource_ids("test-env", [_resource()])
        assert result == {"settings": "global"}


# ---------------------------------------------------------------------------
# Firmware-specific tests
# ---------------------------------------------------------------------------


class TestPluginReconciliation:
    def test_plan_install_missing_plugins(self, tmp_path: Path) -> None:
        """3 desired, 1 live -> 2 install entries (sorted)."""
        manager = SystemFirmwareManager(tmp_path)
        service = _make_service_mock(installed=["os-tailscale"])
        desired = ["os-acme-client", "os-smart", "os-tailscale"]
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            diff = manager.plan("test-env", [_resource(plugins=desired)])
        assert len(diff.updates) == 1
        update = diff.updates[0]
        # install_missing sorted; "os-tailscale" already installed.
        assert update["install_missing"] == ["os-acme-client", "os-smart"]

    def test_apply_install_calls_per_plugin(self, tmp_path: Path) -> None:
        """install_plugin called once per missing plugin."""
        manager = SystemFirmwareManager(tmp_path)
        service = _make_service_mock(installed=["os-tailscale"])
        desired = ["os-acme-client", "os-smart", "os-tailscale"]
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            result = manager.apply("test-env", [_resource(plugins=desired)])
        assert service.install_plugin.call_count == 2
        called_names = sorted(c.args[0] for c in service.install_plugin.call_args_list)
        assert called_names == ["os-acme-client", "os-smart"]
        assert result["resources_created"] == 2

    def test_plan_warns_on_extras(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        """Extras (live but not desired) trigger warning, no remove call."""
        manager = SystemFirmwareManager(tmp_path)
        # Live has extras the YAML doesn't declare.
        service = _make_service_mock(installed=["os-tailscale", "os-old-extra", "os-another-extra"])
        desired: list[str] = ["os-tailscale"]
        with caplog.at_level(logging.WARNING), patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            diff = manager.plan("test-env", [_resource(plugins=desired)])
        # Extras should be warned about (one log per extra).
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) >= 2
        warning_text = " ".join(r.getMessage() for r in warnings)
        assert "os-old-extra" in warning_text
        assert "os-another-extra" in warning_text
        # And no plugin should appear in install_missing.
        if diff.updates:
            assert diff.updates[0].get("install_missing", []) == []
        # Critical: ``remove_plugin`` MUST NOT be called for extras.
        service.remove_plugin.assert_not_called()
