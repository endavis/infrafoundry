"""Unit tests for ``InterfacesSettingsManager`` (#1092)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import yaml

from infrafoundry.core.exceptions import InvalidConfigurationError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.components.interfaces_settings import (
    InterfacesSettingsManager,
)
from infrafoundry.providers.opnsense.services.interfaces_settings import (
    InterfacesSettingsService,
)

SERVICE_PATH = (
    "infrafoundry.providers.opnsense.components.interfaces_settings.InterfacesSettingsService"
)

LIVE = {
    "settings": {
        "disablechecksumoffloading": "1",
        "disablesegmentationoffloading": "1",
        "disablelargereceiveoffloading": "1",
        "disablevlanhwfilter": {
            "0": {"value": "Enable", "selected": 0},
            "1": {"value": "Disable", "selected": 0},
            "2": {"value": "Leave default", "selected": 1},
        },
        "disableipv6": "0",
        "dhcp6_norelease": "0",
        "dhcp6_debug": "0",
        "dhcp6_duid": "",
        "dhcp6_ratimeout": "10",
    }
}


def _resource(config: dict[str, Any]) -> ResourceConfig:
    return ResourceConfig(
        name="interfaces.settings",
        type="interfaces.settings",
        provider="opnsense",
        config=config,
    )


def _service() -> InterfacesSettingsService:
    service = InterfacesSettingsService(MagicMock())
    client = MagicMock()
    client.request.return_value = LIVE
    service.client = client
    return service


def _run(method: str, tmp_path: Path, resources: list[ResourceConfig]) -> tuple[Any, MagicMock]:
    service = _service()
    set_mock = MagicMock(return_value={"result": "saved"})
    service.set_settings = set_mock  # type: ignore[method-assign]
    with patch(SERVICE_PATH) as cls:
        cls.from_environment.return_value = service
        result = getattr(InterfacesSettingsManager(tmp_path), method)("env", resources)
    return result, set_mock


def test_plan_in_sync_is_empty(tmp_path: Path) -> None:
    diff, _ = _run("plan", tmp_path, [_resource({"dhcp6_debug": False})])
    assert diff.is_empty


def test_plan_drift_is_one_update_only(tmp_path: Path) -> None:
    diff, _ = _run("plan", tmp_path, [_resource({"vlan_hardware_filtering": "disable"})])
    assert len(diff.updates) == 1
    assert not diff.adds
    assert not diff.deletes


def test_apply_on_drift_writes_once(tmp_path: Path) -> None:
    result, set_mock = _run("apply", tmp_path, [_resource({"vlan_hardware_filtering": "disable"})])
    set_mock.assert_called_once()
    flat = set_mock.call_args.args[0]["settings"]
    assert flat["disablevlanhwfilter"] == "1"
    assert flat["dhcp6_ratimeout"] == "10"
    assert result["resources_updated"] == 1
    assert [o.action for o in result["resource_outcomes"]] == ["update"]


def test_apply_in_sync_makes_no_write(tmp_path: Path) -> None:
    result, set_mock = _run("apply", tmp_path, [_resource({"dhcp6_ra_timeout": 10})])
    set_mock.assert_not_called()
    assert result["resources_updated"] == 0
    assert result["resource_outcomes"] == []


def test_apply_never_reconfigures(tmp_path: Path) -> None:
    service = _service()
    reconfigure = MagicMock()
    service.reconfigure = reconfigure  # type: ignore[method-assign]
    service.set_settings = MagicMock()  # type: ignore[method-assign]
    with patch(SERVICE_PATH) as cls:
        cls.from_environment.return_value = service
        InterfacesSettingsManager(tmp_path).apply("env", [_resource({"dhcp6_debug": True})])
    reconfigure.assert_not_called()


def test_apply_logs_field_names_not_values(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level("INFO")
    _run("apply", tmp_path, [_resource({"dhcp6_duid": "secret-duid-value"})])
    assert "dhcp6_duid" in caplog.text
    assert "secret-duid-value" not in caplog.text


def test_finalization_hook() -> None:
    assert InterfacesSettingsManager.FINALIZATION_HOOK == "interfaces_settings_reconfigure"


def test_destroy_is_a_noop(tmp_path: Path) -> None:
    with patch(SERVICE_PATH) as cls:
        result = InterfacesSettingsManager(tmp_path).destroy(
            "env", [_resource({"dhcp6_debug": True})]
        )
    cls.from_environment.assert_not_called()
    assert result["resources_destroyed"] == 0


def test_get_resource_ids(tmp_path: Path) -> None:
    ids = InterfacesSettingsManager(tmp_path).get_resource_ids("env", [_resource({})])
    assert ids == {"interfaces.settings": "global"}


def test_two_resources_rejected(tmp_path: Path) -> None:
    with pytest.raises(InvalidConfigurationError):
        _run("plan", tmp_path, [_resource({}), _resource({})])


def test_migrate_exports_non_defaults(tmp_path: Path) -> None:
    service = _service()
    with patch(SERVICE_PATH) as cls:
        cls.from_environment.return_value = service
        text = InterfacesSettingsManager(tmp_path).migrate("env")
    assert yaml.safe_load(text)["opnsense"]["interfaces"]["settings"] == {}


def test_plan_in_sync_with_list_form_option_field(tmp_path: Path) -> None:
    live_list = {
        "settings": {
            **LIVE["settings"],
            "disablevlanhwfilter": [
                {"value": "Enable VLAN Hardware Filtering", "selected": 0},
                {"value": "Disable VLAN Hardware Filtering", "selected": 1},
                {"value": "Leave default", "selected": 0},
            ],
        }
    }
    service = _service()
    service.client.request.return_value = live_list  # type: ignore[attr-defined]
    with patch(SERVICE_PATH) as cls:
        cls.from_environment.return_value = service
        diff = InterfacesSettingsManager(tmp_path).plan(
            "env", [_resource({"vlan_hardware_filtering": "disable"})]
        )
    assert diff.is_empty
