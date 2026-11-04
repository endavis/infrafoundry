"""Unit tests for the 26.1 ``SystemClient`` endpoints (#1149)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from infrafoundry.providers.opnsense.api_client import SystemClient


@pytest.fixture
def parts() -> tuple[SystemClient, MagicMock]:
    raw = MagicMock()
    raw.request.return_value = {}
    return SystemClient(raw), raw


@pytest.mark.parametrize(
    ("method", "args", "http", "path", "data"),
    [
        ("get_firmware_info", (), "GET", "core/firmware/info", None),
        ("get_firmware_settings", (), "GET", "core/firmware/get", None),
        (
            "set_firmware_settings",
            ({"firmware": {"a": "b"}},),
            "POST",
            "core/firmware/set",
            {"firmware": {"a": "b"}},
        ),
        ("install_plugin", ("os-a",), "POST", "core/firmware/install/os-a", None),
        ("remove_plugin", ("os-a",), "POST", "core/firmware/remove/os-a", None),
        ("lock_plugin", ("os-a",), "POST", "core/firmware/lock/os-a", None),
        ("get_tunables", (), "GET", "core/tunables/get", None),
        ("add_tunable", ({"sysctl": {}},), "POST", "core/tunables/addItem", {"sysctl": {}}),
        ("set_tunable", ("u1", {"sysctl": {}}), "POST", "core/tunables/setItem/u1", {"sysctl": {}}),
        ("del_tunable", ("u1",), "POST", "core/tunables/delItem/u1", None),
        ("reconfigure_tunables", (), "POST", "core/tunables/reconfigure", None),
    ],
)
def test_method_and_path(
    parts: tuple[SystemClient, MagicMock],
    method: str,
    args: tuple[Any, ...],
    http: str,
    path: str,
    data: Any,
) -> None:
    client, raw = parts
    getattr(client, method)(*args)
    if data is None:
        raw.request.assert_called_once_with(http, path)
    else:
        raw.request.assert_called_once_with(http, path, data=data)


@pytest.mark.parametrize("method", ["install_plugin", "remove_plugin", "lock_plugin"])
def test_plugin_name_is_percent_encoded(parts: tuple[SystemClient, MagicMock], method: str) -> None:
    client, raw = parts
    getattr(client, method)("../x/y")
    assert raw.request.call_args.args[1].endswith("/..%2Fx%2Fy")


def test_tunable_uuid_is_percent_encoded(parts: tuple[SystemClient, MagicMock]) -> None:
    client, raw = parts
    client.set_tunable("a/b", {})
    assert raw.request.call_args.args[1] == "core/tunables/setItem/a%2Fb"
