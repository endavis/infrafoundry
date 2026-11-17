"""Unit tests for the HA config sync after apply (#1390)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import pytest

from infrafoundry.core.exceptions import APIError, InvalidConfigurationError
from infrafoundry.providers.opnsense.services.hasync_status import (
    HasyncStatusService,
    resolve_ha_sync_options,
    run_ha_sync_after_apply,
)

BACKUP = "192.0.2.2"
MODULE = "infrafoundry.providers.opnsense.services.hasync_status"


class TestResolveOptions:
    def test_defaults(self) -> None:
        empties: list[dict[str, Any] | None] = [None, {}]
        for settings in empties:
            opts = resolve_ha_sync_options(settings)
            assert (opts.mode, opts.timeout) == ("changed", 300)

    @pytest.mark.parametrize(
        ("value", "mode"), [(True, "changed"), (False, "off"), ("always", "always")]
    )
    def test_modes(self, value: object, mode: str) -> None:
        assert resolve_ha_sync_options({"ha_sync_after_apply": value}).mode == mode

    def test_timeout_is_kept(self) -> None:
        assert resolve_ha_sync_options({"ha_sync_timeout": 90}).timeout == 90

    @pytest.mark.parametrize("value", ["yes", 1, None, "ALWAYS"])
    def test_bad_mode(self, value: object) -> None:
        with pytest.raises(InvalidConfigurationError, match="ha_sync_after_apply"):
            resolve_ha_sync_options({"ha_sync_after_apply": value})

    @pytest.mark.parametrize("value", [0, -5, True, "300", 1.5])
    def test_bad_timeout(self, value: object) -> None:
        with pytest.raises(InvalidConfigurationError, match="ha_sync_timeout"):
            resolve_ha_sync_options({"ha_sync_timeout": value})


def _service(reply: Any = None, exc: Exception | None = None) -> HasyncStatusService:
    client = MagicMock()
    if exc is not None:
        client.request.side_effect = exc
    else:
        client.request.return_value = reply
    return HasyncStatusService(client, timeout=120)


def _request(svc: HasyncStatusService) -> MagicMock:
    """Return the service client's ``request`` mock."""
    request: MagicMock = svc.client.request  # type: ignore[assignment]
    return request


class TestVersion:
    def test_error_status_names_backup_endpoint_and_message(self) -> None:
        svc = _service({"status": "error", "message": "fetch error. remote host down?"})
        with pytest.raises(APIError) as info:
            svc.version(BACKUP)
        text = str(info.value)
        assert BACKUP in text
        assert "core/hasync_status/version" in text
        assert "fetch error. remote host down?" in text

    def test_non_dict_reply(self) -> None:
        with pytest.raises(APIError, match=BACKUP):
            _service("oops").version(BACKUP)

    def test_falsy_response_warns_and_continues(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level("WARNING"):
            result = _service({"response": False}).version(BACKUP)
        assert result == {"response": False}
        assert any(BACKUP in r.getMessage() for r in caplog.records)

    def test_good_reply_does_not_warn(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level("WARNING"):
            _service({"response": {"firmware": "x"}}).version(BACKUP)
        assert not caplog.records

    def test_timeout_names_backup_and_timeout(self) -> None:
        svc = _service(exc=httpx.ReadTimeout("slow"))
        with pytest.raises(APIError) as info:
            svc.version(BACKUP)
        text = str(info.value)
        assert BACKUP in text
        assert "120" in text
        assert "core/hasync_status/version" in text

    def test_posts_to_the_endpoint(self) -> None:
        svc = _service({"response": {"a": 1}})
        svc.version(BACKUP)
        _request(svc).assert_called_once_with("POST", "core/hasync_status/version")


class TestRestartAll:
    def test_ok_returns_count(self) -> None:
        svc = _service({"status": "ok", "count": 3})
        assert svc.restart_all(BACKUP) == 3
        _request(svc).assert_called_once_with("POST", "core/hasync_status/restartAll")

    def test_ok_without_count(self) -> None:
        assert _service({"status": "ok"}).restart_all(BACKUP) is None

    def test_error_carries_backup_and_message(self) -> None:
        with pytest.raises(APIError) as info:
            _service({"status": "error", "message": "x"}).restart_all(BACKUP)
        assert BACKUP in str(info.value)
        assert "restartAll: x" in str(info.value)

    def test_empty_reply_is_an_error(self) -> None:
        with pytest.raises(APIError, match=BACKUP):
            _service({}).restart_all(BACKUP)

    def test_non_dict_reply_is_an_error(self) -> None:
        with pytest.raises(APIError, match=BACKUP):
            _service(None).restart_all(BACKUP)

    def test_transport_error_is_wrapped(self) -> None:
        with pytest.raises(APIError, match="120"):
            _service(exc=httpx.ConnectError("down")).restart_all(BACKUP)


def _run(
    settings: dict[str, Any] | None,
    changed: bool,
    *,
    target: str = BACKUP,
    replies: list[Any] | None = None,
) -> tuple[str, MagicMock]:
    """Run the flow with patched config and client; return the line and the client."""
    client = MagicMock()
    client.request.side_effect = [
        {"hasync": {"synchronizetoip": target}},
        *(
            replies
            if replies is not None
            else [{"response": {"v": 1}}, {"status": "ok", "count": 2}]
        ),
    ]
    env = MagicMock()
    env.get_provider_settings.return_value = settings
    with (
        patch("infrafoundry.core.config.ConfigManager") as manager,
        patch(f"{MODULE}.BaseService.client_from_environment", return_value=client) as factory,
    ):
        manager.return_value.load_environment.return_value = env
        line = run_ha_sync_after_apply("env", "opnsense", Path("cfg"), changed)
    client.factory = factory
    return line, client


class TestRunHaSync:
    def test_off_builds_no_client(self) -> None:
        with (
            patch("infrafoundry.core.config.ConfigManager") as manager,
            patch(f"{MODULE}.BaseService.client_from_environment") as factory,
        ):
            env = manager.return_value.load_environment.return_value
            env.get_provider_settings.return_value = {"ha_sync_after_apply": False}
            line = run_ha_sync_after_apply("env", "opnsense", Path("cfg"), True)
        factory.assert_not_called()
        assert line == "HA sync after apply disabled (ha_sync_after_apply: false)"

    def test_changed_mode_skips_a_noop_apply(self) -> None:
        with (
            patch("infrafoundry.core.config.ConfigManager") as manager,
            patch(f"{MODULE}.BaseService.client_from_environment") as factory,
        ):
            env = manager.return_value.load_environment.return_value
            env.get_provider_settings.return_value = {}
            line = run_ha_sync_after_apply("env", "opnsense", Path("cfg"), False)
        factory.assert_not_called()
        assert line == "HA sync skipped: nothing changed"

    def test_always_syncs_without_changes(self) -> None:
        line, client = _run({"ha_sync_after_apply": "always"}, changed=False)
        assert client.request.call_count == 3
        assert line.startswith(f"HA sync to backup {BACKUP}")

    def test_empty_target_only_reads_settings(self) -> None:
        line, client = _run({}, changed=True, target="", replies=[])
        client.request.assert_called_once_with("GET", "core/hasync/get")
        assert line == "HA sync skipped: no synchronize_to_ip on this node"

    def test_version_then_restart_all_once_each(self) -> None:
        line, client = _run({}, changed=True)
        calls = [c.args for c in client.request.call_args_list]
        assert calls == [
            ("GET", "core/hasync/get"),
            ("POST", "core/hasync_status/version"),
            ("POST", "core/hasync_status/restartAll"),
        ]
        assert line == f"HA sync to backup {BACKUP}: synchronized and reconfigured 2 service(s)"

    def test_line_omits_missing_count(self) -> None:
        line, _ = _run({}, changed=True, replies=[{"response": {"v": 1}}, {"status": "ok"}])
        assert line == f"HA sync to backup {BACKUP}: synchronized and reconfigured"

    def test_version_error_stops_before_restart_all(self) -> None:
        with pytest.raises(APIError, match="remote host down"):
            _run(
                {},
                changed=True,
                replies=[{"status": "error", "message": "remote host down"}],
            )

    def test_version_error_never_calls_restart_all(self) -> None:
        client = MagicMock()
        client.request.side_effect = [
            {"hasync": {"synchronizetoip": BACKUP}},
            {"status": "error", "message": "down"},
        ]
        env = MagicMock()
        env.get_provider_settings.return_value = {}
        with (
            patch("infrafoundry.core.config.ConfigManager") as manager,
            patch(f"{MODULE}.BaseService.client_from_environment", return_value=client),
            pytest.raises(APIError),
        ):
            manager.return_value.load_environment.return_value = env
            run_ha_sync_after_apply("env", "opnsense", Path("cfg"), True)
        paths = [c.args[1] for c in client.request.call_args_list]
        assert "core/hasync_status/restartAll" not in paths

    def test_client_is_built_with_the_configured_timeout(self) -> None:
        _, client = _run({"ha_sync_timeout": 77}, changed=True)
        client.factory.assert_called_once_with("env", "opnsense", Path("cfg"), timeout=77)

    def test_default_timeout_is_300(self) -> None:
        _, client = _run({}, changed=True)
        assert client.factory.call_args.kwargs == {"timeout": 300}


def test_client_from_environment_passes_timeout() -> None:
    from infrafoundry.providers.opnsense.services.base import BaseService

    settings = {"api_url": "https://fw.example.com", "api_key": "k", "api_secret": "s"}
    with (
        patch("infrafoundry.core.config.ConfigManager") as manager,
        patch("infrafoundry.providers.opnsense.services.base.OPNsenseClient") as cls,
    ):
        manager.return_value.load_environment.return_value.get_provider_settings.return_value = (
            settings
        )
        BaseService.client_from_environment("env", "opnsense", Path("cfg"), timeout=45)
        BaseService.client_from_environment("env", "opnsense", Path("cfg"))
    assert cls.call_args_list[0].kwargs["timeout"] == 45
    assert "timeout" not in cls.call_args_list[1].kwargs
