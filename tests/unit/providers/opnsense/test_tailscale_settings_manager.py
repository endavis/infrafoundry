"""Unit tests for ``TailscaleSettingsManager`` (#787)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from infrafoundry.core.exceptions import APIError, InvalidConfigurationError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.components.tailscale_settings import (
    PLUGIN_MISSING_WARNING,
    TailscaleSettingsManager,
)
from infrafoundry.providers.opnsense.services.tailscale_settings import TailscaleSettingsService

SERVICE_PATH = (
    "infrafoundry.providers.opnsense.components.tailscale_settings.TailscaleSettingsService"
)


def _live(**overrides: Any) -> dict[str, Any]:
    settings: dict[str, Any] = {
        "enabled": "0",
        "listenPort": "41641",
        "disableSNAT": "0",
        "useExitNode": {"": {"selected": 1}, "peer1": {"selected": 0}},
        "subnets": {"subnet4": []},
    }
    settings.update(overrides)
    return {"settings": settings}


def _resource(**config: Any) -> ResourceConfig:
    return ResourceConfig(
        name="tailscale.settings", type="tailscale.settings", provider="opnsense", config=config
    )


def _run(
    method: str, tmp_path: Path, config: dict[str, Any], live: dict[str, Any] | None = None
) -> tuple[Any, TailscaleSettingsService]:
    service = TailscaleSettingsService(MagicMock())
    service.client.request.return_value = live or _live()  # type: ignore[attr-defined]
    service.set_settings = MagicMock(return_value={"result": "saved"})  # type: ignore[method-assign]
    service.reconfigure = MagicMock()  # type: ignore[method-assign]
    with patch(SERVICE_PATH) as cls:
        cls.from_environment.return_value = service
        result = getattr(TailscaleSettingsManager(tmp_path), method)("env", [_resource(**config)])
    assert not service.reconfigure.called
    return result, service


def test_hook_key() -> None:
    assert TailscaleSettingsManager.FINALIZATION_HOOK == "tailscale_reconfigure"


def test_in_sync_no_write(tmp_path: Path) -> None:
    result, service = _run("apply", tmp_path, {"enabled": False, "enable_snat": True})
    assert result["resource_outcomes"] == []
    service.set_settings.assert_not_called()  # type: ignore[attr-defined]
    diff, _ = _run("plan", tmp_path, {"enabled": False})
    assert diff.is_empty


def test_drift_writes_once_without_subnets(tmp_path: Path) -> None:
    result, service = _run("apply", tmp_path, {"listen_port": 5000, "enable_snat": False})
    service.set_settings.assert_called_once()  # type: ignore[attr-defined]
    body = service.set_settings.call_args.args[0]["settings"]  # type: ignore[attr-defined]
    assert "subnets" not in body
    assert body["listenPort"] == "5000"
    assert body["disableSNAT"] == "1"
    (outcome,) = result["resource_outcomes"]
    assert outcome.address == "opnsense_tailscale_settings.settings"
    assert result["resources_updated"] == 1


def test_plan_404_warns_with_update(tmp_path: Path) -> None:
    service = TailscaleSettingsService(MagicMock())
    service.client.request.side_effect = APIError("nope", status_code=404)  # type: ignore[attr-defined]
    with patch(SERVICE_PATH) as cls:
        cls.from_environment.return_value = service
        diff = TailscaleSettingsManager(tmp_path).plan("env", [_resource(enabled=True)])
    assert diff.warnings == [PLUGIN_MISSING_WARNING]
    assert diff.updates == [{"enabled": "1"}]


def test_plan_other_error_propagates(tmp_path: Path) -> None:
    service = TailscaleSettingsService(MagicMock())
    service.client.request.side_effect = APIError("boom", status_code=500)  # type: ignore[attr-defined]
    with patch(SERVICE_PATH) as cls:
        cls.from_environment.return_value = service
        with pytest.raises(APIError):
            TailscaleSettingsManager(tmp_path).plan("env", [_resource(enabled=True)])


def test_apply_404_raises(tmp_path: Path) -> None:
    service = TailscaleSettingsService(MagicMock())
    service.client.request.side_effect = APIError("nope", status_code=404)  # type: ignore[attr-defined]
    with patch(SERVICE_PATH) as cls:
        cls.from_environment.return_value = service
        with pytest.raises(APIError):
            TailscaleSettingsManager(tmp_path).apply("env", [_resource(enabled=True)])


def test_unknown_exit_node_warns_at_plan(tmp_path: Path) -> None:
    diff, _ = _run("plan", tmp_path, {"use_exit_node": "ghost"})
    assert any("use_exit_node" in w for w in diff.warnings)
    ok, _ = _run("plan", tmp_path, {"use_exit_node": "peer1"})
    assert ok.warnings == []


def test_unknown_exit_node_raises_before_write(tmp_path: Path) -> None:
    service = TailscaleSettingsService(MagicMock())
    service.client.request.return_value = _live()  # type: ignore[attr-defined]
    service.set_settings = MagicMock()  # type: ignore[method-assign]
    with patch(SERVICE_PATH) as cls:
        cls.from_environment.return_value = service
        with pytest.raises(InvalidConfigurationError):
            TailscaleSettingsManager(tmp_path).apply(
                "env", [_resource(use_exit_node="ghost", enabled=True)]
            )
    service.set_settings.assert_not_called()


def test_destroy_makes_no_calls(tmp_path: Path) -> None:
    with patch(SERVICE_PATH) as cls:
        result = TailscaleSettingsManager(tmp_path).destroy("env", [_resource(enabled=True)])
    cls.from_environment.assert_not_called()
    assert result["resources_destroyed"] == 0


def test_singleton_enforced(tmp_path: Path) -> None:
    with patch(SERVICE_PATH), pytest.raises(InvalidConfigurationError):
        TailscaleSettingsManager(tmp_path).plan("env", [_resource(), _resource()])


def test_get_resource_ids(tmp_path: Path) -> None:
    ids = TailscaleSettingsManager(tmp_path).get_resource_ids("env", [_resource()])
    assert ids == {"tailscale.settings": "global"}
