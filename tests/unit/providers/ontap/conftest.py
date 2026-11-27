"""Shared builders and the in-memory ONTAP fake for the ONTAP provider tests.

Documentation values only: ``cluster1``, ``svm1``, ``cluster1-01``, ``e0d``, 192.0.2.x.
"""

from __future__ import annotations

import copy
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from infrafoundry.core.config.models import EnvironmentConfig
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers._netapp.ontap import OntapAPIError
from infrafoundry.providers.ontap.components.manager import OntapManager
from infrafoundry.providers.ontap.settings import OntapSettings

HOST_IP = "192.0.2.1"

SETTINGS = OntapSettings(
    host="cluster1.example.com",
    username="admin-example",
    password="pw-example",
    fingerprint="a" * 64,
    api_spec_dir=Path("/spec-example"),
)

RAW_SETTINGS: dict[str, Any] = {
    "host": "cluster1.example.com",
    "username": "secret://env_secrets/ontap/username",
    "password": "secret://env_secrets/ontap/password",
    "tls_fingerprint": "AB:" * 31 + "AB",
}


def record(
    name: str = "lif1",
    *,
    svm: str = "svm1",
    address: str = "192.0.2.10",
    netmask: str = "24",
    node: str = "cluster1-01",
    port: str = "e0d",
    policy: str = "default-data-files",
    auto_revert: bool = False,
    scope: str = "svm",
    is_home: bool = True,
    uuid: str | None = None,
) -> dict[str, Any]:
    """Build a nested ``network/ip/interfaces`` REST record."""
    return {
        "uuid": uuid or f"uuid-{svm}-{name}",
        "name": name,
        "scope": scope,
        "svm": {"name": svm},
        "ip": {"address": address, "netmask": netmask},
        "location": {
            "home_node": {"name": node},
            "home_port": {"name": port, "node": {"name": node}},
            "auto_revert": auto_revert,
            "is_home": is_home,
        },
        "service_policy": {"name": policy},
    }


def lif(resource_name: str = "lif1", /, **config: Any) -> ResourceConfig:
    """Build a ``network.ip.interface`` resource; defaults match ``record()``."""
    values: dict[str, Any] = {
        "svm": "svm1",
        "address": "192.0.2.10",
        "netmask": 24,
        "home_node": "cluster1-01",
        "home_port": "e0d",
        "service_policy": "default-data-files",
    }
    values.update(config)
    return ResourceConfig(
        name=resource_name,
        type="network.ip.interface",
        provider="ontap",
        config={k: v for k, v in values.items() if v is not None},
    )


def make_env(
    settings: dict[str, Any] | None = None, secrets: dict[str, Any] | None = None
) -> EnvironmentConfig:
    """Build an EnvironmentConfig with ONTAP provider settings."""
    return EnvironmentConfig(
        name="test",
        provider_settings={"ontap": settings} if settings is not None else {},
        secrets=secrets or {},
    )


def _set(body: dict[str, Any], dotted: str, value: Any) -> None:
    *parents, leaf = dotted.split(".")
    for step in parents:
        body = body.setdefault(step, {})
    body[leaf] = value


class FakeOntapService:
    """A stateful stand-in for the cluster: writes change what the next read returns."""

    def __init__(
        self,
        rows: list[dict[str, Any]] | None = None,
        *,
        fail_on: Callable[[str, dict[str, Any]], bool] | None = None,
    ) -> None:
        self.rows: list[dict[str, Any]] = list(rows or [])
        self.calls: list[tuple[str, str | None, dict[str, Any]]] = []
        self.reads: list[list[str]] = []
        self.fail_on = fail_on
        self.version = "NetApp Release 9.18.1"
        self.names: dict[str, set[str]] = {
            "svms": {"svm1"},
            "nodes": {"cluster1-01"},
            "ports": {"cluster1-01:e0d"},
        }

    def _maybe_fail(self, kind: str, fields: dict[str, Any]) -> None:
        if self.fail_on is not None and self.fail_on(kind, fields):
            raise OntapAPIError("ONTAP rejected the request: boom (code 1)")

    def list_interfaces(self, svms: Sequence[str]) -> list[dict[str, Any]]:
        self.reads.append(list(svms))
        return [copy.deepcopy(r) for r in self.rows if r["svm"]["name"] in svms]

    def create_interface(self, **fields: Any) -> None:
        self._maybe_fail("create", fields)
        self.calls.append(("create", None, dict(fields)))
        new: dict[str, Any] = {"scope": "svm", "location": {"is_home": True}}
        for dotted, value in fields.items():
            _set(new, dotted, value)
        new["uuid"] = f"uuid-{new['svm']['name']}-{new['name']}"
        self.rows.append(new)

    def update_interface(self, uuid: str, **fields: Any) -> None:
        self._maybe_fail("update", fields)
        self.calls.append(("update", uuid, dict(fields)))
        row = next(r for r in self.rows if r["uuid"] == uuid)
        for dotted, value in fields.items():
            _set(row, dotted, value)

    def delete_interface(self, uuid: str) -> None:
        self._maybe_fail("delete", {})
        self.calls.append(("delete", uuid, {}))
        self.rows = [r for r in self.rows if r["uuid"] != uuid]

    def cluster_info(self) -> dict[str, Any]:
        return {"name": "cluster1", "version": {"full": self.version}}

    def list_names(self, kind: str) -> set[str]:
        return set(self.names[kind])

    @property
    def writes(self) -> list[str]:
        return [c[0] for c in self.calls]


def manager_for(
    fake: FakeOntapService, tmp_path: Path, host_ip: str | None = HOST_IP
) -> OntapManager:
    """Build a manager that talks to the fake and resolves the host to ``host_ip``."""
    return OntapManager(tmp_path, lambda _settings: fake, lambda _host: host_ip)


@pytest.fixture(autouse=True)
def _settings_loader() -> Iterator[None]:
    """Serve ``SETTINGS`` to every manager instead of reading a config repository."""
    with patch("infrafoundry.providers.ontap.components.manager.load_settings") as loader:
        loader.return_value = SETTINGS
        yield


@pytest.fixture
def fake() -> FakeOntapService:
    """A cluster that holds one converged LIF."""
    return FakeOntapService([record()])
