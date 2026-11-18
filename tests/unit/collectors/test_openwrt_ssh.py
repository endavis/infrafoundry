"""Tests for the OpenWrt collector."""

from __future__ import annotations

from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import pytest

from infrafoundry.collectors.base import CollectorError
from infrafoundry.collectors.openwrt_ssh import (
    OpenWrtSshCollector,
    normalize_ip_addr,
    redact_uci,
    ssh_argv,
)
from infrafoundry.core.config.models import CollectorDeviceConfig

from .conftest import MakeDevice, fixture

OUTPUTS = {
    "uci export network": "openwrt_uci_network.txt",
    "uci export dhcp": "openwrt_uci_dhcp.txt",
    "uci export firewall": "openwrt_uci_firewall.txt",
    "uci export wireless": "openwrt_uci_wireless.txt",
    "ip addr": "openwrt_ip_addr.txt",
    "ip route": "openwrt_ip_route.txt",
}


def _run(
    fail: dict[str, int] | None = None,
) -> tuple[Callable[..., Any], list[list[str]]]:
    fail = fail or {}
    seen: list[list[str]] = []

    def run(argv: list[str], **_kw: Any) -> SimpleNamespace:
        seen.append(argv)
        cmd = argv[-1]
        if cmd in fail:
            return SimpleNamespace(returncode=fail[cmd], stdout=b"", stderr=b"CANARY-STDERR")
        if cmd in OUTPUTS:
            return SimpleNamespace(returncode=0, stdout=fixture(OUTPUTS[cmd]), stderr=b"")
        out = fixture("openwrt_release.txt") + fixture("openwrt_board.json")
        return SimpleNamespace(returncode=0, stdout=out, stderr=b"")

    return run, seen


def _device(make_device: MakeDevice, **kw: Any) -> CollectorDeviceConfig:
    kw.setdefault("address", "192.0.2.1")
    return make_device(
        name="travel-router",
        type="openwrt-ssh",
        username="root",
        port=2222,
        ssh_key_file="/keys/id",
        **kw,
    )


def test_argv(make_device: MakeDevice) -> None:
    argv = ssh_argv(_device(make_device), "ip addr")
    assert "BatchMode=yes" in argv
    assert argv[argv.index("-p") + 1] == "2222"
    assert argv[argv.index("-i") + 1] == "/keys/id"
    assert argv[argv.index("-l") + 1] == "root"
    assert argv[-3:] == ["--", "192.0.2.1", "ip addr"]
    assert not any("StrictHostKeyChecking" in a for a in argv)


def test_collect_artifacts(make_device: MakeDevice) -> None:
    run, seen = _run()
    arts = {a.name: a for a in OpenWrtSshCollector(_device(make_device), run).collect()}
    assert set(arts) == {
        "uci-network.conf", "uci-dhcp.conf", "uci-firewall.conf", "uci-wireless.conf",
        "ip-addr.txt", "ip-route.txt", "system.txt",
    }  # fmt: skip
    assert all(arts[n].secret_bearing for n in arts if n.startswith("uci-"))
    assert not any(arts[n].secret_bearing for n in ("ip-addr.txt", "ip-route.txt", "system.txt"))
    assert len(seen) == 7
    for a in arts.values():
        assert b"CANARY" not in a.content


def test_redact_keeps_non_secret() -> None:
    out = redact_uci(fixture("openwrt_uci_wireless.txt").decode())
    assert "option key '<redacted>'" in out
    assert "option sae_password '<redacted>'" in out
    assert "option ssid 'travel-router-lab'" in out and "psk2" in out
    assert "private_key '<redacted>'" in redact_uci(fixture("openwrt_uci_network.txt").decode())


def test_ip_addr_lft_dropped() -> None:
    out = normalize_ip_addr(fixture("openwrt_ip_addr.txt").decode())
    assert "valid_lft" not in out and "inet 192.0.2.1/24" in out


def test_missing_wireless_tolerated(make_device: MakeDevice) -> None:
    run, _ = _run({"uci export wireless": 1})
    names = [a.name for a in OpenWrtSshCollector(_device(make_device), run).collect()]
    assert "uci-wireless.conf" not in names and "uci-network.conf" in names


def test_other_failure_raises_without_stderr(make_device: MakeDevice) -> None:
    run, _ = _run({"ip route": 255})
    with pytest.raises(CollectorError, match="ip route") as info:
        OpenWrtSshCollector(_device(make_device), run).collect()
    assert "CANARY" not in str(info.value) and "255" in str(info.value)
