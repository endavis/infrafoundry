"""Unit tests for ``AcmeClientSettingsManager`` (#790)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from infrafoundry.core.exceptions import APIError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.components.acmeclient_settings import (
    PLUGIN_MISSING_WARNING,
    AcmeClientSettingsManager,
)
from infrafoundry.providers.opnsense.services.acmeclient_settings import (
    AcmeClientSettingsService,
)

SERVICE_PATH = (
    "infrafoundry.providers.opnsense.components.acmeclient_settings.AcmeClientSettingsService"
)


def _live(**overrides: Any) -> dict[str, Any]:
    settings = {
        "enabled": "1",
        "autoRenewal": "1",
        "UpdateCron": "cron-uuid",
        "environment": "prod",
        "logLevel": "normal",
    }
    settings.update(overrides)
    return {"acmeclient": {"settings": settings}}


def _resource(**config: Any) -> ResourceConfig:
    return ResourceConfig(
        name="acmeclient.settings", type="acmeclient.settings", provider="opnsense", config=config
    )


def _run(
    method: str, tmp_path: Path, config: dict[str, Any], live: dict[str, Any] | None = None
) -> tuple[Any, AcmeClientSettingsService]:
    service = AcmeClientSettingsService(MagicMock())
    service.client.request.return_value = live or _live()  # type: ignore[attr-defined]
    service.set_settings = MagicMock(return_value={"result": "saved"})  # type: ignore[method-assign]
    service.fetch_cron_integration = MagicMock()  # type: ignore[method-assign]
    service.reconfigure = MagicMock()  # type: ignore[method-assign]
    with patch(SERVICE_PATH) as cls:
        cls.from_environment.return_value = service
        result = getattr(AcmeClientSettingsManager(tmp_path), method)("env", [_resource(**config)])
    assert not service.reconfigure.called
    return result, service


def test_hook_key() -> None:
    assert AcmeClientSettingsManager.FINALIZATION_HOOK == "acmeclient_reconfigure"


def test_in_sync_no_write_no_cron_call(tmp_path: Path) -> None:
    result, service = _run("apply", tmp_path, {"enabled": True})
    assert result["resource_outcomes"] == []
    service.set_settings.assert_not_called()  # type: ignore[attr-defined]
    service.fetch_cron_integration.assert_not_called()  # type: ignore[attr-defined]
    diff, _ = _run("plan", tmp_path, {"enabled": True})
    assert diff.is_empty


def test_drift_with_renewal_on_writes_then_fetches_cron_once(tmp_path: Path) -> None:
    result, service = _run("apply", tmp_path, {"log_level": "debug"})
    service.set_settings.assert_called_once()  # type: ignore[attr-defined]
    payload = service.set_settings.call_args.args[0]  # type: ignore[attr-defined]
    assert payload["acmeclient"]["settings"]["UpdateCron"] == "cron-uuid"
    service.fetch_cron_integration.assert_called_once()  # type: ignore[attr-defined]
    assert result["resources_updated"] == 1
    assert result["resource_outcomes"][0].address == "opnsense_acmeclient_settings.settings"


@pytest.mark.parametrize("flag", ["enabled", "autoRenewal"])
def test_drift_with_either_flag_off_does_not_fetch_cron(tmp_path: Path, flag: str) -> None:
    _, service = _run("apply", tmp_path, {"log_level": "debug"}, _live(**{flag: "0"}))
    service.set_settings.assert_called_once()  # type: ignore[attr-defined]
    service.fetch_cron_integration.assert_not_called()  # type: ignore[attr-defined]


def test_turning_renewal_on_fetches_cron(tmp_path: Path) -> None:
    _, service = _run("apply", tmp_path, {"auto_renewal": True}, _live(autoRenewal="0"))
    service.fetch_cron_integration.assert_called_once()  # type: ignore[attr-defined]


def test_destroy_is_a_noop_and_ids_are_global(tmp_path: Path) -> None:
    manager = AcmeClientSettingsManager(tmp_path)
    assert manager.destroy("env", [_resource()])["resources_destroyed"] == 0
    assert manager.get_resource_ids("env", [_resource()]) == {"acmeclient.settings": "global"}


def test_plan_404_is_an_update_plus_plugin_warning(tmp_path: Path) -> None:
    service = AcmeClientSettingsService(MagicMock())
    service.client.request.side_effect = APIError("nope", status_code=404)  # type: ignore[attr-defined]
    with patch(SERVICE_PATH) as cls:
        cls.from_environment.return_value = service
        diff = AcmeClientSettingsManager(tmp_path).plan("env", [_resource(enabled=True)])
    assert len(diff.updates) == 1
    assert diff.warnings == [PLUGIN_MISSING_WARNING]


def test_plan_other_api_errors_propagate(tmp_path: Path) -> None:
    service = AcmeClientSettingsService(MagicMock())
    service.client.request.side_effect = APIError("boom", status_code=500)  # type: ignore[attr-defined]
    with patch(SERVICE_PATH) as cls:
        cls.from_environment.return_value = service
        with pytest.raises(APIError):
            AcmeClientSettingsManager(tmp_path).plan("env", [_resource(enabled=True)])


def test_apply_404_raises(tmp_path: Path) -> None:
    service = AcmeClientSettingsService(MagicMock())
    service.client.request.side_effect = APIError("nope", status_code=404)  # type: ignore[attr-defined]
    with patch(SERVICE_PATH) as cls:
        cls.from_environment.return_value = service
        with pytest.raises(APIError):
            AcmeClientSettingsManager(tmp_path).apply("env", [_resource(enabled=True)])


def test_migrate_exports_yaml(tmp_path: Path) -> None:
    service = AcmeClientSettingsService(MagicMock())
    service.client.request.return_value = _live()  # type: ignore[attr-defined]
    with patch(SERVICE_PATH) as cls:
        cls.from_environment.return_value = service
        text = AcmeClientSettingsManager(tmp_path).migrate("env")
    assert "acmeclient:" in text and "settings:" in text


def test_singleton_diff_warnings_default_to_empty() -> None:
    from infrafoundry.providers.opnsense.components._singleton import SingletonDiff

    assert SingletonDiff(None).warnings == []
    assert SingletonDiff({"a": "1"}, warnings=["w"]).warnings == ["w"]
