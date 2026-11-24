"""Shared builders for the OpenWrt provider tests (documentation values only)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from infrafoundry.core.config.models import EnvironmentConfig
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.openwrt.settings import OpenWrtSettings

FIXTURES = Path(__file__).parent / "fixtures"
MGMT_IP = "192.0.2.2"
SETTINGS = OpenWrtSettings(address=MGMT_IP)


def fixture_text(name: str) -> str:
    """Return a recorded-style ``ansible.posix.json`` document."""
    return (FIXTURES / f"{name}.json").read_text()


def doc(*tasks: dict[str, Any]) -> str:
    """Build a JSON callback document from ``(task name, host result)`` pairs."""
    return json.dumps(
        {"plays": [{"play": {"name": "x"}, "tasks": list(tasks)}], "stats": {}},
    )


def task(name: str, **result: Any) -> dict[str, Any]:
    """Build one task entry of the JSON callback document."""
    return {"task": {"name": name}, "hosts": {"openwrt": result}}


def res(type_name: str, name: str, **config: Any) -> ResourceConfig:
    """Build a resource the way the loaders do (the name is copied into the config)."""
    return ResourceConfig(
        name=name, type=type_name, provider="openwrt", config={"name": name, **config}
    )


def lan(**config: Any) -> ResourceConfig:
    """The router's LAN interface."""
    values: dict[str, Any] = {"ipaddr": "192.0.2.1", "netmask": "255.255.255.0"}
    return res("network.interface", "lan", **{**values, **config})


def printer(**config: Any) -> ResourceConfig:
    """A static lease."""
    values: dict[str, Any] = {"mac": "02:00:00:00:00:0a", "ip": "192.0.2.50"}
    return res("dhcp.host", "printer", **{**values, **config})


def web(**config: Any) -> ResourceConfig:
    """A port forward."""
    values: dict[str, Any] = {"src_dport": 8080, "dest_ip": "192.0.2.50", "dest_port": 80}
    return res("firewall.redirect", "web", **{**values, **config})


def make_env(settings: dict[str, Any] | None = None) -> EnvironmentConfig:
    """Build an EnvironmentConfig with OpenWrt provider settings."""
    return EnvironmentConfig(
        name="test",
        provider_settings={"openwrt": settings} if settings is not None else {},
    )


from .glinet_fake import served_glinet as served_glinet  # noqa: E402  # re-exported fixture
