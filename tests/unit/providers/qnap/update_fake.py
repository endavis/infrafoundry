"""A scripted QNAP switch for the firmware upgrade tests (documentation values)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from infrafoundry.providers.qnap.client import (
    QnapApiError,
    QnapAuthError,
    QnapError,
    QnapUnreachableError,
)


class FakeClock:
    """Monotonic clock whose ``sleep`` advances it."""

    def __init__(self) -> None:
        self.now = 0.0

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


class FakeQnapSwitch:
    """Scripted client surface: ``get``, ``post``, ``about``, ``login``, ``renew``, ``live``.

    ``progress`` is the script of ``firmware/status`` replies after the install POST; the
    markers ``"DROP"`` (connection lost) and ``"401"`` (session refused) raise instead.
    Once a ``done`` or ``DROP`` is consumed the switch is going down: ``grace`` more
    ``live()`` polls answer True, then ``down_polls`` answer False, then it is back on
    ``version_after``.
    """

    def __init__(
        self,
        *,
        version: str = "2.5.0",
        offer: str | None = "2.6.0",
        product: str = "QSW-M",
        dns: bool = True,
        progress: list[str] | None = None,
        version_after: str | None = None,
        grace: int = 1,
        down_polls: int = 2,
    ) -> None:
        self.version = version
        self.offer = offer
        self.product = product
        self.dns = dns
        self.progress = list(progress if progress is not None else ["installing", "done"])
        self.version_after = version_after
        self.grace = grace
        self.down_polls = down_polls
        self.never_down = False
        self.stay_down = False
        self.anomaly = False
        self.failed_message = "image rejected"
        self.check_error: Exception | None = None
        self.install_error: Exception | None = None
        self.login_errors: list[Exception] = []
        self.requests: list[tuple[str, str]] = []
        self.check_timeouts: list[float | None] = []
        self.logins = 0
        self.sessions_open = 0
        self.sessions_closed = 0
        self._installing = False
        self._going_down = False
        self._left = 0
        self._phase = "up"
        self._phase_down_left = 0

    def paths(self) -> list[str]:
        return [path for _, path in self.requests]

    # -- client surface
    def about(self) -> dict[str, Any]:
        return {"Hostname": "sw-example", "Model": "QSW-M-example", "Product": self.product}

    def login(self) -> None:
        self.logins += 1
        if self.login_errors:
            raise self.login_errors.pop(0)

    def renew(self) -> None:
        self.requests.append(("RENEW", "users/login"))

    @contextmanager
    def session(self) -> Iterator[None]:
        self.login()
        self.sessions_open += 1
        try:
            yield
        finally:
            self.sessions_closed += 1

    def live(self) -> bool:
        if self.never_down:
            return True
        if not self._going_down:
            return self._phase == "up"
        if self._left > 0:
            self._left -= 1
            return True
        if self._phase_down_left > 0:
            self._phase_down_left -= 1
            return False
        if self.stay_down:
            return False
        self._going_down = False
        self.version = self.version_after or self.offer or self.version
        return True

    def _go_down(self, grace: int | None = None) -> None:
        self._going_down = True
        self._left = self.grace if grace is None else grace
        self._phase_down_left = self.down_polls

    def get(self, path: str, *, timeout: float | None = None) -> Any:
        self.requests.append(("GET", path))
        if path == "firmware/info":
            if self._going_down and not self.never_down:
                raise QnapUnreachableError("down")
            return {"version": self.version, "buildNumber": "1"}
        if path == "dns/server":
            return [{"key": "1", "val": {"IpAddress": "192.0.2.53" if self.dns else ""}}]
        if path == "firmware/condition":
            return {"anomaly": self.anomaly, "message": "flash busy" if self.anomaly else ""}
        if path == "firmware/update/check":
            self.check_timeouts.append(timeout)
            if self.check_error is not None:
                raise self.check_error
            if self.offer is None:
                return {"newer": False}
            return {"newer": True, "version": self.offer, "buildNumber": "2"}
        if path == "firmware/status":
            return self._status()
        raise QnapApiError(path, 404)

    def _status(self) -> Any:
        step = self.progress.pop(0) if len(self.progress) > 1 else self.progress[0]
        if step == "DROP":
            self._go_down(0)
            raise QnapUnreachableError("connection lost")
        if step == "401":
            raise QnapAuthError("refused")
        if step == "done":
            self._go_down()
        if step == "failed":
            return {"progress": "failed", "message": self.failed_message}
        return {"progress": step}

    def post(self, path: str, body: dict[str, Any] | None = None) -> Any:
        self.requests.append(("POST", path))
        if path == "firmware/update/live":
            if self.install_error is not None:
                raise self.install_error
            self._installing = True
            return {}
        raise QnapApiError(path, 404)


__all__ = ["FakeClock", "FakeQnapSwitch", "QnapError"]
