"""QnapProvider: registration, Terraform stub and the plan hook."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from infrafoundry.providers.qnap import QnapProvider, register
from infrafoundry.providers.qnap.client import QnapUnreachableError
from infrafoundry.providers.qnap.settings import QnapSettingsError

from .conftest import firmware, vlan
from .update_fake import FakeQnapSwitch

pytestmark = pytest.mark.unit


def _provider(tmp_path: Path) -> QnapProvider:
    provider = QnapProvider(tmp_path, tmp_path / "generated")
    provider.set_environment("test")
    return provider


def test_register_metadata() -> None:
    meta = register()
    assert meta.name == "qnap"
    assert meta.resource_types == ["vlan", "lacp.group", "firmware.update"]
    assert meta.provider_class is QnapProvider
    assert callable(meta.cli_registration)


def test_resource_types_and_terraform_types(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    assert provider.get_resource_types() == ["vlan", "lacp.group", "firmware.update"]
    assert provider.get_dependencies() == {
        "lacp.group": [],
        "vlan": ["lacp.group"],
        "firmware.update": [],
    }
    assert provider.get_terraform_resource_types() == {
        "vlan": ["qnap_vlan"],
        "lacp.group": ["qnap_lacp_group"],
        "firmware.update": ["qnap_firmware_update"],
    }


def test_generate_terraform_writes_main_tf(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    provider.generate_terraform([firmware()])
    written = list((tmp_path / "generated").rglob("main.tf"))
    assert written and "terraform {}" in written[0].read_text()


def test_generate_ansible_creates_directories(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    provider.generate_ansible([firmware()])
    assert (tmp_path / "generated").exists()


def test_plan_lines_empty_without_a_resource(tmp_path: Path) -> None:
    assert _provider(tmp_path).firmware_plan_lines("test", []) == []


def test_plan_lines_report_the_offer(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    with (
        patch("infrafoundry.providers.qnap.load_settings"),
        patch("infrafoundry.providers.qnap.QnapClient", return_value=FakeQnapSwitch()),
    ):
        lines = provider.firmware_plan_lines("test", [firmware()])
    assert lines == [
        (
            "firmware.update 'sw-fw': 2.5.0 → 2.6.0 available "
            "(run foundry provider qnap upgrade --env test)",
            False,
        )
    ]


def test_settings_error_becomes_a_warning_line(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    with patch("infrafoundry.providers.qnap.load_settings", side_effect=QnapSettingsError("bad")):
        [(line, warning)] = provider.firmware_plan_lines("test", [firmware()])
    assert warning and "update check failed: bad" in line


def test_unreachable_switch_becomes_a_warning_line(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    switch = FakeQnapSwitch()
    switch.login_errors = [QnapUnreachableError("no route")]
    with (
        patch("infrafoundry.providers.qnap.load_settings"),
        patch("infrafoundry.providers.qnap.QnapClient", return_value=switch),
    ):
        [(line, warning)] = provider.firmware_plan_lines("test", [firmware()])
    assert warning and "no route" in line


def test_deletable_types_are_the_config_types() -> None:
    assert QnapProvider.deletable_types() == {"vlan", "lacp.group"}


def test_rest_methods_delegate_to_the_config_manager(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    with patch("infrafoundry.providers.qnap.QnapConfigManager") as manager:
        instance = manager.return_value
        resources = [vlan(id=10)]
        provider.rest_plan("test", resources, add_only=True, target_resources=["v10"])
        instance.plan.assert_called_once_with(
            "test", resources, add_only=True, managed_resources=None, target_resources=["v10"]
        )
        provider.rest_apply("test", resources)
        instance.apply.assert_called_once_with("test", instance.plan.return_value)
        provider.rest_destroy("test", resources, target_resources=["v10"])
        instance.destroy.assert_called_once_with("test", resources, target_resources=["v10"])
        provider.rest_resource_ids("test", resources)
        instance.resource_ids.assert_called_once_with("test", resources)
