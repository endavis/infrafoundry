"""An in-memory QNAP switch for the VLAN and LACP tests (a helper, not a test module).

All values are documentation values: 8 physical ports, LAG interfaces from 9 (``lag1`` is
interface 9), VLANs 1, 10 and 20, management on VLAN 1. The write verbs follow the API's
semantics: a ``PUT`` replaces a complete member list, ``POST`` creates, ``DELETE`` removes.
Unlike the real switch (unknown), the fake refuses a port that would be untagged in two
VLANs, so the tests prove the order of the writes.

``GET ports`` returns a full row per physical port plus one ``ieee8023ad`` row per LACP
group, as a real switch does. ``PUT portlist`` takes the array the web UI sends and answers
400 for anything else; ``mtu_switch_wide`` makes an MTU write reach every port.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from infrafoundry.providers.qnap.client import QnapApiError, QnapError, QnapUnreachableError


class FakeClock:
    """Monotonic clock whose ``sleep`` advances it."""

    def __init__(self) -> None:
        self.now = 0.0

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def port_row(**overrides: Any) -> dict[str, Any]:
    """Return the ``val`` of a physical port: auto-negotiating at 1G, up, 1500 MTU."""
    row: dict[str, Any] = {
        "Alias": "",
        "AutoMode": True,
        "Combo": False,
        "FC": False,
        "FEC": "N/A",
        "Fdx": True,
        "FlowControlStatus": False,
        "MTU": 1500,
        "MediaType": "Copper",
        "Shutdown": False,
        "Speed": "oneGB",
        "Type": "ieee8023ad_none",
    }
    row.update(overrides)
    return row


def lag_row() -> dict[str, Any]:
    """Return the ``val`` of a LACP interface row, as ``GET ports`` shows it."""
    return port_row(AutoMode=False, Speed="", Type="ieee8023ad")


class FakeQnapConfig:
    """Scripted client surface for the config manager."""

    def __init__(
        self,
        *,
        ports: int = 8,
        start_index: int = 8,
        mgmt_key: str = "1",
        member_as_str: bool = True,
    ) -> None:
        self.port_count = ports
        self.start_index = start_index
        self.mgmt_key = mgmt_key
        self.member_as_str = member_as_str
        self.vlans: dict[int, dict[int, bool]] = {
            1: dict.fromkeys(range(1, ports + 1), False),
            10: {1: True, 2: True},
            20: {1: True},
        }
        self.lags: dict[int, dict[str, Any]] = {}
        self.calls: list[tuple[str, str, Any]] = []
        self.sessions = 0
        self.fail_write: dict[int, Exception] = {}
        """Write number (0-based) to the exception it raises."""
        self.ignore_writes: set[tuple[str, str]] = set()
        """``(method, path)`` pairs that answer success without changing anything."""
        self.live_answers: list[bool] = []
        """Scripted ``live()`` answers; empty means up."""
        self.live_always_down = False
        self.clock: FakeClock | None = None
        self.max_channels = 8
        self.max_ports = 8
        self.mtu_switch_wide = False
        self.port_rows: dict[int, dict[str, Any]] = {
            p: port_row(Alias=f"spare-{p}") for p in range(1, ports + 1)
        }
        self.timeouts: list[tuple[str, float | None]] = []
        """``(path, timeout)`` of every PUT, in order."""
        self._writes = 0

    # -- helpers for tests
    def add_lag(self, group: int, members: list[int], mode: str = "lacp") -> None:
        self.lags[group] = {"mode": mode, "members": list(members)}

    def writes(self) -> list[tuple[str, str, Any]]:
        return [c for c in self.calls if c[0] != "GET"]

    def port_writes(self) -> list[Any]:
        return [body for method, path, body in self.calls if path == "portlist" and method == "PUT"]

    def vlan_ids(self) -> list[int]:
        return sorted(self.vlans)

    # -- client surface
    @contextmanager
    def session(self) -> Iterator[None]:
        self.sessions += 1
        yield

    def live(self) -> bool:
        if self.live_always_down:
            return False
        if self.live_answers:
            return self.live_answers.pop(0)
        return True

    def get(self, path: str, *, timeout: float | None = None) -> Any:
        self.calls.append(("GET", path, None))
        if path == "vlan":
            return [
                {
                    "key": str(vid),
                    "val": [{"Port": str(p), "Tagged": t} for p, t in sorted(members.items())],
                }
                for vid, members in sorted(self.vlans.items())
            ]
        if path == "lacp/group":
            return [
                {
                    "key": str(g),
                    "val": {
                        "AggrMode": lag["mode"],
                        "PortMembers": [
                            str(m) if self.member_as_str else m for m in lag["members"]
                        ],
                    },
                }
                for g, lag in sorted(self.lags.items())
            ]
        if path == "lacp/info":
            return {
                "StartIndex": self.start_index,
                "MaxPortChannels": self.max_channels,
                "MaxPortsPerPortChannel": self.max_ports,
            }
        if path == "ports":
            rows = [{"key": str(p), "val": dict(v)} for p, v in sorted(self.port_rows.items())]
            rows += [
                {"key": str(self.start_index + g), "val": lag_row()} for g in sorted(self.lags)
            ]
            return rows
        if path == "ip/ipv4/interface":
            return [{"key": self.mgmt_key, "val": {"enableInterface": True}}]
        raise QnapApiError(path, 404)

    def _write(self, method: str, path: str, body: dict[str, Any] | list[Any]) -> None:
        self.calls.append((method, path, body))
        number = self._writes
        self._writes += 1
        if number in self.fail_write:
            raise self.fail_write[number]
        if (method, path) in self.ignore_writes:
            return
        if path == "portlist":
            self._write_ports(method, body)
        elif not isinstance(body, dict):
            raise QnapApiError(path, 400)
        elif path == "vlan":
            self._write_vlan(method, body)
        elif path == "lacp/group":
            self._write_lag(method, body)
        else:
            raise QnapApiError(path, 404)

    def _write_ports(self, method: str, body: dict[str, Any] | list[Any]) -> None:
        # The real switch takes an array at the top level and refuses an object with 400.
        if method != "PUT" or not isinstance(body, list):
            raise QnapApiError("portlist", 400)
        for entry in body:
            port = int(entry["idx"])
            if port not in self.port_rows:
                raise QnapApiError("portlist", 400)
            data = dict(entry["data"])
            if data["AutoMode"] != (data["Speed"] == "autoNegMode"):
                raise QnapApiError("portlist", 400)
            if data["AutoMode"]:
                data["Speed"] = self.port_rows[port]["Speed"]  # the negotiated speed stays
            self.port_rows[port] = data
            if self.mtu_switch_wide:
                for row in self.port_rows.values():
                    row["MTU"] = data["MTU"]

    def _write_vlan(self, method: str, body: dict[str, Any]) -> None:
        if method == "DELETE":
            # The real switch refuses a scalar ``idx`` with 400; it takes a list of keys.
            if not isinstance(body["idx"], list):
                raise QnapApiError("vlan", 400)
            for idx in body["idx"]:
                vid = int(idx)
                if vid == 1 or vid not in self.vlans:
                    raise QnapApiError("vlan", 400)
                del self.vlans[vid]
            return
        for entry in body["data"]:
            vid = int(entry["key"])
            if (method == "POST") == (vid in self.vlans):
                raise QnapApiError("vlan", 400)
            members = {int(m["Port"]): bool(m["Tagged"]) for m in entry["val"]}
            for port, tagged in members.items():
                if not tagged and any(
                    other != vid and others.get(port) is False
                    for other, others in self.vlans.items()
                ):
                    raise QnapApiError("vlan", 400)
            self.vlans[vid] = members

    def _write_lag(self, method: str, body: dict[str, Any]) -> None:
        if method == "DELETE":
            for idx in body["idx"]:
                if int(idx) not in self.lags:
                    raise QnapApiError("lacp/group", 400)
                del self.lags[int(idx)]
            return
        group = int(body["idx"])
        if (method == "POST") == (group in self.lags):
            raise QnapApiError("lacp/group", 400)
        data = body["data"]
        self.lags[group] = {
            "mode": data["AggrMode"],
            "members": [int(m) for m in data["PortMembers"]],
        }

    def post(self, path: str, body: dict[str, Any] | None = None) -> Any:
        self._write("POST", path, body or {})

    def put(
        self, path: str, body: dict[str, Any] | list[Any], *, timeout: float | None = None
    ) -> Any:
        self.timeouts.append((path, timeout))
        self._write("PUT", path, body)

    def delete(self, path: str, body: dict[str, Any]) -> Any:
        self._write("DELETE", path, body)


__all__ = ["FakeClock", "FakeQnapConfig", "QnapError", "QnapUnreachableError"]
