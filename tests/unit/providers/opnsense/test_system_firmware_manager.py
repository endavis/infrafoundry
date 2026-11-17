"""Unit tests for ``SystemFirmwareManager`` (#806 keystone).

Coverage:
    - Standard 8-test singleton template (plan/apply no-change/update,
      destroy noop, get_resource_ids, plan-raises-on-multiple).
    - Plus 3 firmware-specific tests:
      - test_plan_install_missing_plugins: 3 desired, 1 live -> 2 add entries
      - test_apply_install_calls_per_plugin: install_plugin called once per
        missing plugin
      - test_plan_warns_on_extras: extras detected, warning logged, no remove
        call
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock, patch

import httpx
import pytest

from infrafoundry.core.exceptions import (
    APIError,
    AuthenticationError,
    InvalidConfigurationError,
)
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.components.system_firmware import (
    SystemFirmwareManager,
)
from infrafoundry.providers.opnsense.services.system_firmware import SystemFirmwareService

SERVICE_PATH = "infrafoundry.providers.opnsense.components.system_firmware.SystemFirmwareService"


def _resource(
    *, plugins: list[str] | None = None, extra: dict[str, Any] | None = None
) -> ResourceConfig:
    return ResourceConfig(
        name="system.firmware",
        type="system.firmware",
        provider="opnsense",
        config={
            "plugins": plugins if plugins is not None else ["os-tailscale"],
            **(extra or {}),
        },
    )


def _make_service_mock(
    *,
    installed: list[str] | None = None,
    settings: dict[str, str] | None = None,
) -> SystemFirmwareService:
    """Build a real ``SystemFirmwareService`` over a mocked ``SystemClient``.

    ``core/firmware/info`` and ``core/firmware/get`` are separate reads, so
    the mock answers each with its live shape (``installed`` is ``"0"``/``"1"``).
    """
    installed_set = set(installed or [])
    service = SystemFirmwareService(MagicMock())
    client = MagicMock()

    def _info() -> dict[str, Any]:
        return {
            "plugin": [
                {"name": p, "installed": "1", "locked": "N/A"} for p in sorted(installed_set)
            ]
            + [{"name": "os-other", "installed": "0", "locked": "N/A"}]
        }

    def _install(name: str) -> dict[str, Any]:
        # The install job completes: later reads of firmware/info show the plugin.
        installed_set.add(name)
        return {"status": "ok"}

    client.get_firmware_info.side_effect = _info
    client.get_upgrade_status.return_value = {"status": "done", "log": ""}
    client.get_firmware_settings.return_value = {
        "firmware": {
            "mirror": "",
            "flavour": "",
            "type": "",
            "subscription": "",
            "reboot": "0",
            **(settings or {}),
        }
    }
    client.install_plugin.side_effect = _install
    client.set_firmware_settings.return_value = {"result": "saved"}
    service.system_client = client
    return service


def _client(service: SystemFirmwareService) -> MagicMock:
    return cast(MagicMock, service.system_client)


# ---------------------------------------------------------------------------
# Standard 8-test template
# ---------------------------------------------------------------------------


class TestPlan:
    def test_plan_no_change(self, tmp_path: Path) -> None:
        manager = SystemFirmwareManager(tmp_path)
        service = _make_service_mock(installed=["os-tailscale"])
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            diff = manager.plan("test-env", [_resource(plugins=["os-tailscale"])])
        assert diff.is_empty

    def test_plan_update(self, tmp_path: Path) -> None:
        """A single missing plugin is one add and no update (plan matches apply, #1238)."""
        manager = SystemFirmwareManager(tmp_path)
        service = _make_service_mock(installed=[])
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            diff = manager.plan("test-env", [_resource(plugins=["os-acme-client"])])
        assert diff.adds == [{"plugin": "os-acme-client"}]
        assert diff.updates == []
        assert not diff.is_empty

    def test_plan_raises_on_multiple_resources(self, tmp_path: Path) -> None:
        manager = SystemFirmwareManager(tmp_path)
        with pytest.raises(InvalidConfigurationError):
            manager.plan("test-env", [_resource(), _resource()])


class TestApply:
    def test_apply_no_change(self, tmp_path: Path) -> None:
        manager = SystemFirmwareManager(tmp_path)
        service = _make_service_mock(installed=["os-tailscale"])
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            result = manager.apply("test-env", [_resource(plugins=["os-tailscale"])])
        _client(service).install_plugin.assert_not_called()
        assert result["resources_created"] == 0
        assert result["resources_updated"] == 0

    def test_apply_update(self, tmp_path: Path) -> None:
        manager = SystemFirmwareManager(tmp_path)
        service = _make_service_mock(installed=[])
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            result = manager.apply("test-env", [_resource(plugins=["os-acme-client"])])
        _client(service).install_plugin.assert_called_once_with("os-acme-client")
        assert result["resources_created"] == 1
        outcome = result["resource_outcomes"][0]
        assert outcome.action == "add"
        assert outcome.resource_name == "os-acme-client"


class TestDestroy:
    def test_destroy_noop(self, tmp_path: Path) -> None:
        """Firmware destroy never auto-uninstalls plugins."""
        manager = SystemFirmwareManager(tmp_path)
        result = manager.destroy("test-env", [_resource()])
        assert result["resources_destroyed"] == 0


class TestGetResourceIds:
    def test_get_resource_ids(self, tmp_path: Path) -> None:
        manager = SystemFirmwareManager(tmp_path)
        result = manager.get_resource_ids("test-env", [_resource()])
        assert result == {"system.firmware": "global"}

    def test_get_resource_ids_uses_resource_name(self, tmp_path: Path) -> None:
        custom = _resource().model_copy(update={"name": "custom"})
        result = SystemFirmwareManager(tmp_path).get_resource_ids("test-env", [custom])
        assert result == {"custom": "global"}

    def test_get_resource_ids_empty(self, tmp_path: Path) -> None:
        assert SystemFirmwareManager(tmp_path).get_resource_ids("test-env", []) == {}


# ---------------------------------------------------------------------------
# Firmware-specific tests
# ---------------------------------------------------------------------------


class TestPluginReconciliation:
    def test_plan_install_missing_plugins(self, tmp_path: Path) -> None:
        """3 desired, 1 live -> 2 install entries (sorted)."""
        manager = SystemFirmwareManager(tmp_path)
        service = _make_service_mock(installed=["os-tailscale"])
        desired = ["os-acme-client", "os-smart", "os-tailscale"]
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            diff = manager.plan("test-env", [_resource(plugins=desired)])
        # Sorted adds; "os-tailscale" already installed; no settings update.
        assert diff.adds == [{"plugin": "os-acme-client"}, {"plugin": "os-smart"}]
        assert diff.updates == []

    def test_apply_install_calls_per_plugin(self, tmp_path: Path) -> None:
        """install_plugin called once per missing plugin."""
        manager = SystemFirmwareManager(tmp_path)
        service = _make_service_mock(installed=["os-tailscale"])
        desired = ["os-acme-client", "os-smart", "os-tailscale"]
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            result = manager.apply("test-env", [_resource(plugins=desired)])
        assert _client(service).install_plugin.call_count == 2
        called_names = sorted(c.args[0] for c in _client(service).install_plugin.call_args_list)
        assert called_names == ["os-acme-client", "os-smart"]
        assert result["resources_created"] == 2

    def test_plan_warns_on_extras(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        """Extras (live but not desired) trigger warning, no remove call."""
        manager = SystemFirmwareManager(tmp_path)
        # Live has extras the YAML doesn't declare.
        service = _make_service_mock(installed=["os-tailscale", "os-old-extra", "os-another-extra"])
        desired: list[str] = ["os-tailscale"]
        with caplog.at_level(logging.WARNING), patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            diff = manager.plan("test-env", [_resource(plugins=desired)])
        # Extras should be warned about (one log per extra).
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) >= 2
        warning_text = " ".join(r.getMessage() for r in warnings)
        assert "os-old-extra" in warning_text
        assert "os-another-extra" in warning_text
        # And no plugin should be planned for install.
        assert diff.adds == []
        assert diff.is_empty
        # Critical: ``remove_plugin`` MUST NOT be called for extras.
        _client(service).remove_plugin.assert_not_called()


class TestSettings:
    def test_plan_empty_when_yaml_omits_settings_and_live_has_mirror(self, tmp_path: Path) -> None:
        manager = SystemFirmwareManager(tmp_path)
        service = _make_service_mock(installed=["os-tailscale"], settings={"mirror": "https://m"})
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            diff = manager.plan("test-env", [_resource(plugins=["os-tailscale"])])
        assert diff.is_empty

    def test_plan_shows_settings_drift(self, tmp_path: Path) -> None:
        manager = SystemFirmwareManager(tmp_path)
        service = _make_service_mock(installed=["os-tailscale"], settings={"mirror": "old"})
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            diff = manager.plan(
                "test-env",
                [_resource(plugins=["os-tailscale"], extra={"mirror": "new"})],
            )
        assert diff.updates == [{"settings": {"mirror": "new"}}]
        assert diff.adds == []

    def test_apply_installs_then_writes_drifted_keys_only(self, tmp_path: Path) -> None:
        manager = SystemFirmwareManager(tmp_path)
        service = _make_service_mock(installed=[], settings={"mirror": "old", "flavour": "latest"})
        resource = _resource(
            plugins=["os-acme-client", "os-smart"], extra={"mirror": "new", "flavour": "latest"}
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            result = manager.apply("test-env", [resource])
        client = _client(service)
        assert client.install_plugin.call_count == 2
        client.set_firmware_settings.assert_called_once_with(
            {"firmware": {"mirror": "new", "flavour": "latest"}}
        )
        assert result["resources_created"] == 2
        assert result["resources_updated"] == 1
        settings_outcome = result["resource_outcomes"][-1]
        assert settings_outcome.address == "opnsense_system_firmware.settings"
        assert settings_outcome.action == "update"
        assert settings_outcome.resource_name == "system.firmware"

    def test_apply_no_set_when_only_plugins_differ(self, tmp_path: Path) -> None:
        manager = SystemFirmwareManager(tmp_path)
        service = _make_service_mock(installed=[])
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            result = manager.apply("test-env", [_resource(plugins=["os-smart"])])
        _client(service).set_firmware_settings.assert_not_called()
        assert result["resources_updated"] == 0

    def test_failed_set_raises_api_error(self, tmp_path: Path) -> None:
        manager = SystemFirmwareManager(tmp_path)
        service = _make_service_mock(installed=["os-tailscale"])
        _client(service).set_firmware_settings.return_value = {
            "result": "failed",
            "validations": {"firmware.mirror": "bad"},
        }
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            with pytest.raises(APIError):
                manager.apply(
                    "test-env",
                    [_resource(plugins=["os-tailscale"], extra={"mirror": "new"})],
                )

    def test_logs_carry_keys_not_values(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        manager = SystemFirmwareManager(tmp_path)
        service = _make_service_mock(installed=["os-tailscale"])
        with caplog.at_level(logging.DEBUG), patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            manager.apply(
                "test-env",
                [_resource(plugins=["os-tailscale"], extra={"mirror": "secret-mirror-value"})],
            )
        text = " ".join(r.getMessage() for r in caplog.records)
        assert "mirror" in text
        assert "secret-mirror-value" not in text


# ---------------------------------------------------------------------------
# Install verification and plan/apply parity (#1238)
# ---------------------------------------------------------------------------

TIME_PATH = "infrafoundry.providers.opnsense.services.system_firmware.time"
_LOG = "***GOT REQUEST TO INSTALL***\nInstallation out of date. The update is required.\n***DONE***"


def _never_installs(service: SystemFirmwareService) -> None:
    """Make the install job a no-op, as on a box that refuses the install."""
    _client(service).install_plugin.side_effect = lambda name: {"status": "ok"}


class TestWaitForPluginInstall:
    def test_succeeds_after_one_running_poll(self) -> None:
        service = _make_service_mock(installed=[])
        client = _client(service)
        installed_row = {"plugin": [{"name": "os-x", "installed": "1"}]}
        client.get_firmware_info.side_effect = [{"plugin": []}, installed_row]
        client.get_upgrade_status.return_value = {"status": "running", "log": ""}
        with patch(TIME_PATH) as fake_time:
            fake_time.monotonic.return_value = 0.0
            service.wait_for_plugin_install("os-x", timeout=30, interval=1)
        assert client.get_upgrade_status.call_count == 1
        fake_time.sleep.assert_called_once_with(1)

    def test_fails_when_job_done_but_not_installed(self) -> None:
        service = _make_service_mock(installed=[])
        _client(service).get_upgrade_status.return_value = {"status": "done", "log": _LOG}
        with patch(TIME_PATH) as fake_time:
            fake_time.monotonic.return_value = 0.0
            with pytest.raises(APIError) as exc:
                service.wait_for_plugin_install("os-x", timeout=30, interval=1)
        assert "os-x" in str(exc.value)
        assert "Installation out of date" in str(exc.value)

    def test_stale_done_gets_one_more_observation(self) -> None:
        """A first non-running status may be a stale one; a later running job is awaited."""
        service = _make_service_mock(installed=[])
        client = _client(service)
        client.get_firmware_info.side_effect = [
            {"plugin": []},
            {"plugin": []},
            {"plugin": [{"name": "os-x", "installed": "1"}]},
        ]
        client.get_upgrade_status.side_effect = [
            {"status": "done", "log": "old"},
            {"status": "running", "log": ""},
        ]
        with patch(TIME_PATH) as fake_time:
            fake_time.monotonic.return_value = 0.0
            service.wait_for_plugin_install("os-x", timeout=30, interval=1)
        assert client.get_upgrade_status.call_count == 2

    def test_times_out_with_log_tail_limited(self) -> None:
        service = _make_service_mock(installed=[])
        long_log = "\n".join(f"line {i}" for i in range(100))
        _client(service).get_upgrade_status.return_value = {"status": "running", "log": long_log}
        with patch(TIME_PATH) as fake_time:
            fake_time.monotonic.side_effect = [0.0, 1.0, 100.0]
            with pytest.raises(APIError) as exc:
                service.wait_for_plugin_install("os-x", timeout=10, interval=1)
        message = str(exc.value)
        assert "timed out" in message
        assert "line 99" in message
        assert "line 79" not in message

    @pytest.mark.parametrize("status", [{"status": "done"}, {"status": "done", "log": None}, []])
    def test_missing_or_non_str_log_still_raises_api_error(self, status: Any) -> None:
        service = _make_service_mock(installed=[])
        _client(service).get_upgrade_status.return_value = status
        with patch(TIME_PATH) as fake_time:
            fake_time.monotonic.return_value = 0.0
            with pytest.raises(APIError, match="os-x"):
                service.wait_for_plugin_install("os-x", timeout=30, interval=1)


class TestInstallLogSanitized:
    _KEY = "k3y-SECRET-0123"
    _SUB = "SUBSCRIPTION-xyz-789"
    _USER = "hunter2pw"
    _LOG = (
        "Fetching https://opnsense-update.deciso.com/" + _KEY + "/FreeBSD:14:amd64/26.1/latest"
        " failed\n"
        "proxy ftp://admin:" + _USER + "@mirror.example.org:8080/pkg?token=abc#frag.\n"
        "using subscription " + _SUB + " for repo\n"
        "Installation out of date. The update to opnsense-26.1.11_10 is required."
    )

    def _raise(self, settings: dict[str, str] | None, *, settings_fail: bool = False) -> APIError:
        service = _make_service_mock(installed=[], settings=settings)
        client = _client(service)
        client.get_upgrade_status.return_value = {"status": "done", "log": self._LOG}
        if settings_fail:
            client.get_firmware_settings.side_effect = RuntimeError("boom")
        with patch(TIME_PATH) as fake_time:
            fake_time.monotonic.return_value = 0.0
            with pytest.raises(APIError) as exc:
                service.wait_for_plugin_install("os-x", timeout=30, interval=1)
        return exc.value

    def _check(self, err: APIError, *, sub_masked: bool = True) -> None:
        secrets = [self._KEY, self._USER, "token=abc", "FreeBSD:14"]
        if sub_masked:
            secrets.append(self._SUB)
        for text in (str(err), str(err.response)):
            for secret in secrets:
                assert secret not in text
            assert "https://opnsense-update.deciso.com/***" in text
            assert "ftp://mirror.example.org:8080/***" in text
            assert "Installation out of date. The update to opnsense-26.1.11_10 is required." in (
                text
            )

    def test_urls_and_subscription_masked(self) -> None:
        self._check(self._raise({"subscription": self._SUB}))

    def test_settings_read_failure_falls_back_to_url_masking(self) -> None:
        self._check(self._raise(None, settings_fail=True), sub_masked=False)


class TestApplyVerifiesInstall:
    def test_apply_raises_when_plugin_not_installed(self, tmp_path: Path) -> None:
        manager = SystemFirmwareManager(tmp_path)
        service = _make_service_mock(installed=[], settings={"mirror": "old"})
        _never_installs(service)
        _client(service).get_upgrade_status.return_value = {"status": "done", "log": _LOG}
        resource = _resource(plugins=["os-acme-client"], extra={"mirror": "new"})
        with patch(SERVICE_PATH) as svc_cls, patch(TIME_PATH) as fake_time:
            fake_time.monotonic.return_value = 0.0
            svc_cls.from_environment.return_value = service
            with pytest.raises(APIError, match="os-acme-client"):
                manager.apply("test-env", [resource])
        _client(service).set_firmware_settings.assert_not_called()


class TestPlanApplyParity:
    @pytest.mark.parametrize(
        ("plugins", "extra", "live_mirror", "adds", "updates"),
        [
            (["os-a", "os-b"], None, "", 2, 0),
            (["os-tailscale"], {"mirror": "new"}, "old", 0, 1),
            (["os-a"], {"mirror": "new"}, "old", 1, 1),
        ],
        ids=["plugins-only", "settings-only", "both"],
    )
    def test_plan_counts_match_apply(
        self,
        tmp_path: Path,
        plugins: list[str],
        extra: dict[str, str] | None,
        live_mirror: str,
        adds: int,
        updates: int,
    ) -> None:
        manager = SystemFirmwareManager(tmp_path)
        resource = _resource(plugins=plugins, extra=extra)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = _make_service_mock(
                installed=["os-tailscale"], settings={"mirror": live_mirror}
            )
            diff = manager.plan("test-env", [resource])
            svc_cls.from_environment.return_value = _make_service_mock(
                installed=["os-tailscale"], settings={"mirror": live_mirror}
            )
            result = manager.apply("test-env", [resource])
        assert len(diff.adds) == adds == result["resources_created"]
        assert len(diff.updates) == updates == result["resources_updated"]


# ---------------------------------------------------------------------------
# Firmware update (#1452)
# ---------------------------------------------------------------------------

_STATUS_UPDATE = {
    "status": "update",
    "all_packages": {},
    "product_id": "opnsense",
    "product_version": "26.1.6_2",
    "status_reboot": "0",
    "upgrade_packages": [
        {"name": "opnsense", "current_version": "26.1.6_2", "new_version": "26.1.7"},
        {"name": "curl", "current_version": "8.0", "new_version": "8.1"},
    ],
}
_STATUS_NONE = {
    "status": "none",
    "all_packages": {},
    "product_id": "opnsense",
    "product_version": "26.1.6_2",
    "status_reboot": "0",
}


def _update_service(
    status: dict[str, Any],
    *,
    installed: list[str] | None = None,
    versions: list[str] | None = None,
) -> SystemFirmwareService:
    """Service mock whose check reports ``status`` and whose box reaches the new version.

    ``versions`` are the successive ``product_version`` answers of
    ``firmware/info`` once the update has been started; before that the box
    runs the status' own version.
    """
    service = _make_service_mock(installed=installed)
    client = _client(service)
    base_info = client.get_firmware_info.side_effect
    state = {"updated": False}
    queue = list(versions if versions is not None else ["26.1.7"])

    def _info() -> dict[str, Any]:
        info: dict[str, Any] = base_info()
        if not state["updated"]:
            info["product_version"] = status.get("product_version", "")
        else:
            info["product_version"] = queue.pop(0) if len(queue) > 1 else queue[0]
        return info

    def _update() -> dict[str, Any]:
        state["updated"] = True
        return {"status": "ok", "msg_uuid": "x"}

    client.get_firmware_info.side_effect = _info
    client.check_firmware.return_value = {"status": "ok", "msg_uuid": "x"}
    client.get_firmware_status.return_value = status
    client.update_firmware.side_effect = _update
    return service


def _plan(
    manager: SystemFirmwareManager, service: SystemFirmwareService, resource: ResourceConfig
) -> Any:
    with patch(SERVICE_PATH) as svc_cls, patch(TIME_PATH) as fake_time:
        fake_time.monotonic.return_value = 0.0
        svc_cls.from_environment.return_value = service
        return manager.plan("test-env", [resource])


def _apply(
    manager: SystemFirmwareManager, service: SystemFirmwareService, resource: ResourceConfig
) -> Any:
    with patch(SERVICE_PATH) as svc_cls, patch(TIME_PATH) as fake_time:
        fake_time.monotonic.return_value = 0.0
        svc_cls.from_environment.return_value = service
        return manager.apply("test-env", [resource])


class TestPlanFirmwareUpdate:
    def test_update_absent_calls_no_firmware_update_endpoint(self, tmp_path: Path) -> None:
        service = _update_service(_STATUS_UPDATE, installed=["os-tailscale"])
        diff = _plan(SystemFirmwareManager(tmp_path), service, _resource(plugins=["os-tailscale"]))
        client = _client(service)
        assert diff.is_empty
        client.check_firmware.assert_not_called()
        client.get_firmware_status.assert_not_called()
        client.update_firmware.assert_not_called()

    def test_update_false_calls_nothing(self, tmp_path: Path) -> None:
        service = _update_service(_STATUS_UPDATE, installed=["os-tailscale"])
        resource = _resource(plugins=["os-tailscale"], extra={"update": False})
        diff = _plan(SystemFirmwareManager(tmp_path), service, resource)
        assert diff.is_empty
        _client(service).check_firmware.assert_not_called()

    def test_current_box_plans_clean(self, tmp_path: Path) -> None:
        service = _update_service(_STATUS_NONE, installed=["os-tailscale"])
        resource = _resource(plugins=["os-tailscale"], extra={"update": True})
        diff = _plan(SystemFirmwareManager(tmp_path), service, resource)
        assert diff.is_empty
        assert diff.warnings == []
        _client(service).check_firmware.assert_called_once_with()

    def test_pending_update_is_a_change(self, tmp_path: Path) -> None:
        service = _update_service(_STATUS_UPDATE, installed=["os-tailscale"])
        resource = _resource(plugins=["os-tailscale"], extra={"update": True})
        diff = _plan(SystemFirmwareManager(tmp_path), service, resource)
        assert diff.updates == [{"firmware_update": {"from": "26.1.6_2", "to": "26.1.7"}}]
        assert not diff.is_empty
        _client(service).update_firmware.assert_not_called()

    def test_pending_update_with_reboot_warns(self, tmp_path: Path) -> None:
        service = _update_service(
            {**_STATUS_UPDATE, "status_reboot": "1"}, installed=["os-tailscale"]
        )
        resource = _resource(plugins=["os-tailscale"], extra={"update": True})
        diff = _plan(SystemFirmwareManager(tmp_path), service, resource)
        assert len(diff.warnings) == 1
        assert "reboot" in diff.warnings[0]

    def test_target_falls_back_to_current_without_product_row(self, tmp_path: Path) -> None:
        status = {**_STATUS_UPDATE, "upgrade_packages": [{"name": "curl", "new_version": "9"}]}
        service = _update_service(status, installed=["os-tailscale"])
        resource = _resource(plugins=["os-tailscale"], extra={"update": True})
        diff = _plan(SystemFirmwareManager(tmp_path), service, resource)
        assert diff.updates == [{"firmware_update": {"from": "26.1.6_2", "to": "26.1.6_2"}}]

    def test_major_upgrade_only_plans_clean(self, tmp_path: Path) -> None:
        status = {**_STATUS_NONE, "status": "upgrade"}
        service = _update_service(status, installed=["os-tailscale"])
        resource = _resource(plugins=["os-tailscale"], extra={"update": True})
        diff = _plan(SystemFirmwareManager(tmp_path), service, resource)
        assert diff.is_empty

    def test_error_status_warns_without_entry(self, tmp_path: Path) -> None:
        status = {"status": "error", "status_msg": "Could not connect to https://pkg.example.com/x"}
        service = _update_service(status, installed=["os-tailscale"])
        resource = _resource(plugins=["os-tailscale"], extra={"update": True})
        diff = _plan(SystemFirmwareManager(tmp_path), service, resource)
        assert diff.is_empty
        assert len(diff.warnings) == 1
        assert "Could not connect" in diff.warnings[0]
        assert "/x" not in diff.warnings[0]

    def test_no_check_data_warns(self, tmp_path: Path) -> None:
        service = _update_service({"status": "none"}, installed=["os-tailscale"])
        resource = _resource(plugins=["os-tailscale"], extra={"update": True})
        diff = _plan(SystemFirmwareManager(tmp_path), service, resource)
        assert diff.is_empty
        assert len(diff.warnings) == 1

    def test_update_and_settings_drift_are_two_updates(self, tmp_path: Path) -> None:
        service = _update_service(_STATUS_UPDATE, installed=["os-tailscale"])
        resource = _resource(
            plugins=["os-tailscale"], extra={"update": True, "mirror": "https://m.example.com"}
        )
        diff = _plan(SystemFirmwareManager(tmp_path), service, resource)
        assert len(diff.updates) == 2
        assert "firmware_update" in diff.updates[0]
        assert "settings" in diff.updates[1]

    def test_check_wait_times_out(self, tmp_path: Path) -> None:
        service = _update_service(_STATUS_UPDATE, installed=["os-tailscale"])
        _client(service).get_upgrade_status.return_value = {"status": "running", "log": ""}
        resource = _resource(plugins=["os-tailscale"], extra={"update": True})
        with patch(SERVICE_PATH) as svc_cls, patch(TIME_PATH) as fake_time:
            fake_time.monotonic.side_effect = [0.0, 301.0]
            svc_cls.from_environment.return_value = service
            with pytest.raises(APIError, match="timed out"):
                SystemFirmwareManager(tmp_path).plan("test-env", [resource])


class TestApplyFirmwareUpdate:
    def test_update_absent_calls_nothing(self, tmp_path: Path) -> None:
        service = _update_service(_STATUS_UPDATE, installed=["os-tailscale"])
        result = _apply(
            SystemFirmwareManager(tmp_path), service, _resource(plugins=["os-tailscale"])
        )
        client = _client(service)
        client.check_firmware.assert_not_called()
        client.update_firmware.assert_not_called()
        assert result["resources_updated"] == 0

    def test_current_box_makes_no_update_call(self, tmp_path: Path) -> None:
        service = _update_service(_STATUS_NONE, installed=["os-tailscale"])
        resource = _resource(plugins=["os-tailscale"], extra={"update": True})
        result = _apply(SystemFirmwareManager(tmp_path), service, resource)
        _client(service).update_firmware.assert_not_called()
        assert result["resources_updated"] == 0

    def test_update_runs_before_plugins_and_settings(self, tmp_path: Path) -> None:
        service = _update_service(_STATUS_UPDATE, installed=[])
        client = _client(service)
        calls: list[str] = []

        def _rec(name: str, value: Any) -> Any:
            calls.append(name)
            return value

        client.check_firmware.side_effect = lambda: _rec("check", {"status": "ok"})
        orig_update = client.update_firmware.side_effect
        client.update_firmware.side_effect = lambda: _rec("update", orig_update())
        orig_install = client.install_plugin.side_effect
        client.install_plugin.side_effect = lambda n: _rec("install", orig_install(n))
        client.set_firmware_settings.side_effect = lambda p: _rec("settings", {"result": "saved"})
        client.get_upgrade_status.return_value = {"status": "done", "log": ""}
        resource = _resource(
            plugins=["os-acme-client"], extra={"update": True, "mirror": "https://m.example.com"}
        )
        result = _apply(SystemFirmwareManager(tmp_path), service, resource)
        assert calls == ["check", "update", "install", "settings"]
        assert result["resources_created"] == 1
        assert result["resources_updated"] == 2
        outcomes = [(o.address, o.action) for o in result["resource_outcomes"]]
        assert outcomes == [
            ("opnsense_system_firmware.update", "update"),
            ("opnsense_firmware_plugin.os-acme-client", "add"),
            ("opnsense_system_firmware.settings", "update"),
        ]

    def test_error_status_raises_before_any_write(self, tmp_path: Path) -> None:
        service = _update_service({"status": "error", "status_msg": "boom"}, installed=[])
        resource = _resource(plugins=["os-acme-client"], extra={"update": True})
        with pytest.raises(APIError, match="boom"):
            _apply(SystemFirmwareManager(tmp_path), service, resource)
        client = _client(service)
        client.update_firmware.assert_not_called()
        client.install_plugin.assert_not_called()

    def test_start_failure_raises(self, tmp_path: Path) -> None:
        service = _update_service(_STATUS_UPDATE, installed=[])
        client = _client(service)
        client.update_firmware.side_effect = APIError("refused", provider="opnsense")
        resource = _resource(plugins=["os-acme-client"], extra={"update": True})
        with pytest.raises(APIError, match="refused"):
            _apply(SystemFirmwareManager(tmp_path), service, resource)
        client.install_plugin.assert_not_called()

    def test_rejected_start_raises(self, tmp_path: Path) -> None:
        service = _update_service(_STATUS_UPDATE, installed=[])
        _client(service).update_firmware.side_effect = None
        _client(service).update_firmware.return_value = {"result": "failed"}
        resource = _resource(plugins=["os-acme-client"], extra={"update": True})
        with pytest.raises(APIError, match="rejected"):
            _apply(SystemFirmwareManager(tmp_path), service, resource)

    def test_update_timeout_is_passed_to_the_wait(self, tmp_path: Path) -> None:
        service = _update_service(_STATUS_UPDATE, installed=["os-tailscale"])
        resource = _resource(
            plugins=["os-tailscale"], extra={"update": True, "update_timeout": 900}
        )
        with patch.object(service, "wait_for_update") as wait:
            _apply(SystemFirmwareManager(tmp_path), service, resource)
        wait.assert_called_once_with("26.1.7", timeout=900)

    def test_update_timeout_defaults_to_1800(self, tmp_path: Path) -> None:
        service = _update_service(_STATUS_UPDATE, installed=["os-tailscale"])
        resource = _resource(plugins=["os-tailscale"], extra={"update": True})
        with patch.object(service, "wait_for_update") as wait:
            _apply(SystemFirmwareManager(tmp_path), service, resource)
        wait.assert_called_once_with("26.1.7", timeout=1800)


class TestWaitForUpdate:
    def _service(self, versions: list[str]) -> SystemFirmwareService:
        service = _make_service_mock()
        client = _client(service)
        queue = list(versions)
        client.get_firmware_info.side_effect = lambda: {
            "product_version": queue.pop(0) if len(queue) > 1 else queue[0],
            "plugin": [],
        }
        return service

    def test_success_through_a_reboot(self) -> None:
        service = self._service(["26.1.7"])
        client = _client(service)
        client.get_upgrade_status.side_effect = [
            {"status": "running", "log": "***GOT REQUEST TO UPDATE***"},
            {"status": "reboot", "log": "rebooting"},
            httpx.ConnectError("down"),
            APIError("bad gateway", status_code=502, provider="opnsense"),
            {"status": "error", "log": ""},
        ]
        with patch(TIME_PATH) as fake_time:
            fake_time.monotonic.return_value = 0.0
            service.wait_for_update("26.1.7", timeout=100, interval=1)
        assert fake_time.sleep.call_count == 4

    def test_transient_error_while_reading_info_is_in_progress(self) -> None:
        service = _make_service_mock()
        client = _client(service)
        client.get_upgrade_status.return_value = {"status": "done", "log": ""}
        client.get_firmware_info.side_effect = [
            APIError("503", status_code=503, provider="opnsense"),
            {"product_version": "26.1.7", "plugin": []},
        ]
        with patch(TIME_PATH) as fake_time:
            fake_time.monotonic.return_value = 0.0
            service.wait_for_update("26.1.7", timeout=100, interval=1)

    def test_failed_update_reports_log_tail(self) -> None:
        service = self._service(["26.1.6_2"])
        _client(service).get_upgrade_status.return_value = {
            "status": "done",
            "log": "line1\nFetching failed for https://pkg.example.com/secret/path\n***DONE***",
        }
        with patch(TIME_PATH) as fake_time:
            fake_time.monotonic.return_value = 0.0
            with pytest.raises(APIError) as exc:
                service.wait_for_update("26.1.7", timeout=100, interval=1)
        text = str(exc.value)
        assert "26.1.7" in text
        assert "Fetching failed" in text
        assert "secret/path" not in text
        assert "https://pkg.example.com/***" in text

    def test_stale_done_gets_one_more_observation(self) -> None:
        service = self._service(["26.1.6_2", "26.1.7"])
        _client(service).get_upgrade_status.return_value = {"status": "done", "log": ""}
        with patch(TIME_PATH) as fake_time:
            fake_time.monotonic.return_value = 0.0
            service.wait_for_update("26.1.7", timeout=100, interval=1)
        assert fake_time.sleep.call_count == 1

    def test_reboot_timeout_carries_the_last_log(self) -> None:
        service = self._service(["26.1.6_2"])
        client = _client(service)
        client.get_upgrade_status.side_effect = [
            {"status": "running", "log": "installing base"},
            httpx.ConnectError("down"),
            httpx.ConnectError("down"),
        ]
        with patch(TIME_PATH) as fake_time:
            fake_time.monotonic.side_effect = [0.0, 1.0, 2.0, 101.0]
            with pytest.raises(APIError) as exc:
                service.wait_for_update("26.1.7", timeout=100, interval=1)
        assert "timed out after 100s" in str(exc.value)
        assert "installing base" in str(exc.value)

    def test_authentication_error_is_not_swallowed(self) -> None:
        service = self._service(["26.1.7"])
        _client(service).get_upgrade_status.side_effect = AuthenticationError(
            "denied", provider="opnsense"
        )
        with patch(TIME_PATH) as fake_time:
            fake_time.monotonic.return_value = 0.0
            with pytest.raises(AuthenticationError):
                service.wait_for_update("26.1.7", timeout=100, interval=1)

    def test_subscription_is_masked_in_the_log(self) -> None:
        service = self._service(["26.1.6_2"])
        client = _client(service)
        client.get_firmware_settings.return_value = {
            "firmware": {"subscription": "sekret-key", "mirror": "", "reboot": "0"}
        }
        client.get_upgrade_status.return_value = {"status": "done", "log": "key sekret-key bad"}
        with patch(TIME_PATH) as fake_time:
            fake_time.monotonic.return_value = 0.0
            with pytest.raises(APIError) as exc:
                service.wait_for_update("26.1.7", timeout=100, interval=1)
        assert "sekret-key" not in str(exc.value)

    def test_partial_failure_with_expected_version_succeeds_with_warning(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        service = self._service(["26.1.7"])
        _client(service).get_upgrade_status.return_value = {
            "status": "done",
            "log": "Partial update failure",
        }
        with patch(TIME_PATH) as fake_time, caplog.at_level(logging.WARNING):
            fake_time.monotonic.return_value = 0.0
            service.wait_for_update("26.1.7", timeout=100, interval=1)
        assert "partial update failure" in caplog.text


class TestFirmwareUpdateConfigNeverWritten:
    def test_set_payload_carries_no_update_keys(self, tmp_path: Path) -> None:
        service = _update_service(_STATUS_NONE, installed=["os-tailscale"])
        resource = _resource(
            plugins=["os-tailscale"],
            extra={"update": True, "update_timeout": 900, "mirror": "https://m.example.com"},
        )
        _apply(SystemFirmwareManager(tmp_path), service, resource)
        payload = _client(service).set_firmware_settings.call_args.args[0]
        assert payload == {"firmware": {"mirror": "https://m.example.com"}}

    def test_export_has_no_update_keys(self) -> None:
        service = _make_service_mock(installed=["os-tailscale"])
        out = service.export_to_yaml()
        assert "update" not in out
