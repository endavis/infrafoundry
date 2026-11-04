"""Unit tests for ``SystemFirmwareService`` (#1149)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.services.system_firmware import SystemFirmwareService


@pytest.fixture
def service() -> SystemFirmwareService:
    svc = SystemFirmwareService(MagicMock())
    svc.system_client = MagicMock()
    return svc


def _res(**config: object) -> ResourceConfig:
    return ResourceConfig(
        name="settings", type="system.firmware", provider="opnsense", config=dict(config)
    )


def test_extract_settings(service: SystemFirmwareService) -> None:
    fields = service.extract_firmware_settings_fields(
        {"firmware": {"mirror": " m ", "flavour": "f", "plugins": "x", "aux": 1}}
    )
    assert fields["mirror"] == "m"
    assert fields["flavour"] == "f"
    assert fields["type"] == ""
    assert "plugins" not in fields
    assert "aux" not in fields


@pytest.mark.parametrize("response", [{}, {"firmware": "x"}])
def test_extract_settings_missing_envelope(
    service: SystemFirmwareService,
    response: dict,  # type: ignore[type-arg]
) -> None:
    assert service.extract_firmware_settings_fields(response) == {}


def test_desired_only_yaml_keys(service: SystemFirmwareService) -> None:
    assert service.build_desired_firmware_settings_fields(_res(mirror="m", plugins=[])) == {
        "mirror": "m"
    }


def test_drift_none_when_yaml_omits_mirror(service: SystemFirmwareService) -> None:
    live = {"mirror": "https://live", "flavour": "latest"}
    assert service.settings_drift(live, {}) is None
    assert service.settings_drift(live, {"flavour": "latest"}) is None


def test_drift_only_yaml_keys(service: SystemFirmwareService) -> None:
    live = {"mirror": "a", "flavour": "latest"}
    assert service.settings_drift(live, {"mirror": "b"}) == {"mirror": "b"}


def test_extract_installed_plugins_live_shape(service: SystemFirmwareService) -> None:
    info = {
        "plugin": [
            {"name": "os-b", "installed": "1", "locked": "N/A"},
            {"name": "os-a", "installed": "1", "locked": "N/A"},
            {"name": "os-c", "installed": "0", "locked": "N/A"},
            "junk",
            {"installed": "1"},
        ]
    }
    assert service.extract_installed_plugins(info) == ["os-a", "os-b"]
    assert service.extract_installed_plugins({"plugin": "x"}) == []


def test_build_desired_plugin_list(service: SystemFirmwareService) -> None:
    assert service.build_desired_plugin_list(_res(plugins="b, a ,a")) == ["a", "b"]
    assert service.build_desired_plugin_list(_res(plugins=["b", "a"])) == ["a", "b"]
    assert service.build_desired_plugin_list(_res(plugins=3)) == []


def test_export_omits_subscription(service: SystemFirmwareService) -> None:
    client = service.system_client
    client.get_firmware_info.return_value = {  # type: ignore[attr-defined]
        "plugin": [{"name": "os-a", "installed": "1"}]
    }
    client.get_firmware_settings.return_value = {  # type: ignore[attr-defined]
        "firmware": {"mirror": "m", "subscription": "KEY", "flavour": "", "reboot": "0"}
    }
    out = service.export_to_yaml()
    assert "os-a" in out
    assert "mirror" in out
    assert "KEY" not in out
    assert "subscription" not in out


def test_install_failed_raises(service: SystemFirmwareService) -> None:
    from infrafoundry.core.exceptions import APIError

    service.system_client.install_plugin.return_value = {"result": "failed"}  # type: ignore[attr-defined]
    with pytest.raises(APIError):
        service.install_plugin("os-a")
