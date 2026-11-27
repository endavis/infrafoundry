"""Shared builders for the MikroTik provider tests (documentation values only)."""

from __future__ import annotations

import copy
import ipaddress
import json
from pathlib import Path
from typing import Any

import pytest

from infrafoundry.core.config.models import EnvironmentConfig
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.mikrotik.client import RouterOSAPIError, RouterOSConnectionError
from infrafoundry.providers.mikrotik.components.manager import MikroTikManager
from infrafoundry.providers.mikrotik.settings import MikroTikSettings

FIXTURES = Path(__file__).parent / "fixtures"
MGMT_IP = "192.0.2.2"
SETTINGS = MikroTikSettings(api_url=f"https://{MGMT_IP}", username="admin", password="pw-example")


class FakeRouterOS:
    """In-memory RouterOS: tables keyed by REST path, with a call log."""

    def __init__(self, tables: dict[str, list[dict[str, str]]]) -> None:
        self.tables = copy.deepcopy(tables)
        self.calls: list[tuple[Any, ...]] = []
        self.errors: dict[tuple[str, str], RouterOSAPIError | RouterOSConnectionError] = {}
        """Raise this error on ``(verb, path)`` (the path of a PATCH or DELETE has the id)."""
        self.put_returns_id = True
        self._next_id = 100

    @classmethod
    def from_fixture(cls, name: str) -> FakeRouterOS:
        return cls(json.loads((FIXTURES / f"{name}.json").read_text()))

    def get(self, path: str) -> list[dict[str, str]]:
        self.calls.append(("GET", path))
        return copy.deepcopy(self.tables.get(path, []))

    def _fail(self, verb: str, path: str) -> None:
        error = self.errors.get((verb, path))
        if error is not None:
            raise error

    def put(self, path: str, body: dict[str, str]) -> dict[str, str]:
        self.calls.append(("PUT", path, dict(body)))
        self._fail("PUT", path)
        row = {**body, ".id": f"*{self._next_id}", "disabled": "false", "dynamic": "false"}
        self._next_id += 1
        self.tables.setdefault(path, []).append(row)
        return dict(row) if self.put_returns_id else {}

    def post(self, path: str, body: dict[str, Any] | None = None) -> Any:
        body = dict(body or {})
        self.calls.append(("POST", path, body))
        self._fail("POST", path)
        if path == "certificate/sign":
            rows = [r for r in self.tables.get("certificate", []) if r.get(".id") == body["number"]]
            if not rows:
                raise RouterOSAPIError("no such item")
            rows[0]["fingerprint"] = "AA:" * 31 + "AA"
            rows[0]["private-key"] = "true"
        return None

    def _row(self, path: str, row_id: str) -> dict[str, str]:
        return next(r for r in self.tables.get(path, []) if r.get(".id") == row_id)

    def patch(self, path: str, row_id: str, body: dict[str, str]) -> dict[str, str]:
        self.calls.append(("PATCH", f"{path}/{row_id}", dict(body)))
        self._fail("PATCH", f"{path}/{row_id}")
        row = self._row(path, row_id)
        row.update(body)
        return dict(row)

    def delete(self, path: str, row_id: str) -> None:
        self.calls.append(("DELETE", f"{path}/{row_id}"))
        self._fail("DELETE", f"{path}/{row_id}")
        self.tables[path].remove(self._row(path, row_id))

    def writes(self) -> list[tuple[Any, ...]]:
        """The PUT, POST, PATCH and DELETE calls, in order."""
        return [c for c in self.calls if c[0] in ("PUT", "POST", "PATCH", "DELETE")]

    def execute(self, script: str) -> str:
        self.calls.append(("EXECUTE", script))
        return ""


def resource(type_name: str, name: str, **config: Any) -> ResourceConfig:
    """Build a MikroTik resource."""
    return ResourceConfig(name=name, type=type_name, provider="mikrotik", config=config)


def bootstrap_https(name: str = "bootstrap-https") -> list[ResourceConfig]:
    """A self-signed certificate plus ``www-ssl`` and ``api-ssl`` serving with it."""
    return [
        resource(
            "certificate",
            name,
            **{
                "common-name": "router.example.com",
                "key-usage": ["digital-signature", "key-encipherment", "tls-server"],
                "days-valid": 365,
            },
        ),
        resource("ip.service", "www-ssl", certificate=name, disabled=False),
        resource("ip.service", "api-ssl", certificate=name, disabled=False),
    ]


def with_https_services(fake: FakeRouterOS) -> FakeRouterOS:
    """Add the disabled ``api-ssl`` service and an empty certificate table to ``fake``."""
    services = fake.tables.setdefault("ip/service", [])
    if not any(r["name"] == "api-ssl" for r in services):
        services.append(
            {
                ".id": "*42",
                "name": "api-ssl",
                "port": "8729",
                "disabled": "true",
                "dynamic": "false",
            }
        )
    for row in services:
        if row["name"] == "www-ssl":
            row["disabled"] = "true"
    fake.tables.setdefault("certificate", [])
    return fake


def make_env(
    settings: dict[str, Any] | None = None, secrets: dict[str, Any] | None = None
) -> EnvironmentConfig:
    """Build an EnvironmentConfig with MikroTik provider settings."""
    return EnvironmentConfig(
        name="test",
        provider_settings={"mikrotik": settings} if settings is not None else {},
        secrets=secrets,
    )


def resolve_literal(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    """Resolve only IP literals; a hostname does not resolve."""
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        return None


@pytest.fixture
def wan_edge() -> FakeRouterOS:
    """A filtering edge switch reachable at the management address."""
    return FakeRouterOS.from_fixture("wan_edge")


@pytest.fixture
def factory() -> FakeRouterOS:
    """A device in its vendor-default configuration."""
    return FakeRouterOS.from_fixture("factory_default")


def manager_for(
    fake: FakeRouterOS, monkeypatch: pytest.MonkeyPatch, settings: MikroTikSettings = SETTINGS
) -> MikroTikManager:
    """A manager that reads ``fake`` and uses the documentation settings."""
    monkeypatch.setattr(
        "infrafoundry.providers.mikrotik.components.manager.load_settings",
        lambda config_dir, env_name: settings,
    )
    return MikroTikManager(Path("."), client_factory=lambda s: fake, host_resolver=resolve_literal)


def converged_wan_edge() -> list[ResourceConfig]:
    """Resources that describe the ``wan_edge`` fixture exactly."""
    port = "interface.bridge.port"
    vlan = "interface.bridge.vlan"
    return [
        resource("interface.bridge", "bridge", **{"vlan-filtering": True, "pvid": 1}),
        resource(port, "p1", interface="ether1", bridge="bridge", pvid=99),
        resource(port, "p2", interface="ether2", bridge="bridge", pvid=10),
        resource(port, "p3", interface="ether3", bridge="bridge", pvid=20),
        resource(port, "p4", interface="ether4", bridge="bridge", pvid=1),
        resource(
            vlan,
            "v10",
            bridge="bridge",
            **{"vlan-ids": 10, "tagged": ["bridge", "ether4"], "untagged": ["ether2"]},
        ),
        resource(
            vlan,
            "v20",
            bridge="bridge",
            **{"vlan-ids": 20, "tagged": ["bridge", "ether4"], "untagged": ["ether3"]},
        ),
        resource(
            vlan,
            "v99",
            bridge="bridge",
            **{"vlan-ids": 99, "tagged": ["bridge", "ether4"], "untagged": ["ether1"]},
        ),
        resource("interface.vlan", "vlan99", interface="bridge", **{"vlan-id": 99}),
        resource("ip.address", "mgmt", address="192.0.2.2/24", interface="vlan99"),
        resource("ip.service", "www-ssl", port=443, disabled=False),
    ]
