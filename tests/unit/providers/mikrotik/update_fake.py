"""A scripted RouterOS device for the ``system.package.update`` tests (documentation values)."""

from __future__ import annotations

from typing import Any

from infrafoundry.providers.mikrotik.client import RouterOSAPIError, RouterOSConnectionError

FOREVER = 10**6
SERIAL = "SERIAL-EXAMPLE-0001"


class FakeClock:
    """Monotonic clock whose ``sleep`` advances it."""

    def __init__(self) -> None:
        self.now = 0.0

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


class FakeUpdateDevice:
    """Scripted ``get``/``post`` device. Only ``system/resource`` polls advance a reboot."""

    def __init__(
        self,
        *,
        installed: str = "7.24",
        latest: str = "7.25",
        channel: str = "stable",
        routerboard: bool | None = True,
        current_fw: str = "7.20",
        upgrade_fw: str = "7.20",
    ) -> None:
        self.installed = installed
        self.latest = latest
        self.channel = channel
        self.checked = False
        self.check_status: str | None = None
        self.check_reply_as_list = True
        self.routerboard = routerboard
        self.current_fw = current_fw
        self.upgrade_fw = upgrade_fw
        self.routerboard_error: Exception | None = None
        self.uptime = 3 * 86400
        self.posts: list[tuple[str, dict[str, Any] | None]] = []
        self.errors: dict[str, Exception] = {}
        self.install_reply: Any = None
        self.install_drops = False
        self.reboot_drops = False
        self.version_after: str | None = None
        self.fw_after: str | None = None
        self.never_unreachable = False
        self.grace = 1
        self.down_polls = 2
        self.install_status: str | None = None
        self._phase = "up"
        self._left = 0
        self._apply: str = ""

    # -- helpers
    def paths(self) -> list[str]:
        return [p for p, _ in self.posts]

    def _begin(self, kind: str) -> None:
        self._phase = "going_down"
        self._left = self.grace
        self._apply = kind

    def _finish(self) -> None:
        self._phase = "up"
        self.uptime = 30
        if self._apply == "routeros":
            self.installed = self.version_after or self.latest
            self.checked = False
        else:
            self.current_fw = self.fw_after or self.upgrade_fw

    def _tick(self) -> None:
        if self._phase == "going_down":
            self._left -= 1
            if self._left < 0:
                if self.never_unreachable:
                    self._finish()
                else:
                    self._phase, self._left = "down", self.down_polls
        elif self._phase == "down":
            self._left -= 1
            if self._left < 0:
                self._finish()

    # -- client surface
    def get(self, path: str) -> list[dict[str, str]]:
        if path == "system/resource":
            self._tick()
            if self._phase == "down":
                raise RouterOSConnectionError("unreachable")
            return [
                {
                    "version": self.installed,
                    "uptime": f"{self.uptime // 86400}d"
                    if self.uptime >= 86400
                    else f"{self.uptime}s",
                }
            ]
        if self._phase == "down":
            raise RouterOSConnectionError("unreachable")
        if path == "system/package/update":
            row = {"channel": self.channel, "installed-version": self.installed}
            if self.checked:
                row["latest-version"] = self.latest
                row["status"] = self.check_status or self._status()
            if self.install_status and self._phase == "going_down":
                row["status"] = self.install_status
            return [row]
        if path == "system/routerboard":
            if self.routerboard_error is not None:
                raise self.routerboard_error
            if self.routerboard is None:
                return [{"routerboard": "false"}]
            return [
                {
                    "routerboard": "true" if self.routerboard else "false",
                    "current-firmware": self.current_fw,
                    "upgrade-firmware": self.upgrade_fw,
                    "serial-number": SERIAL,
                    "model": "example-model",
                }
            ]
        raise AssertionError(f"unexpected GET {path}")

    def _status(self) -> str:
        return (
            "New version is available"
            if self.latest != self.installed
            else ("System is already up to date")
        )

    def post(self, path: str, body: dict[str, Any] | None = None) -> Any:
        self.posts.append((path, body))
        if path in self.errors:
            raise self.errors[path]
        if path == "system/package/update/check-for-updates":
            self.checked = True
            if not self.check_reply_as_list:
                return []
            return [
                {".section": "0", "status": "finding out latest version..."},
                {
                    ".section": "1",
                    "latest-version": self.latest,
                    "status": self.check_status or self._status(),
                },
            ]
        if path == "system/package/update/set":
            self.channel = str((body or {})["channel"])
            self.checked = False
            return None
        if path == "system/package/update/install":
            self._begin("routeros")
            if self.install_drops:
                self._phase, self._left = "down", self.down_polls
                raise RouterOSConnectionError("connection dropped")
            return self.install_reply
        if path == "system/routerboard/upgrade":
            return None
        if path == "system/reboot":
            self._begin("firmware")
            if self.reboot_drops:
                self._phase, self._left = "down", self.down_polls
                raise RouterOSConnectionError("connection dropped")
            return None
        raise RouterOSAPIError(f"unexpected POST {path}", 404)
