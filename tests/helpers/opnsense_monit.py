"""Fake monit box for the monit tests (#791). Fake data only: every UUID is synthetic."""

from __future__ import annotations

import re
from typing import Any

from infrafoundry.core.provider import ResourceConfig

SECRET = "s3cr3t-sentinel-not-real"  # nosec B105  # test fixture

_SECTIONS = {"Alert": "alert", "Service": "service", "Test": "test"}
#: Row fields the box returns as option dicts, so tests exercise ``flatten_option``.
_OPTION_FIELDS = ("type", "action", "events", "tests", "depends", "interface")
_GENERAL_OPTIONS = ("mailserver", "sslversion", "httpdAllow")
_ROUTE = re.compile(r"^monit/settings/(add|set|del)(Alert|Service|Test)(?:/([\w-]+))?$")


def stock_general() -> dict[str, str]:
    """Return the stock ``general`` section as flat strings (what the fake stores)."""
    return {
        "enabled": "0",
        "interval": "120",
        "startdelay": "120",
        "mailserver": "127.0.0.1",
        "port": "25",
        "username": "",
        "password": "",
        "ssl": "0",
        "sslversion": "auto",
        "sslverify": "1",
        "logfile": "",
        "statefile": "",
        "eventqueuePath": "",
        "eventqueueSlots": "",
        "httpdEnabled": "0",
        "httpdUsername": "root",
        "httpdPassword": "",
        "httpdPort": "2812",
        "httpdAllow": "",
        "mmonitUrl": "",
        "mmonitTimeout": "5",
        "mmonitRegisterCredentials": "1",
    }


def option_dict(selected: str, universe: tuple[str, ...] = ()) -> dict[str, dict[str, Any]]:
    """Render a comma-joined selection the way MVC does: ``{key: {value, selected}}``."""
    chosen = [part for part in selected.split(",") if part]
    keys = list(dict.fromkeys([*universe, *chosen]))
    options = {k: {"value": k, "selected": 1 if k in chosen else 0} for k in keys}
    if not chosen:
        options = {"": {"value": "None", "selected": 1}, **options}
    return options


class FakeMonitBox:
    """In-memory monit module behind ``request(method, path, data)``.

    Attributes:
        general: Flat ``general`` section.
        rows: ``section -> uuid -> flat row`` for ``alert``, ``service`` and ``test``.
        calls: Every ``(method, path, data)`` seen.
        reject_referenced_deletes: Answer ``failed`` to a delete of a referenced row.
    """

    def __init__(self) -> None:
        self.general: dict[str, str] = stock_general()
        self.rows: dict[str, dict[str, dict[str, str]]] = {
            "alert": {},
            "service": {},
            "test": {},
        }
        self.calls: list[tuple[str, str, Any]] = []
        self.reject_referenced_deletes = True
        self.omit_uuid_on_add = False
        self._counter = 0

    # -- helpers ---------------------------------------------------------------

    def new_uuid(self) -> str:
        """Return the next synthetic UUID."""
        self._counter += 1
        return f"00000000-0000-4000-8000-{self._counter:012d}"

    def seed(self, section: str, row: dict[str, str]) -> str:
        """Add a flat row directly and return its UUID."""
        uuid = self.new_uuid()
        self.rows[section][uuid] = dict(row)
        return uuid

    def uuid_of(self, section: str, name: str) -> str:
        """Return the UUID of the row with the given identity."""
        key = "recipient" if section == "alert" else "name"
        return next(u for u, r in self.rows[section].items() if r.get(key) == name)

    def names(self, section: str) -> list[str]:
        """Return the identities of a section's rows."""
        key = "recipient" if section == "alert" else "name"
        return [r.get(key, "") for r in self.rows[section].values()]

    def writes(self) -> list[tuple[str, str, Any]]:
        """Return the write calls (everything but the model read)."""
        return [c for c in self.calls if c[1] != "monit/settings/get"]

    def paths(self) -> list[str]:
        """Return the paths of the write calls, in order."""
        return [p for _, p, _ in self.writes()]

    def count(self, path: str) -> int:
        """Return how many times ``path`` was called."""
        return sum(1 for _, p, _ in self.calls if p == path)

    def _render_row(self, row: dict[str, str]) -> dict[str, Any]:
        return {k: option_dict(v) if k in _OPTION_FIELDS else v for k, v in row.items()}

    def _render(self) -> dict[str, Any]:
        general: dict[str, Any] = {
            k: option_dict(v) if k in _GENERAL_OPTIONS else v for k, v in self.general.items()
        }
        model: dict[str, Any] = {"general": general}
        for section, rows in self.rows.items():
            model[section] = {u: self._render_row(r) for u, r in rows.items()} or []
        return {"monit": model}

    def _referenced(self, section: str, uuid: str) -> bool:
        if section == "test":
            return any(uuid in r.get("tests", "").split(",") for r in self.rows["service"].values())
        if section == "service":
            return any(
                uuid in r.get("depends", "").split(",") for r in self.rows["service"].values()
            )
        return False

    # -- the API ---------------------------------------------------------------

    def request(self, method: str, path: str, data: Any = None, **_: Any) -> dict[str, Any]:
        """Answer one API call."""
        self.calls.append((method, path, data))
        if path == "monit/settings/get":
            return self._render()
        if path == "monit/settings/set":
            for wire, value in data["monit"]["general"].items():
                self.general[wire] = value
            return {"result": "saved"}
        if path == "monit/service/reconfigure":
            return {"status": "ok"}
        match = _ROUTE.match(path)
        if match is None:
            raise AssertionError(f"unexpected monit call {method} {path}")
        action, noun, uuid = match.groups()
        section = _SECTIONS[noun]
        if action == "add":
            new = self.new_uuid()
            self.rows[section][new] = {k: str(v) for k, v in data[section].items()}
            return (
                {"result": "saved"} if self.omit_uuid_on_add else {"result": "saved", "uuid": new}
            )
        if uuid is None or uuid not in self.rows[section]:
            return {"result": "failed", "validations": {"uuid": "not found"}}
        if action == "set":
            self.rows[section][uuid].update({k: str(v) for k, v in data[section].items()})
            return {"result": "saved"}
        if self.reject_referenced_deletes and self._referenced(section, uuid):
            return {"result": "failed", "validations": {"reference": "still referenced"}}
        del self.rows[section][uuid]
        return {"result": "deleted"}


def single(type_name: str, **config: Any) -> ResourceConfig:
    """Build a singleton resource (the loader does not inject ``name`` into those)."""
    return ResourceConfig(name=type_name, type=type_name, provider="opnsense", config=config)


def res(type_name: str, name: str, **config: Any) -> ResourceConfig:
    """Build a monit resource the way the loader does (it injects ``name``)."""
    config.setdefault("name", name)
    return ResourceConfig(name=name, type=type_name, provider="opnsense", config=config)


_STOCK_TESTS: tuple[tuple[str, str, str, str], ...] = (
    ("ping", "Ping", "NetworkPing", "failed ping"),
    ("network-link", "NetworkLink", "NetworkInterface", "failed link"),
    (
        "network-saturation",
        "NetworkSaturation",
        "NetworkInterface",
        "saturation is greater than 75%",
    ),
    ("memory-usage", "MemoryUsage", "SystemResource", "memory usage is greater than 75%"),
    ("cpu-usage", "CPUUsage", "SystemResource", "cpu usage is greater than 75%"),
    ("load-avg-1", "LoadAvg1", "SystemResource", "loadavg (1min) is greater than 4"),
    ("load-avg-5", "LoadAvg5", "SystemResource", "loadavg (5min) is greater than 3"),
    ("load-avg-15", "LoadAvg15", "SystemResource", "loadavg (15min) is greater than 2"),
    ("space-usage", "SpaceUsage", "SpaceUsage", "space usage is greater than 75%"),
    ("changed-status", "ChangedStatus", "ProgramStatus", "changed status"),
    ("non-zero-status", "NonZeroStatus", "ProgramStatus", "status != 0"),
)


def stock_resources() -> list[ResourceConfig]:
    """Return the stock-equivalent set: settings, 1 alert, 11 tests and 4 services."""
    resources = [single("monit.settings", enabled=False, interval=120)]
    resources.append(
        res(
            "monit.alerts",
            "alerts-example-com",
            recipient="alerts@example.com",
            enabled=False,
            noton=False,
        )
    )
    for handle, wire, kind, condition in _STOCK_TESTS:
        resources.append(
            res(
                "monit.tests",
                handle,
                test_name=wire,
                type=kind,
                condition=condition,
                action="alert",
            )
        )
    resources += [
        res(
            "monit.services",
            "host",
            service_name="$HOST",
            enabled=True,
            type="system",
            timeout=300,
            start_timeout=30,
            tests=["memory-usage", "cpu-usage", "load-avg-1", "load-avg-5", "load-avg-15"],
        ),
        res(
            "monit.services",
            "root-fs",
            service_name="RootFs",
            enabled=True,
            type="filesystem",
            path="/",
            tests=["space-usage"],
        ),
        res(
            "monit.services",
            "carp-status-change",
            service_name="carp_status_change",
            enabled=False,
            type="custom",
            path="/opt/example/carp_status.sh",
            tests=["changed-status"],
        ),
        res(
            "monit.services",
            "gateway-alert",
            service_name="gateway_alert",
            enabled=False,
            type="custom",
            path="/opt/example/gateway_alert.sh",
            tests=["non-zero-status"],
        ),
    ]
    return resources
