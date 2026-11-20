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
    DISABLED_WARNING,
    KEY_WRITE_ONLY_WARNING,
    STILL_LOGGED_OUT_WARNING,
    TailscaleAuthManager,
)
from infrafoundry.providers.opnsense.components.tailscale_settings import PLUGIN_MISSING_WARNING
from infrafoundry.providers.opnsense.services.tailscale_auth import (
    MINT_PLACEHOLDER,
    REDACTED,
    TailscaleAuthService,
)

SERVICE_PATH = "infrafoundry.providers.opnsense.components.tailscale_auth.TailscaleAuthService"
SECRETS_CM = "infrafoundry.providers.opnsense.components._secrets.ConfigManager"
URI = "secret://env_secrets/opnsense/tailscale/auth/pre_auth_key"
SENTINEL = "tskey-auth-SENTINEL-0001"
OTHER = "tskey-auth-OTHER-0002"
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


# --- mint (#1510) ----------------------------------------------------------------

MINT_ID_URI = "secret://env_secrets/opnsense/tailscale/auth/oauth_client_id"
MINT_SECRET_URI = "secret://env_secrets/opnsense/tailscale/auth/oauth_client_secret"
FAKE_ID = "fake-client-id"
FAKE_CLIENT_SECRET = "tskey-client-FAKE-0003"
FAKE_KEY = "tskey-auth-FAKEKEY-0004"
MANAGER = "infrafoundry.providers.opnsense.components.tailscale_auth"


def _mint_cm() -> MagicMock:
    env = MagicMock()
    env.secrets = {
        "opnsense": {
            "tailscale": {
                "auth": {"oauth_client_id": FAKE_ID, "oauth_client_secret": FAKE_CLIENT_SECRET}
            }
        }
    }
    cls = MagicMock()
    cls.return_value.load_environment.return_value = env
    return cls


def _mint_config(**extra: Any) -> dict[str, Any]:
    return {
        "mint": {
            "oauth_client_id": MINT_ID_URI,
            "oauth_client_secret": MINT_SECRET_URI,
            "tags": ["tag:example"],
        },
        **extra,
    }


class _Box:
    """Fake OPNsense client: routes by path, states are consumed one per status read."""

    def __init__(
        self,
        states: list[str],
        *,
        enabled: str = "1",
        server: str = SERVER,
        status_error: APIError | None = None,
    ) -> None:
        self.states = list(states)
        self.enabled = enabled
        self.server = server
        self.status_error = status_error
        self.calls: list[str] = []

    def request(self, method: str, path: str, data: Any = None, **_: Any) -> Any:
        self.calls.append(path)
        if path == "tailscale/authentication/get":
            return _live("", self.server)
        if path == "tailscale/status/status":
            if self.status_error:
                raise self.status_error
            state = self.states.pop(0) if len(self.states) > 1 else self.states[0]
            return {"BackendState": state}
        if path == "tailscale/settings/get":
            return {"settings": {"enabled": self.enabled}}
        return {"result": "saved"}


def _run_mint(
    method: str, tmp_path: Path, box: _Box, config: dict[str, Any] | None = None
) -> tuple[Any, TailscaleAuthService, MagicMock]:
    service = TailscaleAuthService(box)  # type: ignore[arg-type]
    service.mint_key = MagicMock(return_value=FAKE_KEY)  # type: ignore[method-assign]
    sleeps = MagicMock()
    with (
        patch(SERVICE_PATH) as cls,
        patch(SECRETS_CM, _mint_cm()),
        patch(f"{MANAGER}._sleep", sleeps),
    ):
        cls.from_environment.return_value = service
        result = getattr(TailscaleAuthManager(tmp_path), method)(
            "env", [_resource(**(config or _mint_config()))]
        )
    return result, service, sleeps


def _set_bodies(box: _Box) -> int:
    return box.calls.count("tailscale/authentication/set")


def test_mint_running_node_mints_and_writes_nothing(tmp_path: Path) -> None:
    box = _Box(["Running"])
    result, service, _ = _run_mint("apply", tmp_path, box)
    service.mint_key.assert_not_called()  # type: ignore[attr-defined]
    assert _set_bodies(box) == 0
    assert "tailscale/service/reconfigure" not in box.calls
    assert result["resource_outcomes"] == []
    assert "warnings" not in result


def test_mint_running_node_plan_is_empty(tmp_path: Path) -> None:
    diff, service, _ = _run_mint("plan", tmp_path, _Box(["Running"]))
    assert diff.is_empty
    service.mint_key.assert_not_called()  # type: ignore[attr-defined]


def test_mint_stopped_node_plan_shows_placeholder_only(tmp_path: Path) -> None:
    diff, service, _ = _run_mint("plan", tmp_path, _Box(["NeedsLogin"]))
    assert diff.updates == [{"pre_auth_key": MINT_PLACEHOLDER}]
    service.mint_key.assert_not_called()  # type: ignore[attr-defined]
    assert FAKE_KEY not in repr(diff.updates)


def test_mint_plan_404_warns(tmp_path: Path) -> None:
    box = _Box(["NeedsLogin"], status_error=APIError("nf", status_code=404))
    diff, _, _ = _run_mint("plan", tmp_path, box)
    assert diff.warnings == [PLUGIN_MISSING_WARNING]
    assert diff.updates == [{"pre_auth_key": MINT_PLACEHOLDER}]


def test_mint_login_server_drift_on_running_node_writes_no_key(tmp_path: Path) -> None:
    config = _mint_config(login_server="https://controlplane.tailscale.com")
    box = _Box(["Running"], server=SERVER)
    diff, _, _ = _run_mint("plan", tmp_path, box, config)
    assert diff.updates == [{"login_server": "https://controlplane.tailscale.com"}]
    result, service, _ = _run_mint("apply", tmp_path, _Box(["Running"], server=SERVER), config)
    service.mint_key.assert_not_called()  # type: ignore[attr-defined]
    assert result["resources_updated"] == 1


def test_mint_stopped_node_one_mint_one_write_reconfigure_then_running(tmp_path: Path) -> None:
    # status reads: apply check, then poll sees Running
    box = _Box(["NeedsLogin", "Running"])
    result, service, sleeps = _run_mint("apply", tmp_path, box)
    service.mint_key.assert_called_once()  # type: ignore[attr-defined]
    assert _set_bodies(box) == 1
    assert box.calls.count("tailscale/service/reconfigure") == 1
    assert result["resources_updated"] == 1
    assert "warnings" not in result
    sleeps.assert_not_called()


def test_mint_writes_the_minted_key(tmp_path: Path) -> None:
    box = _Box(["NeedsLogin", "Running"])
    bodies: list[Any] = []
    original = box.request

    def spy(method: str, path: str, data: Any = None, **kw: Any) -> Any:
        if path == "tailscale/authentication/set":
            bodies.append(data)
        return original(method, path, data, **kw)

    box.request = spy  # type: ignore[method-assign]
    _run_mint("apply", tmp_path, box)
    assert bodies[0]["authentication"]["preAuthKey"] == FAKE_KEY


def test_mint_second_window_recovery(tmp_path: Path) -> None:
    states = ["NeedsLogin"] + ["Starting"] * 6 + ["Running"]
    box = _Box(states)
    result, _, sleeps = _run_mint("apply", tmp_path, box)
    assert box.calls.count("tailscale/service/reconfigure") == 2
    assert "warnings" not in result
    assert sleeps.call_count == 5


def test_mint_still_not_running_warns_without_failing(tmp_path: Path) -> None:
    box = _Box(["NeedsLogin"])
    result, _, _ = _run_mint("apply", tmp_path, box)
    assert result["success"] is True
    assert result["warnings"] == [STILL_LOGGED_OUT_WARNING]
    assert box.calls.count("tailscale/service/reconfigure") == 2
    assert FAKE_KEY not in repr(result)


def test_mint_disabled_service_skips_with_warning(tmp_path: Path) -> None:
    box = _Box(["NeedsLogin"], enabled="0")
    result, service, _ = _run_mint("apply", tmp_path, box)
    service.mint_key.assert_not_called()  # type: ignore[attr-defined]
    assert _set_bodies(box) == 0
    assert result["warnings"] == [DISABLED_WARNING]


def test_mint_never_logs_credentials_or_key(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    box = _Box(["NeedsLogin"])
    result, _, _ = _run_mint("apply", tmp_path, box)
    plan, _, _ = _run_mint("plan", tmp_path, _Box(["NeedsLogin"]))
    blob = caplog.text + repr(result) + repr(plan.updates) + repr(plan.warnings)
    for secret in (FAKE_KEY, FAKE_CLIENT_SECRET, FAKE_ID):
        assert secret not in blob


def test_mint_conflicting_pre_auth_key_raises(tmp_path: Path) -> None:
    from infrafoundry.core.exceptions import InvalidConfigurationError

    with pytest.raises(InvalidConfigurationError):
        _run_mint("plan", tmp_path, _Box(["Running"]), _mint_config(update_pre_auth_key=True))
