"""The glinet.firmware component: parsing, schema and the upgrade state machine (#1655)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest

from infrafoundry.providers.openwrt.glinet.firmware import (
    FIRMWARE_TYPE,
    FirmwareStatus,
    FirmwareUpgradeError,
    FirmwareUpgrader,
    check_firmware,
    check_firmware_resources,
    parse_check,
    plan_line,
)
from infrafoundry.providers.openwrt.glinet.rpc import GlinetApiDriftError, GlinetUnreachableError

from .conftest import res

pytestmark = pytest.mark.unit

OLD = {"current_version": "4.8.7", "current_type": "release"}
OFFER = {**OLD, "version_new": "4.8.8"}
NEW = {"current_version": "4.8.8", "current_type": "release"}
DOWN = GlinetUnreachableError("down")


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


class FakeClient:
    """Scripted RPC client; the last ``checks`` / ``probes`` entry repeats."""

    def __init__(
        self,
        checks: list[Any],
        statuses: list[Any] | None = None,
        probes: list[Any] | None = None,
        upgrade_reply: Any = None,
    ) -> None:
        self.checks = checks
        self.statuses = statuses or []
        self.probes = probes or [None]
        self.upgrade_reply = upgrade_reply if upgrade_reply is not None else {}
        self.calls: list[tuple[str, dict[str, Any] | None]] = []
        self.sessions = 0

    @contextmanager
    def session(self) -> Iterator[str]:
        self.sessions += 1
        yield "sid"

    def call(self, sid: str, module: str, method: str, params: dict[str, Any] | None = None) -> Any:
        self.calls.append((method, params))
        if method == "check_firmware_online":
            return self.checks.pop(0) if len(self.checks) > 1 else self.checks[0]
        if method == "upgrade_online":
            return self.upgrade_reply
        item = self.statuses.pop(0) if self.statuses else []
        if isinstance(item, Exception):
            raise item
        return item

    def probe_tls(self) -> None:
        item = self.probes.pop(0) if len(self.probes) > 1 else self.probes[0]
        if item is not None:
            raise item

    def methods(self) -> list[str]:
        return [m for m, _ in self.calls]


def _upgrader(client: FakeClient, clock: FakeClock, ssh: Any = None) -> FirmwareUpgrader:
    return FirmwareUpgrader(
        client,
        host_key_probe=ssh or (lambda: None),
        sleep=clock.sleep,
        clock=clock.clock,
        poll_interval=2.0,
        start_grace=60.0,
    )


# ----- parse_check -----


def test_parse_up_to_date() -> None:
    status = parse_check(OLD)
    assert (status.current_version, status.update_available) == ("4.8.7", False)


@pytest.mark.parametrize("empty", ["", None])
def test_parse_empty_version_new_is_up_to_date(empty: object) -> None:
    assert parse_check({**OLD, "version_new": empty}).update_available is False


def test_parse_offer() -> None:
    status = parse_check(OFFER)
    assert (status.version_new, status.update_available) == ("4.8.8", True)


@pytest.mark.parametrize(
    "reply",
    [
        [],
        "x",
        None,
        {"current_type": "release"},
        {"current_version": ""},
        {**OLD, "version_new": 5},
    ],
)
def test_parse_drift(reply: object) -> None:
    with pytest.raises(GlinetApiDriftError):
        parse_check(reply)


def test_check_firmware_uses_one_session() -> None:
    client = FakeClient([OFFER])
    assert check_firmware(client).version_new == "4.8.8"
    assert client.sessions == 1


def test_plan_line() -> None:
    assert plan_line("fw", FirmwareStatus("4.8.7", None, None), "dev") == (
        "glinet.firmware 'fw': up to date (4.8.7)"
    )
    line = plan_line("fw", FirmwareStatus("4.8.7", None, "4.8.8"), "dev")
    assert "4.8.7 → 4.8.8 available" in line
    assert "foundry provider openwrt upgrade --env dev" in line


# ----- schema -----


def test_schema_accepts_a_bare_resource() -> None:
    assert check_firmware_resources([res(FIRMWARE_TYPE, "fw")]) == []


def test_schema_rejects_fields_bad_names_and_duplicates() -> None:
    findings = check_firmware_resources(
        [
            res(FIRMWARE_TYPE, "fw", version="4.8.8"),
            res(FIRMWARE_TYPE, "bad name"),
            res(FIRMWARE_TYPE, "second"),
        ]
    )
    text = "\n".join(f.message for f in findings)
    assert "unknown field(s): version" in text
    assert "resource name may use only" in text
    assert "only one glinet.firmware resource" in text


# ----- upgrader -----


def test_upgrade_happy_path() -> None:
    clock = FakeClock()
    client = FakeClient(
        [OFFER, NEW],
        statuses=[[], {"status": 1, "percent": 40}, {"status": 6}],
        probes=[DOWN, DOWN, None],
    )
    ssh_calls: list[int] = []
    result = _upgrader(client, clock, lambda: ssh_calls.append(1)).upgrade("4.8.8", 1200)
    assert result.current_version == "4.8.8"
    upgrade_calls = [p for m, p in client.calls if m == "upgrade_online"]
    assert upgrade_calls == [{"keep_config": True, "keep_package": True}]
    assert ssh_calls == [1]


def test_connection_error_after_accepting_means_rebooting() -> None:
    clock = FakeClock()
    client = FakeClient([OFFER, NEW], statuses=[DOWN], probes=[DOWN, None])
    assert _upgrader(client, clock).upgrade("4.8.8", 1200).current_version == "4.8.8"


def test_need_reboot_flag_refuses_and_never_polls() -> None:
    client = FakeClient([OFFER], upgrade_reply={"need_reboot_flag": True})
    with pytest.raises(FirmwareUpgradeError, match="reboot it and rerun"):
        _upgrader(client, FakeClock()).upgrade("4.8.8", 1200)
    assert "get_online_upgrade_status" not in client.methods()


@pytest.mark.parametrize(
    ("code", "text"),
    [
        (2, "download failed"),
        (5, "image verification failed"),
        (7, "upgrade failed"),
        (9, "signature verification failed"),
    ],
)
def test_terminal_statuses(code: int, text: str) -> None:
    client = FakeClient([OFFER], statuses=[{"status": code}])
    with pytest.raises(FirmwareUpgradeError, match=text):
        _upgrader(client, FakeClock()).upgrade("4.8.8", 1200)


def test_never_started_fails_after_the_grace_period() -> None:
    client = FakeClient([OFFER])
    with pytest.raises(FirmwareUpgradeError, match="did not start"):
        _upgrader(client, FakeClock()).upgrade("4.8.8", 1200)


def test_unknown_status_keeps_polling_until_the_timeout() -> None:
    client = FakeClient([OFFER], statuses=[{"status": 99}] * 1000)
    with pytest.raises(FirmwareUpgradeError, match="timed out"):
        _upgrader(client, FakeClock()).upgrade("4.8.8", 300)


def test_timeout_while_the_device_is_down() -> None:
    client = FakeClient([OFFER], statuses=[{"status": 6}], probes=[DOWN])
    with pytest.raises(FirmwareUpgradeError, match="come back"):
        _upgrader(client, FakeClock()).upgrade("4.8.8", 300)


def test_device_never_goes_down_times_out() -> None:
    client = FakeClient([OFFER], statuses=[{"status": 6}], probes=[None])
    with pytest.raises(FirmwareUpgradeError, match="reboot"):
        _upgrader(client, FakeClock()).upgrade("4.8.8", 300)


def test_host_key_probe_failure_is_an_error() -> None:
    def ssh() -> None:
        raise FirmwareUpgradeError("ssh exited 255")

    client = FakeClient([OFFER, NEW], statuses=[{"status": 6}], probes=[DOWN, None])
    with pytest.raises(FirmwareUpgradeError, match="ssh exited 255"):
        _upgrader(client, FakeClock(), ssh).upgrade("4.8.8", 1200)


def test_other_probe_exceptions_are_wrapped() -> None:
    def ssh() -> None:
        raise OSError("no ssh")

    client = FakeClient([OFFER, NEW], statuses=[{"status": 6}], probes=[DOWN, None])
    with pytest.raises(FirmwareUpgradeError, match="host key could not be verified"):
        _upgrader(client, FakeClock(), ssh).upgrade("4.8.8", 1200)


def _scripted_ssh(failures: list[Exception]) -> tuple[Any, list[int]]:
    calls: list[int] = []

    def ssh() -> None:
        calls.append(1)
        if len(calls) <= len(failures):
            raise failures[len(calls) - 1]

    return ssh, calls


def test_host_key_probe_retries_mismatch_then_passes() -> None:
    mismatch = FirmwareUpgradeError("host key mismatch")
    ssh, calls = _scripted_ssh([mismatch, mismatch])
    clock = FakeClock()
    client = FakeClient([OFFER, NEW], statuses=[{"status": 6}], probes=[DOWN, None])
    result = _upgrader(client, clock, ssh).upgrade("4.8.8", 1200)
    assert result.current_version == "4.8.8"
    assert len(calls) == 3
    assert clock.now >= 4.0  # slept between the attempts


def test_host_key_mismatch_until_the_deadline_fails_before_the_version_check() -> None:
    def ssh() -> None:
        raise FirmwareUpgradeError("host key mismatch")

    client = FakeClient([OFFER, NEW], statuses=[{"status": 6}], probes=[DOWN, None])
    with pytest.raises(FirmwareUpgradeError, match="host key mismatch"):
        _upgrader(client, FakeClock(), ssh).upgrade("4.8.8", 300)
    assert client.methods().count("check_firmware_online") == 1  # only the offer check


def test_host_key_probe_other_exception_then_passes() -> None:
    ssh, calls = _scripted_ssh([OSError("no ssh yet")])
    client = FakeClient([OFFER, NEW], statuses=[{"status": 6}], probes=[DOWN, None])
    assert _upgrader(client, FakeClock(), ssh).upgrade("4.8.8", 1200).current_version == "4.8.8"
    assert len(calls) == 2


def test_host_key_probe_other_exception_until_the_deadline_is_wrapped() -> None:
    def ssh() -> None:
        raise OSError("no ssh")

    client = FakeClient([OFFER, NEW], statuses=[{"status": 6}], probes=[DOWN, None])
    with pytest.raises(FirmwareUpgradeError, match="could not be verified after the upgrade"):
        _upgrader(client, FakeClock(), ssh).upgrade("4.8.8", 300)
    assert client.methods().count("check_firmware_online") == 1


def test_coming_back_on_the_old_version_is_an_error() -> None:
    client = FakeClient([OFFER, OLD], statuses=[{"status": 6}], probes=[DOWN, None])
    with pytest.raises(FirmwareUpgradeError, match="did not install"):
        _upgrader(client, FakeClock()).upgrade("4.8.8", 1200)


def test_offer_changed_fails_before_upgrade_online() -> None:
    client = FakeClient([{**OLD, "version_new": "4.9.0"}])
    with pytest.raises(FirmwareUpgradeError, match="offer changed"):
        _upgrader(client, FakeClock()).upgrade("4.8.8", 1200)
    assert "upgrade_online" not in client.methods()
