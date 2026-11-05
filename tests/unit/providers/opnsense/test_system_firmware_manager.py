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
from typing import cast
from unittest.mock import MagicMock, patch

import pytest

from infrafoundry.core.exceptions import APIError, InvalidConfigurationError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.components.system_firmware import (
    SystemFirmwareManager,
)
from infrafoundry.providers.opnsense.services.system_firmware import SystemFirmwareService

SERVICE_PATH = "infrafoundry.providers.opnsense.components.system_firmware.SystemFirmwareService"


def _resource(
    *, plugins: list[str] | None = None, extra: dict[str, str] | None = None
) -> ResourceConfig:
    return ResourceConfig(
        name="system.firmware",
        type="system.firmware",
        provider="opnsense",
        config={
            "plugins": plugins if plugins is not None else ["os-tailscale"],
            **(extra or {}),
        },
    )


def _make_service_mock(
    *,
    installed: list[str] | None = None,
    settings: dict[str, str] | None = None,
) -> SystemFirmwareService:
    """Build a real ``SystemFirmwareService`` over a mocked ``SystemClient``.

    ``core/firmware/info`` and ``core/firmware/get`` are separate reads, so
    the mock answers each with its live shape (``installed`` is ``"0"``/``"1"``).
    """
    installed_list = installed or []
    service = SystemFirmwareService(MagicMock())
    client = MagicMock()
    client.get_firmware_info.return_value = {
        "plugin": [{"name": p, "installed": "1", "locked": "N/A"} for p in installed_list]
        + [{"name": "os-other", "installed": "0", "locked": "N/A"}]
    }
    client.get_firmware_settings.return_value = {
        "firmware": {
            "mirror": "",
            "flavour": "",
            "type": "",
            "subscription": "",
            "reboot": "0",
            **(settings or {}),
        }
    }
    client.install_plugin.return_value = {"status": "ok"}
    client.set_firmware_settings.return_value = {"result": "saved"}
    service.system_client = client
    return service


def _client(service: SystemFirmwareService) -> MagicMock:
    return cast(MagicMock, service.system_client)


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
        _client(service).install_plugin.assert_not_called()
        assert result["resources_created"] == 0
        assert result["resources_updated"] == 0

    def test_apply_update(self, tmp_path: Path) -> None:
        manager = SystemFirmwareManager(tmp_path)
        service = _make_service_mock(installed=[])
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            result = manager.apply("test-env", [_resource(plugins=["os-acme-client"])])
        _client(service).install_plugin.assert_called_once_with("os-acme-client")
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
        assert result == {"system.firmware": "global"}

    def test_get_resource_ids_uses_resource_name(self, tmp_path: Path) -> None:
        custom = _resource().model_copy(update={"name": "custom"})
        result = SystemFirmwareManager(tmp_path).get_resource_ids("test-env", [custom])
        assert result == {"custom": "global"}

    def test_get_resource_ids_empty(self, tmp_path: Path) -> None:
        assert SystemFirmwareManager(tmp_path).get_resource_ids("test-env", []) == {}


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
        assert _client(service).install_plugin.call_count == 2
        called_names = sorted(c.args[0] for c in _client(service).install_plugin.call_args_list)
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
        _client(service).remove_plugin.assert_not_called()


class TestSettings:
    def test_plan_empty_when_yaml_omits_settings_and_live_has_mirror(self, tmp_path: Path) -> None:
        manager = SystemFirmwareManager(tmp_path)
        service = _make_service_mock(installed=["os-tailscale"], settings={"mirror": "https://m"})
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            diff = manager.plan("test-env", [_resource(plugins=["os-tailscale"])])
        assert diff.is_empty

    def test_plan_shows_settings_drift(self, tmp_path: Path) -> None:
        manager = SystemFirmwareManager(tmp_path)
        service = _make_service_mock(installed=["os-tailscale"], settings={"mirror": "old"})
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            diff = manager.plan(
                "test-env",
                [_resource(plugins=["os-tailscale"], extra={"mirror": "new"})],
            )
        assert diff.updates[0]["settings"] == {"mirror": "new"}
        assert diff.updates[0]["install_missing"] == []

    def test_apply_installs_then_writes_drifted_keys_only(self, tmp_path: Path) -> None:
        manager = SystemFirmwareManager(tmp_path)
        service = _make_service_mock(installed=[], settings={"mirror": "old", "flavour": "latest"})
        resource = _resource(
            plugins=["os-acme-client", "os-smart"], extra={"mirror": "new", "flavour": "latest"}
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            result = manager.apply("test-env", [resource])
        client = _client(service)
        assert client.install_plugin.call_count == 2
        client.set_firmware_settings.assert_called_once_with(
            {"firmware": {"mirror": "new", "flavour": "latest"}}
        )
        assert result["resources_created"] == 2
        assert result["resources_updated"] == 1
        settings_outcome = result["resource_outcomes"][-1]
        assert settings_outcome.address == "opnsense_system_firmware.settings"
        assert settings_outcome.action == "update"
        assert settings_outcome.resource_name == "system.firmware"

    def test_apply_no_set_when_only_plugins_differ(self, tmp_path: Path) -> None:
        manager = SystemFirmwareManager(tmp_path)
        service = _make_service_mock(installed=[])
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            result = manager.apply("test-env", [_resource(plugins=["os-smart"])])
        _client(service).set_firmware_settings.assert_not_called()
        assert result["resources_updated"] == 0

    def test_failed_set_raises_api_error(self, tmp_path: Path) -> None:
        manager = SystemFirmwareManager(tmp_path)
        service = _make_service_mock(installed=["os-tailscale"])
        _client(service).set_firmware_settings.return_value = {
            "result": "failed",
            "validations": {"firmware.mirror": "bad"},
        }
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            with pytest.raises(APIError):
                manager.apply(
                    "test-env",
                    [_resource(plugins=["os-tailscale"], extra={"mirror": "new"})],
                )

    def test_logs_carry_keys_not_values(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        manager = SystemFirmwareManager(tmp_path)
        service = _make_service_mock(installed=["os-tailscale"])
        with caplog.at_level(logging.DEBUG), patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            manager.apply(
                "test-env",
                [_resource(plugins=["os-tailscale"], extra={"mirror": "secret-mirror-value"})],
            )
        text = " ".join(r.getMessage() for r in caplog.records)
        assert "mirror" in text
        assert "secret-mirror-value" not in text
