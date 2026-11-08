"""Unit tests for ``SyslogSettingsManager`` (#804)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from infrafoundry.core.exceptions import InvalidConfigurationError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.components.syslog_settings import SyslogSettingsManager
from infrafoundry.providers.opnsense.services.syslog_settings import SyslogSettingsService

SERVICE_PATH = "infrafoundry.providers.opnsense.components.syslog_settings.SyslogSettingsService"

LIVE = {
    "syslog": {
        "general": {"enabled": "1", "loglocal": "1", "maxpreserve": "31", "maxfilesize": "10"},
        "destinations": {"rows": []},
    }
}


def _resource(config: dict[str, Any]) -> ResourceConfig:
    return ResourceConfig(
        name="syslog.settings", type="syslog.settings", provider="opnsense", config=config
    )


def _run(method: str, tmp_path: Path, resources: list[ResourceConfig]) -> tuple[Any, MagicMock]:
    service = SyslogSettingsService(MagicMock())
    client = MagicMock()
    client.request.return_value = LIVE
    service.client = client
    set_mock = MagicMock(return_value={"result": "saved"})
    service.set_settings = set_mock  # type: ignore[method-assign]
    service.reconfigure = MagicMock()  # type: ignore[method-assign]
    with patch(SERVICE_PATH) as cls:
        cls.from_environment.return_value = service
        result = getattr(SyslogSettingsManager(tmp_path), method)("env", resources)
    assert not service.reconfigure.called
    return result, set_mock


def test_plan_in_sync_is_empty(tmp_path: Path) -> None:
    diff, _ = _run("plan", tmp_path, [_resource({"enabled": True})])
    assert diff.is_empty


def test_plan_single_field_drift(tmp_path: Path) -> None:
    diff, _ = _run("plan", tmp_path, [_resource({"max_preserve": 7})])
    assert len(diff.updates) == 1
    assert not diff.adds
    assert not diff.deletes


def test_plan_all_fields_drift(tmp_path: Path) -> None:
    diff, _ = _run(
        "plan",
        tmp_path,
        [_resource({"enabled": False, "log_local": False, "max_preserve": 1, "max_file_size": 2})],
    )
    assert len(diff.updates) == 1


def test_apply_on_drift_writes_once(tmp_path: Path) -> None:
    result, set_mock = _run("apply", tmp_path, [_resource({"log_local": False})])
    set_mock.assert_called_once()
    payload = set_mock.call_args.args[0]
    assert payload == {
        "syslog": {
            "general": {"enabled": "1", "loglocal": "0", "maxpreserve": "31", "maxfilesize": "10"}
        }
    }
    assert result["resources_updated"] == 1
    assert [o.action for o in result["resource_outcomes"]] == ["update"]
    assert result["resource_outcomes"][0].address == "opnsense_syslog_settings.settings"


def test_apply_in_sync_makes_no_write(tmp_path: Path) -> None:
    result, set_mock = _run("apply", tmp_path, [_resource({"max_file_size": 10})])
    set_mock.assert_not_called()
    assert result["resources_updated"] == 0
    assert result["resource_outcomes"] == []


def test_finalization_hook() -> None:
    assert SyslogSettingsManager.FINALIZATION_HOOK == "syslog_reconfigure"


def test_destroy_is_a_noop(tmp_path: Path) -> None:
    with patch(SERVICE_PATH) as cls:
        result = SyslogSettingsManager(tmp_path).destroy("env", [_resource({"enabled": True})])
    cls.from_environment.assert_not_called()
    assert result["resources_destroyed"] == 0


def test_get_resource_ids(tmp_path: Path) -> None:
    assert SyslogSettingsManager(tmp_path).get_resource_ids("env", [_resource({})]) == {
        "syslog.settings": "global"
    }


def test_two_resources_rejected(tmp_path: Path) -> None:
    with pytest.raises(InvalidConfigurationError):
        _run("plan", tmp_path, [_resource({}), _resource({})])
