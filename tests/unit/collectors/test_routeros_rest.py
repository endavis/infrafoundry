"""Tests for the RouterOS collector."""

from __future__ import annotations

import pytest

from infrafoundry.collectors.base import CollectorError
from infrafoundry.collectors.routeros_rest import RouterOSRestCollector, normalize_export
from infrafoundry.core.config.models import CollectorDeviceConfig
from infrafoundry.providers.mikrotik.client import RouterOSConnectionError

from .conftest import MakeDevice, fixture


class _Client:
    def __init__(self, output: str = "", error: Exception | None = None) -> None:
        self.output, self.error = output, error
        self.scripts: list[str] = []

    def execute(self, script: str) -> str:
        self.scripts.append(script)
        if self.error:
            raise self.error
        return self.output


def _device(make_device: MakeDevice) -> CollectorDeviceConfig:
    return make_device(name="switch-core", type="routeros-rest", address="http://192.0.2.2")


def test_executes_terse_export_and_strips_header(make_device: MakeDevice) -> None:
    client = _Client(fixture("routeros_export.rsc").decode())
    arts = RouterOSRestCollector(_device(make_device), lambda _s: client).collect()
    assert client.scripts == ["/export terse"]
    text = arts[0].content.decode()
    assert "by RouterOS" not in text
    assert "# model = CRS-example" in text
    assert arts[0].name == "export.rsc" and arts[0].secret_bearing


def test_header_only_difference_normalises_equal() -> None:
    a = "# 2000-01-01 00:00:00 by RouterOS 7.0\n/ip address add\n"
    b = "# 2001-02-02 10:00:00 by RouterOS 7.0\n/ip address add\n"
    assert normalize_export(a) == normalize_export(b)


def test_client_error_wrapped(make_device: MakeDevice) -> None:
    client = _Client(error=RouterOSConnectionError("unreachable"))
    with pytest.raises(CollectorError, match="unreachable"):
        RouterOSRestCollector(_device(make_device), lambda _s: client).collect()


def test_settings_error_wrapped(make_device: MakeDevice) -> None:
    dev = make_device(type="routeros-rest", address="no-scheme")
    with pytest.raises(CollectorError):
        RouterOSRestCollector(dev, lambda _s: _Client()).collect()
