"""Unit tests for ``TailscaleAuthManager`` (#787)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from infrafoundry.core.exceptions import APIError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.components.tailscale_auth import (
    KEY_WRITE_ONLY_WARNING,
    TailscaleAuthManager,
)
from infrafoundry.providers.opnsense.components.tailscale_settings import PLUGIN_MISSING_WARNING
from infrafoundry.providers.opnsense.services.tailscale_auth import REDACTED, TailscaleAuthService

SERVICE_PATH = "infrafoundry.providers.opnsense.components.tailscale_auth.TailscaleAuthService"
SECRETS_CM = "infrafoundry.providers.opnsense.components._secrets.ConfigManager"
URI = "secret://env_secrets/opnsense/tailscale/auth/pre_auth_key"
SENTINEL = "tskey-auth-SENTINEL-0001"  # nosec B105
OTHER = "tskey-auth-OTHER-0002"  # nosec B105
SERVER = "https://controlplane.example.com"


def _cm() -> MagicMock:
    env = MagicMock()
    env.secrets = {"opnsense": {"tailscale": {"auth": {"pre_auth_key": SENTINEL}}}}
    cls = MagicMock()
    cls.return_value.load_environment.return_value = env
    return cls


def _live(key: str = "", server: str = SERVER) -> dict[str, Any]:
    return {"authentication": {"loginServer": server, "preAuthKey": key}}


def _resource(**config: Any) -> ResourceConfig:
    return ResourceConfig(
        name="tailscale.auth", type="tailscale.auth", provider="opnsense", config=config
    )


def _run(
    method: str, tmp_path: Path, config: dict[str, Any], live: dict[str, Any]
) -> tuple[Any, TailscaleAuthService]:
    service = TailscaleAuthService(MagicMock())
    service.client.request.return_value = live  # type: ignore[attr-defined]
    service.set_auth = MagicMock(return_value={"result": "saved"})  # type: ignore[method-assign]
    with patch(SERVICE_PATH) as cls, patch(SECRETS_CM, _cm()):
        cls.from_environment.return_value = service
        result = getattr(TailscaleAuthManager(tmp_path), method)("env", [_resource(**config)])
    return result, service


def _written(service: TailscaleAuthService) -> dict[str, Any]:
    return service.set_auth.call_args.args[0]["authentication"]  # type: ignore[attr-defined,no-any-return]


def test_hook_key() -> None:
    assert TailscaleAuthManager.FINALIZATION_HOOK == "tailscale_reconfigure"


def test_readable_equal_key_no_write(tmp_path: Path) -> None:
    result, service = _run("apply", tmp_path, {"pre_auth_key": URI}, _live(SENTINEL))
    assert result["resource_outcomes"] == []
    service.set_auth.assert_not_called()  # type: ignore[attr-defined]


def test_readable_different_key_writes_it(tmp_path: Path) -> None:
    result, service = _run("apply", tmp_path, {"pre_auth_key": URI}, _live(OTHER))
    assert _written(service)["preAuthKey"] == SENTINEL
    assert result["resources_updated"] == 1


def test_unreadable_key_without_flag_no_write_and_warns(tmp_path: Path) -> None:
    result, service = _run("apply", tmp_path, {"pre_auth_key": URI}, _live(""))
    service.set_auth.assert_not_called()  # type: ignore[attr-defined]
    assert result["resource_outcomes"] == []
    diff, _ = _run("plan", tmp_path, {"pre_auth_key": URI}, _live(""))
    assert diff.warnings == [KEY_WRITE_ONLY_WARNING]
    assert diff.is_empty


def test_unreadable_key_with_flag_writes_key(tmp_path: Path) -> None:
    _, service = _run(
        "apply", tmp_path, {"pre_auth_key": URI, "update_pre_auth_key": True}, _live("")
    )
    assert _written(service)["preAuthKey"] == SENTINEL


def test_flag_with_equal_key_is_a_change(tmp_path: Path) -> None:
    result, service = _run(
        "apply", tmp_path, {"pre_auth_key": URI, "update_pre_auth_key": True}, _live(SENTINEL)
    )
    assert result["resources_updated"] == 1
    assert _written(service)["preAuthKey"] == SENTINEL


def test_login_server_only_drift_sends_no_key(tmp_path: Path) -> None:
    _, service = _run(
        "apply",
        tmp_path,
        {"login_server": "https://b.example.com", "pre_auth_key": URI},
        _live(""),
    )
    assert _written(service) == {"loginServer": "https://b.example.com"}


def test_plan_map_is_redacted(tmp_path: Path) -> None:
    diff, _ = _run("plan", tmp_path, {"pre_auth_key": URI, "update_pre_auth_key": True}, _live(""))
    assert diff.updates == [{"pre_auth_key": REDACTED}]
    assert SENTINEL not in repr(diff.updates)
    assert SENTINEL not in repr(diff.warnings)


def test_key_never_logged(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.DEBUG):
        _run("apply", tmp_path, {"pre_auth_key": URI, "update_pre_auth_key": True}, _live(OTHER))
        _run("plan", tmp_path, {"pre_auth_key": URI}, _live(OTHER))
    assert SENTINEL not in caplog.text
    assert OTHER not in caplog.text
    assert any("pre_auth_key" in r.getMessage() for r in caplog.records)


def test_key_not_in_exception(tmp_path: Path) -> None:
    service = TailscaleAuthService(MagicMock())
    service.client.request.return_value = {"preAuthKey": OTHER}  # type: ignore[attr-defined]
    with patch(SERVICE_PATH) as cls, patch(SECRETS_CM, _cm()):
        cls.from_environment.return_value = service
        with pytest.raises(APIError) as exc:
            TailscaleAuthManager(tmp_path).apply("env", [_resource(pre_auth_key=URI)])
    assert SENTINEL not in str(exc.value)
    assert OTHER not in str(exc.value)
    assert OTHER not in str(exc.value.response)


def test_plan_404_warns(tmp_path: Path) -> None:
    service = TailscaleAuthService(MagicMock())
    service.client.request.side_effect = APIError("nope", status_code=404)  # type: ignore[attr-defined]
    with patch(SERVICE_PATH) as cls, patch(SECRETS_CM, _cm()):
        cls.from_environment.return_value = service
        diff = TailscaleAuthManager(tmp_path).plan("env", [_resource(pre_auth_key=URI)])
    assert diff.warnings == [PLUGIN_MISSING_WARNING]
    assert diff.updates == [{"pre_auth_key": REDACTED}]


def test_destroy_is_noop_and_ids(tmp_path: Path) -> None:
    manager = TailscaleAuthManager(tmp_path)
    assert manager.destroy("env", [_resource()])["resources_destroyed"] == 0
    assert manager.get_resource_ids("env", [_resource()]) == {"tailscale.auth": "global"}
