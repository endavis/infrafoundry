"""Unit tests for ``HasyncSettingsManager`` (#1389)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from infrafoundry.core.exceptions import InvalidConfigurationError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.components.hasync_settings import (
    PASSWORD_WRITE_ONLY_WARNING,
    HasyncSettingsManager,
)
from infrafoundry.providers.opnsense.services.hasync_settings import (
    REDACTED,
    HasyncSettingsService,
)

SERVICE_PATH = "infrafoundry.providers.opnsense.components.hasync_settings.HasyncSettingsService"
SECRETS_CM = "infrafoundry.providers.opnsense.components._secrets.ConfigManager"
URI = "secret://env_secrets/opnsense/hasync/password"
FAKE = "FAKE-SYNC-PASSWORD-0001"
OTHER = "FAKE-SYNC-PASSWORD-0002"


def _cm() -> MagicMock:
    env = MagicMock()
    env.secrets = {"opnsense": {"hasync": {"password": FAKE}}}
    cls = MagicMock()
    cls.return_value.load_environment.return_value = env
    return cls


def _live(password: str = "", **over: Any) -> dict[str, Any]:
    live: dict[str, Any] = {
        "disablepreempt": "0",
        "pfsyncinterface": {"": {"selected": 1}, "lan": {"selected": 0}},
        "pfsyncpeerip": "",
        "pfsyncversion": {"1301": {"selected": 0}, "1400": {"selected": 1}},
        "username": "",
        "password": password,
        "syncitems": {"aliases": {"selected": 0}, "rules": {"selected": 0}},
    }
    live.update(over)
    return {"hasync": live}


def _resource(**config: Any) -> ResourceConfig:
    return ResourceConfig(
        name="hasync.settings", type="hasync.settings", provider="opnsense", config=config
    )


def _run(
    method: str, tmp_path: Path, config: dict[str, Any], live: dict[str, Any]
) -> tuple[Any, HasyncSettingsService]:
    service = HasyncSettingsService(MagicMock())
    service.client.request.return_value = live  # type: ignore[attr-defined]
    service.set_settings = MagicMock(return_value={"result": "saved"})  # type: ignore[method-assign]
    service.reconfigure = MagicMock()  # type: ignore[method-assign]
    with patch(SERVICE_PATH) as cls, patch(SECRETS_CM, _cm()):
        cls.from_environment.return_value = service
        result = getattr(HasyncSettingsManager(tmp_path), method)("env", [_resource(**config)])
    return result, service


def _written(service: HasyncSettingsService) -> dict[str, Any]:
    return service.set_settings.call_args.args[0]["hasync"]  # type: ignore[attr-defined,no-any-return]


def test_hook_key() -> None:
    assert HasyncSettingsManager.FINALIZATION_HOOK == "hasync_reconfigure"


def test_in_sync_no_write_and_empty_diff(tmp_path: Path) -> None:
    diff, _ = _run("plan", tmp_path, {"username": ""}, _live())
    assert diff.is_empty
    result, service = _run("apply", tmp_path, {"username": ""}, _live())
    assert result["resource_outcomes"] == []
    service.set_settings.assert_not_called()  # type: ignore[attr-defined]


def test_drift_updates_once_and_plan_is_redacted(tmp_path: Path) -> None:
    config = {"username": "fw-test-sync", "password": URI}
    diff, _ = _run("plan", tmp_path, config, _live(""))
    assert diff.updates == [{"username": "fw-test-sync", "password": REDACTED}]
    assert FAKE not in repr(diff.updates)
    result, service = _run("apply", tmp_path, config, _live(""))
    assert result["resources_updated"] == 1
    service.set_settings.assert_called_once()  # type: ignore[attr-defined]
    service.reconfigure.assert_not_called()  # type: ignore[attr-defined]


def test_unreadable_password_with_other_drift_sends_password(tmp_path: Path) -> None:
    _, service = _run("apply", tmp_path, {"username": "u", "password": URI}, _live(""))
    assert _written(service)["password"] == FAKE


def test_unreadable_password_nothing_else_no_write_and_warns(tmp_path: Path) -> None:
    result, service = _run("apply", tmp_path, {"password": URI}, _live(""))
    service.set_settings.assert_not_called()  # type: ignore[attr-defined]
    assert result["resource_outcomes"] == []
    diff, _ = _run("plan", tmp_path, {"password": URI}, _live(""))
    assert diff.warnings == [PASSWORD_WRITE_ONLY_WARNING]
    assert diff.is_empty


def test_update_password_flag_writes_password(tmp_path: Path) -> None:
    _, service = _run("apply", tmp_path, {"password": URI, "update_password": True}, _live(""))
    assert _written(service)["password"] == FAKE


def test_readable_equal_and_different_password(tmp_path: Path) -> None:
    result, service = _run("apply", tmp_path, {"password": URI}, _live(FAKE))
    service.set_settings.assert_not_called()  # type: ignore[attr-defined]
    assert result["resources_updated"] == 0
    _, service = _run("apply", tmp_path, {"password": URI}, _live(OTHER))
    assert _written(service)["password"] == FAKE
    assert OTHER not in repr(service.set_settings.call_args)  # type: ignore[attr-defined]


def test_password_never_logged_or_in_exception(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG):
        _run("apply", tmp_path, {"username": "u", "password": URI}, _live(OTHER))
        _run("plan", tmp_path, {"username": "u", "password": URI}, _live(OTHER))
    assert FAKE not in caplog.text
    assert OTHER not in caplog.text
    with pytest.raises(InvalidConfigurationError) as exc:
        _run("apply", tmp_path, {"password": URI, "sync_items": ["bogus"]}, _live(OTHER))
    assert FAKE not in str(exc.value)
    assert OTHER not in str(exc.value)


def test_unknown_references_warn_at_plan_and_fail_before_write(tmp_path: Path) -> None:
    config = {"pfsync_interface": "opt99", "sync_items": ["rules", "bogus"]}
    diff, _ = _run("plan", tmp_path, config, _live())
    assert diff.warnings is not None
    assert len(diff.warnings) == 2
    service = HasyncSettingsService(MagicMock())
    service.client.request.return_value = _live()  # type: ignore[attr-defined]
    service.set_settings = MagicMock()  # type: ignore[method-assign]
    with patch(SERVICE_PATH) as cls, patch(SECRETS_CM, _cm()):
        cls.from_environment.return_value = service
        with pytest.raises(InvalidConfigurationError, match="opt99"):
            HasyncSettingsManager(tmp_path).apply("env", [_resource(**config)])
    service.set_settings.assert_not_called()


def test_destroy_ids_and_singleton(tmp_path: Path) -> None:
    manager = HasyncSettingsManager(tmp_path)
    result = manager.destroy("env", [_resource(username="u")])
    assert result == {"success": True, "resources_destroyed": 0, "resource_outcomes": []}
    assert manager.get_resource_ids("env", [_resource()]) == {"hasync.settings": "global"}
    with pytest.raises(Exception, match=r"hasync\.settings"):
        manager.plan("env", [_resource(), _resource()])


def test_migrate_delegates_to_service(tmp_path: Path) -> None:
    with patch(SERVICE_PATH) as cls:
        cls.from_environment.return_value.export_to_yaml.return_value = "yaml"
        assert HasyncSettingsManager(tmp_path).migrate("env") == "yaml"


def test_deletes_only_phase_does_nothing(tmp_path: Path) -> None:
    service = HasyncSettingsService(MagicMock())
    with patch(SERVICE_PATH) as cls:
        cls.from_environment.return_value = service
        result = HasyncSettingsManager(tmp_path).apply(
            "env", [_resource(username="u")], deletes_only=True
        )
    assert result["resource_outcomes"] == []
    service.client.request.assert_not_called()  # type: ignore[attr-defined]
