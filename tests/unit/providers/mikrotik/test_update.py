"""The ``system.package.update`` component: checks, plan lines and the two-stage upgrader."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pytest
import yaml

from infrafoundry.core.config.package_loader import PackageLoader
from infrafoundry.providers.mikrotik.client import RouterOSAPIError, RouterOSConnectionError
from infrafoundry.providers.mikrotik.components.update import (
    UPDATE_TYPE,
    RouterBoardStatus,
    RouterOSUpdateCheckError,
    RouterOSUpgradeError,
    RouterOSUpgrader,
    UpdateStatus,
    check_update,
    check_update_resources,
    current_versions,
    declared_channel,
    parse_check_reply,
    parse_routerboard,
    parse_update,
    plan_line,
    read_routerboard,
    uptime_seconds,
)

from .conftest import resource
from .update_fake import SERIAL, FakeClock, FakeUpdateDevice

pytestmark = pytest.mark.unit


def _findings(*resources: Any) -> str:
    return "\n".join(f.message for f in check_update_resources(list(resources)))


def _upgrader(device: FakeUpdateDevice) -> tuple[RouterOSUpgrader, FakeClock]:
    clock = FakeClock()
    return RouterOSUpgrader(device, sleep=clock.sleep, clock=clock.clock, poll_interval=5.0), clock


# -- resource checks


def test_bare_entry_validates_clean(tmp_path: Path) -> None:
    envs = tmp_path / "envs"
    package = envs / "dev" / "mikrotik" / "demo"
    package.mkdir(parents=True)
    (package / "infrafoundry.yml").write_text("name: demo\nresources:\n  - resources.yaml\n")
    body = {"resources": [{"name": "ros", "type": UPDATE_TYPE, "provider": "mikrotik"}]}
    (package / "resources.yaml").write_text(yaml.safe_dump(body))
    resources, _e, _v = PackageLoader(envs).load_package(
        package, provider="mikrotik", env_name="dev"
    )
    assert check_update_resources(resources) == []
    assert declared_channel(resources[0]) == "stable"


@pytest.mark.parametrize("channel", ["stable", "long-term", "testing", "development"])
def test_valid_channels(channel: str) -> None:
    assert _findings(resource(UPDATE_TYPE, "ros", channel=channel)) == ""
    assert declared_channel(resource(UPDATE_TYPE, "ros", channel=channel)) == channel


def test_invalid_channel_unknown_field_and_duplicates() -> None:
    assert "'channel' must be one of" in _findings(resource(UPDATE_TYPE, "ros", channel="beta"))
    assert "unknown field(s): version" in _findings(resource(UPDATE_TYPE, "ros", version="7.25"))
    assert "only one" in _findings(resource(UPDATE_TYPE, "a"), resource(UPDATE_TYPE, "b"))
    assert "resource name" in _findings(resource(UPDATE_TYPE, "bad name"))
    assert _findings(resource("ip.service", "x", bogus=1)) == ""


# -- parsing


def test_parse_update() -> None:
    with pytest.raises(RouterOSUpdateCheckError):
        parse_update({"channel": "stable"})
    status = parse_update({"installed-version": "7.24", "channel": "stable"})
    assert status.latest_version is None and not status.update_available


def test_parse_check_reply() -> None:
    sections = [
        {"status": "finding out latest version..."},
        {"latest-version": "7.25", "status": "New version is available"},
    ]
    assert parse_check_reply(sections) == sections[1]
    assert parse_check_reply([sections[0]]) is None
    assert parse_check_reply(None) is None
    with pytest.raises(RouterOSUpdateCheckError):
        parse_check_reply([{"status": "ERROR: could not resolve host"}])


@pytest.mark.parametrize(
    ("status", "latest", "expected"),
    [
        ("New version is available", "7.25", True),
        ("System is already up to date", "7.24", False),
        (None, "7.25", True),
        (None, "7.24", False),
        (None, None, False),
    ],
)
def test_update_available(status: str | None, latest: str | None, expected: bool) -> None:
    assert UpdateStatus("7.24", latest, status, "stable").update_available is expected


def test_parse_routerboard_and_lag() -> None:
    lag = parse_routerboard(
        {"routerboard": "true", "current-firmware": "7.20", "upgrade-firmware": "7.25"}
    )
    assert lag.present and lag.lags
    assert not parse_routerboard({"routerboard": "false"}).present
    assert not parse_routerboard({"routerboard": "true"}).present
    same = parse_routerboard(
        {"routerboard": "yes", "current-firmware": "7.25", "upgrade-firmware": "7.25"}
    )
    assert same.present and not same.lags


def test_read_routerboard_absent_and_errors() -> None:
    device = FakeUpdateDevice()
    device.routerboard_error = RouterOSAPIError("no such command", 404)
    assert not read_routerboard(device).present
    device.routerboard_error = RouterOSAPIError("boom", 500)
    with pytest.raises(RouterOSAPIError):
        read_routerboard(device)
    device.routerboard_error = RouterOSConnectionError("down")
    with pytest.raises(RouterOSConnectionError):
        read_routerboard(device)


def test_serial_number_is_never_kept(caplog: pytest.LogCaptureFixture) -> None:
    device = FakeUpdateDevice(upgrade_fw="7.25")
    with caplog.at_level(logging.DEBUG):
        state = check_update(device, "stable")
    assert SERIAL not in repr(state) and SERIAL not in caplog.text


# -- check_update and plan lines


def test_check_update_posts_check_when_channel_matches() -> None:
    device = FakeUpdateDevice()
    state = check_update(device, "stable")
    assert device.paths() == ["system/package/update/check-for-updates"]
    assert state.update.update_available and state.channel_mismatch is None


def test_check_update_falls_back_to_get_without_sections() -> None:
    device = FakeUpdateDevice()
    device.check_reply_as_list = False
    assert check_update(device, "stable").update.latest_version == "7.25"


def test_channel_mismatch_makes_no_post() -> None:
    device = FakeUpdateDevice(channel="long-term")
    state = check_update(device, "stable")
    assert device.posts == []
    assert state.channel_mismatch == ("long-term", "stable")
    line, warning = plan_line("ros", state, "dev")
    assert warning and "device follows 'long-term', resource declares 'stable'" in line


def test_plan_lines() -> None:
    up = check_update(FakeUpdateDevice(latest="7.24"), "stable")
    assert plan_line("ros", up, "dev") == (f"{UPDATE_TYPE} 'ros': up to date (7.24)", False)
    ros = plan_line("ros", check_update(FakeUpdateDevice(), "stable"), "dev")
    assert "7.24 → 7.25 available" in ros[0] and "--env dev" in ros[0] and not ros[1]
    fw = plan_line(
        "ros", check_update(FakeUpdateDevice(latest="7.24", upgrade_fw="7.25"), "stable"), "dev"
    )
    assert "RouterBOARD firmware 7.20 → 7.25 pending" in fw[0] and "available" not in fw[0]
    both = plan_line("ros", check_update(FakeUpdateDevice(upgrade_fw="7.25"), "stable"), "dev")
    assert "available" in both[0] and "pending" in both[0]


def test_uptime_parsing() -> None:
    assert uptime_seconds("1w2d3h4m5s") == 604800 + 2 * 86400 + 3 * 3600 + 4 * 60 + 5
    assert uptime_seconds("45s") == 45
    assert uptime_seconds("") is None and uptime_seconds(None) is None


def test_current_versions_best_effort() -> None:
    assert "RouterOS 7.24" in current_versions(FakeUpdateDevice())
    device = FakeUpdateDevice()
    device.routerboard_error = RouterOSConnectionError("down")
    assert "unreachable" in current_versions(device)


# -- upgrader, stage 1


@pytest.mark.parametrize("reply", [[{"status": "ok"}], {"status": "ok"}, None])
def test_install_accepts_any_reply_shape(reply: Any) -> None:
    device = FakeUpdateDevice()
    device.install_reply = reply
    upgrader, _ = _upgrader(device)
    report = upgrader.upgrade("7.25", 600)
    assert report.routeros_version == "7.25" and device.installed == "7.25"
    assert "system/package/update/install" in device.paths()


def test_install_connection_drop_means_going_down() -> None:
    device = FakeUpdateDevice()
    device.install_drops = True
    upgrader, _ = _upgrader(device)
    assert upgrader.upgrade("7.25", 600).routeros_version == "7.25"


def test_down_detected_by_uptime_reset() -> None:
    device = FakeUpdateDevice()
    device.never_unreachable = True
    upgrader, _ = _upgrader(device)
    assert upgrader.upgrade("7.25", 600).routeros_version == "7.25"


def _fails(
    device: FakeUpdateDevice, expected: str | None, timeout: int = 600
) -> RouterOSUpgradeError:
    upgrader, _ = _upgrader(device)
    with pytest.raises(RouterOSUpgradeError) as caught:
        upgrader.upgrade(expected, timeout)
    return caught.value


def test_offer_changed_sends_no_install() -> None:
    device = FakeUpdateDevice(latest="7.26")
    error = _fails(device, "7.25")
    assert error.step == "check" and "offer changed" in str(error)
    assert "system/package/update/install" not in device.paths()


def test_install_api_error() -> None:
    device = FakeUpdateDevice()
    device.errors["system/package/update/install"] = RouterOSAPIError("refused", 400)
    assert _fails(device, "7.25").step == "install"


def test_error_status_while_waiting() -> None:
    device = FakeUpdateDevice()
    device.install_status = "ERROR: download failed"
    device.grace = 5
    assert _fails(device, "7.25").step == "install"


def test_timeout_waiting_for_down() -> None:
    device = FakeUpdateDevice()
    device.grace = 10**6
    error = _fails(device, "7.25", 120)
    assert error.step == "reboot-wait" and "reboot" in str(error)


def test_timeout_waiting_for_up() -> None:
    device = FakeUpdateDevice()
    device.down_polls = 10**6
    error = _fails(device, "7.25", 120)
    assert error.step == "reboot-wait" and "come back" in str(error)


def test_returned_on_old_version() -> None:
    device = FakeUpdateDevice()
    device.version_after = "7.24"
    error = _fails(device, "7.25")
    assert error.step == "verify-routeros" and "returned on 7.24" in str(error)


# -- upgrader, stage 2


def test_routerboard_stage_runs_after_routeros() -> None:
    device = FakeUpdateDevice(upgrade_fw="7.25")
    upgrader, _ = _upgrader(device)
    report = upgrader.upgrade("7.25", 600)
    assert report.firmware_version == "7.25" and device.current_fw == "7.25"
    paths = device.paths()
    assert paths.index("system/routerboard/upgrade") < paths.index("system/reboot")


def test_routerboard_only_when_routeros_current() -> None:
    device = FakeUpdateDevice(latest="7.24", upgrade_fw="7.25")
    upgrader, _ = _upgrader(device)
    report = upgrader.upgrade(None, 600)
    assert report.routeros_version is None and report.firmware_version == "7.25"
    assert "system/package/update/install" not in device.paths()


def test_reboot_connection_drop_accepted() -> None:
    device = FakeUpdateDevice(upgrade_fw="7.25")
    device.reboot_drops = True
    upgrader, _ = _upgrader(device)
    assert upgrader.upgrade(None, 600).firmware_version == "7.25"


def test_firmware_unchanged_after_reboot_fails() -> None:
    device = FakeUpdateDevice(upgrade_fw="7.25")
    device.fw_after = "7.20"
    error = _fails(device, None)
    assert error.step == "verify-routerboard"


def test_routerboard_upgrade_and_reboot_errors() -> None:
    device = FakeUpdateDevice(upgrade_fw="7.25")
    device.errors["system/routerboard/upgrade"] = RouterOSAPIError("no", 400)
    assert _fails(device, None).step == "routerboard-upgrade"
    device = FakeUpdateDevice(upgrade_fw="7.25")
    device.errors["system/reboot"] = RouterOSAPIError("no", 400)
    assert _fails(device, None).step == "reboot"


@pytest.mark.parametrize("routerboard", [None, False])
def test_routerboard_stage_skipped_on_chr(routerboard: bool | None) -> None:
    device = FakeUpdateDevice(routerboard=routerboard)
    upgrader, _ = _upgrader(device)
    report = upgrader.upgrade("7.25", 600)
    assert report.routerboard_skipped and report.firmware_version is None
    assert "system/reboot" not in device.paths()


def test_routerboard_404_skips_stage() -> None:
    device = FakeUpdateDevice()
    device.routerboard_error = RouterOSAPIError("no such command", 404)
    upgrader, _ = _upgrader(device)
    assert upgrader.upgrade("7.25", 600).routerboard_skipped


def test_each_stage_has_its_own_deadline() -> None:
    device = FakeUpdateDevice(upgrade_fw="7.25")
    device.down_polls = 20  # about 100 s of polling per reboot, under the 150 s deadline
    upgrader, clock = _upgrader(device)
    report = upgrader.upgrade("7.25", 150)
    assert report.firmware_version == "7.25"
    assert clock.now > 150  # the total exceeds one deadline


def test_dataclass_defaults() -> None:
    assert not RouterBoardStatus(present=False).lags
