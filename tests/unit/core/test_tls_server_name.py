"""The fixed-server-name adapter shared by the API certificate installers."""

from __future__ import annotations

import pytest
import requests

from infrafoundry.core.tls_server_name import ServerNameAdapter

pytestmark = pytest.mark.unit


def test_the_adapter_pins_sni_and_the_host_name_check() -> None:
    adapter = ServerNameAdapter("device.example.com")
    kwargs = adapter.poolmanager.connection_pool_kw
    assert kwargs["server_hostname"] == "device.example.com"
    assert kwargs["assert_hostname"] == "device.example.com"


def test_the_longest_mount_prefix_selects_the_adapter() -> None:
    session = requests.Session()
    session.mount("https://192.0.2.1", ServerNameAdapter("device.example.com"))
    adapter = session.get_adapter("https://192.0.2.1/api/cluster")
    assert isinstance(adapter, ServerNameAdapter)
    assert not isinstance(session.get_adapter("https://192.0.2.9/api"), ServerNameAdapter)
