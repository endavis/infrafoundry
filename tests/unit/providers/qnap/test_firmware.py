"""The firmware.update component: schema checks, the update check, plan lines, the upgrader."""

from __future__ import annotations

from typing import Any

import pytest

from infrafoundry.providers.qnap.client import (
    QnapApiDriftError,
    QnapAuthError,
    QnapTimeoutError,
    QnapUnreachableError,
)
from infrafoundry.providers.qnap.components.firmware import (
    FirmwareInfo,
    FirmwareState,
    QnapFirmwareUpgrader,
    QnapUpgradeError,
    UpdateOffer,
    check_firmware,
    check_firmware_resources,
    current_version,
    parse_offer,
    plan_line,
)

from .conftest import firmware
from .update_fake import FakeClock, FakeQnapSwitch

pytestmark = pytest.mark.unit


# -- schema
def test_valid_resource_has_no_findings() -> None:
    assert check_firmware_resources([firmware()]) == []


def test_unknown_field_second_resource_and_bad_name_are_errors() -> None:
    assert "unknown field" in check_firmware_resources([firmware(version="2.6")])[0].message
    assert "only one" in check_firmware_resources([firmware("a"), firmware("b")])[0].message
    assert "resource name" in check_firmware_resources([firmware("bad name")])[0].message


def test_entry_level_keys_are_not_fields() -> None:
    assert (
        check_firmware_resources([firmware(name="x", provider="qnap", type="firmware.update")])
        == []
    )


# -- check
def test_newer_offer() -> None:
    switch = FakeQnapSwitch()
    state = check_firmware(switch, 90)
    assert state.current == FirmwareInfo("2.5.0", "1")
    assert state.offer == UpdateOffer(True, "2.6.0", "2")
    assert switch.check_timeouts == [90]


def test_up_to_date() -> None:
    state = check_firmware(FakeQnapSwitch(offer=None), 90)
    assert state.offer == UpdateOffer(False)


def test_no_dns_server_skips_the_check_with_a_reason() -> None:
    switch = FakeQnapSwitch(dns=False)
    state = check_firmware(switch, 90)
    assert state.offer is None and "no DNS server" in str(state.skipped_reason)
    assert "firmware/update/check" not in switch.paths()


def test_excluded_product_skips_the_check() -> None:
    switch = FakeQnapSwitch(product="M5216")
    state = check_firmware(switch, 90)
    assert state.offer is None and state.skipped_reason is not None
    assert "firmware/update/check" not in switch.paths()


def test_check_timeout_propagates() -> None:
    switch = FakeQnapSwitch()
    switch.check_error = QnapTimeoutError("slow")
    with pytest.raises(QnapTimeoutError):
        check_firmware(switch, 90)


@pytest.mark.parametrize("reply", [{"newer": "yes"}, {"version": "1"}, {"newer": True}, [], None])
def test_drifted_check_reply(reply: Any) -> None:
    with pytest.raises(QnapApiDriftError):
        parse_offer(reply)


# -- plan lines
def test_plan_line_texts() -> None:
    current = FirmwareInfo("2.5.0")
    available = plan_line("fw", FirmwareState(current, UpdateOffer(True, "2.6.0")), "dev")
    assert available == (
        "firmware.update 'fw': 2.5.0 → 2.6.0 available "
        "(run foundry provider qnap upgrade --env dev)",
        False,
    )
    assert plan_line("fw", FirmwareState(current, UpdateOffer(False)), "dev") == (
        "firmware.update 'fw': up to date (2.5.0)",
        False,
    )
    line, warning = plan_line("fw", FirmwareState(current, None, "no DNS"), "dev")
    assert warning and "update check skipped: no DNS" in line


def test_current_version_is_best_effort() -> None:
    assert current_version(FakeQnapSwitch()) == "firmware 2.5.0"
    switch = FakeQnapSwitch()
    switch._going_down = True
    assert "unreachable" in current_version(switch)


# -- upgrader
def _upgrader(switch: FakeQnapSwitch) -> tuple[QnapFirmwareUpgrader, FakeClock]:
    clock = FakeClock()
    return QnapFirmwareUpgrader(switch, sleep=clock.sleep, clock=clock.clock), clock


def _step(switch: FakeQnapSwitch, timeout: int = 600) -> QnapUpgradeError:
    upgrader, _ = _upgrader(switch)
    with pytest.raises(QnapUpgradeError) as caught:
        upgrader.upgrade("2.6.0", timeout)
    return caught.value


def test_happy_path() -> None:
    switch = FakeQnapSwitch(progress=["preparing", "installing", "done"])
    upgrader, _ = _upgrader(switch)
    assert upgrader.upgrade("2.6.0", 600) == "2.6.0"
    assert switch.paths().count("firmware/update/live") == 1
    assert "firmware/update/check" not in switch.paths()  # no second check
    assert ("RENEW", "users/login") in switch.requests
    assert switch.logins == 1


def test_anomaly_refuses_before_any_install() -> None:
    switch = FakeQnapSwitch()
    switch.anomaly = True
    error = _step(switch)
    assert error.step == "precheck" and "flash busy" in str(error)
    assert "firmware/update/live" not in switch.paths()


def test_failed_progress_names_the_step_and_message() -> None:
    error = _step(FakeQnapSwitch(progress=["extracting", "failed"]))
    assert error.step == "progress" and "image rejected" in str(error)


def test_install_that_never_starts() -> None:
    error = _step(FakeQnapSwitch(progress=["none"]))
    assert error.step == "install" and "did not start" in str(error)


def test_unknown_progress_value_continues() -> None:
    switch = FakeQnapSwitch(progress=["rebooting-soon", "done"])
    upgrader, _ = _upgrader(switch)
    assert upgrader.upgrade("2.6.0", 600) == "2.6.0"


def test_connection_drop_during_the_poll_goes_to_the_up_wait() -> None:
    switch = FakeQnapSwitch(progress=["installing", "DROP"])
    upgrader, _ = _upgrader(switch)
    assert upgrader.upgrade("2.6.0", 600) == "2.6.0"


def test_install_post_connection_drop_goes_to_the_up_wait() -> None:
    switch = FakeQnapSwitch()
    switch.install_error = QnapUnreachableError("gone")
    switch._go_down(0)
    upgrader, _ = _upgrader(switch)
    assert upgrader.upgrade("2.6.0", 600) == "2.6.0"


def test_install_request_failure_names_install() -> None:
    switch = FakeQnapSwitch()
    switch.install_error = QnapAuthError("refused")
    assert _step(switch).step == "install"


def test_missed_reboot_with_the_right_version_succeeds() -> None:
    switch = FakeQnapSwitch(version="2.6.0")
    switch.never_down = True
    upgrader, _ = _upgrader(switch)
    assert upgrader.upgrade("2.6.0", 100) == "2.6.0"


def test_missed_reboot_with_the_wrong_version_times_out_in_reboot_wait() -> None:
    switch = FakeQnapSwitch()
    switch.never_down = True
    assert _step(switch, 100).step == "reboot-wait"


def test_timeout_waiting_to_come_back() -> None:
    switch = FakeQnapSwitch()
    switch.stay_down = True
    error = _step(switch, 100)
    assert error.step == "reboot-wait" and "come back" in str(error)


def test_refused_login_after_the_reboot_is_one_attempt() -> None:
    switch = FakeQnapSwitch()
    switch.login_errors = [QnapAuthError("refused")]
    error = _step(switch)
    assert error.step == "login" and switch.logins == 1


def test_version_mismatch_after_the_reboot() -> None:
    switch = FakeQnapSwitch(version_after="2.5.1")
    error = _step(switch)
    assert error.step == "verify" and "2.5.1" in str(error)


def test_401_during_the_poll_gets_one_fresh_login() -> None:
    switch = FakeQnapSwitch(progress=["installing", "401", "done"])
    upgrader, _ = _upgrader(switch)
    assert upgrader.upgrade("2.6.0", 600) == "2.6.0"
    assert switch.logins == 2  # the re-login and the post-reboot login


def test_second_401_aborts() -> None:
    error = _step(FakeQnapSwitch(progress=["401"]))
    assert error.step == "progress"


def test_failed_fresh_login_aborts() -> None:
    switch = FakeQnapSwitch(progress=["401"])
    switch.login_errors = [QnapAuthError("refused")]
    error = _step(switch)
    assert error.step == "progress" and switch.logins == 1
