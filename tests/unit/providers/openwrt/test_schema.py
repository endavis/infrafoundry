"""Tests for the OpenWrt resource schema and value normalization."""

from typing import Any

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.openwrt.schema import (
    KIND_BOOL,
    KIND_INT,
    KIND_PORTS,
    KIND_PROTO,
    SPECS,
    check_resources,
    covers_port,
    desired_from_resources,
    mac_variants,
    normalize_uci_value,
)

from .conftest import SETTINGS, lan, printer, res, web


def _messages(*resources: Any, settings: Any = None) -> list[str]:
    return [f.message for f in check_resources(list(resources), settings)]


def test_valid_resources_have_no_findings() -> None:
    pool = res("dhcp.pool", "lan", start=100, limit=150, leasetime="12h")
    assert _messages(lan(), pool, printer(), web()) == []


def test_other_providers_types_are_skipped() -> None:
    other = res("vm", "x", whatever=1)
    assert _messages(other) == []


@pytest.mark.parametrize(
    ("kind", "value", "expected"),
    [
        (KIND_INT, 100, "100"),
        (KIND_BOOL, True, "1"),
        (KIND_BOOL, False, "0"),
        (KIND_PROTO, ["tcp", "udp"], "tcp udp"),
        (KIND_PROTO, "tcp udp", "tcp udp"),
        (KIND_PORTS, 8080, "8080"),
    ],
)
def test_values_render_as_uci_stores_them(kind: str, value: Any, expected: str) -> None:
    assert normalize_uci_value(kind, value) == expected


def test_desired_values_are_uci_strings_with_defaults() -> None:
    item = desired_from_resources([web(enabled=False)])[0]
    assert item.key == "web"
    assert item.values == {
        "src": "wan",
        "dest": "lan",
        "proto": "tcp udp",
        "target": "DNAT",
        "name": "web",
        "src_dport": "8080",
        "dest_ip": "192.0.2.50",
        "dest_port": "80",
        "enabled": "0",
    }
    assert item.address == "openwrt_firewall_redirect.web"


def test_lease_hostname_maps_to_uci_name_and_resource_name_is_not_a_hostname() -> None:
    item = desired_from_resources([printer(hostname="printer-1", leasetime="12h")])[0]
    assert item.values == {
        "mac": "02:00:00:00:00:0a",
        "ip": "192.0.2.50",
        "name": "printer-1",
        "leasetime": "12h",
    }
    plain = desired_from_resources([printer()])[0]
    assert "name" not in plain.values


def test_interface_key_defaults_to_resource_name_and_is_not_a_value() -> None:
    item = desired_from_resources([lan()])[0]
    assert item.key == "lan"
    assert item.values == {"ipaddr": "192.0.2.1", "netmask": "255.255.255.0"}


def test_pool_key_defaults_to_resource_name() -> None:
    item = desired_from_resources([res("dhcp.pool", "lan", start=100)])[0]
    assert (item.key, item.values) == ("lan", {"interface": "lan", "start": "100"})


def test_absent_lease_carries_only_the_key() -> None:
    item = desired_from_resources([printer(absent=True)])[0]
    assert item.absent
    assert item.values == {}


@pytest.mark.parametrize(
    ("resource", "text"),
    [
        (lan(ipaddr="192.0.2.1/24"), "separate 'netmask'"),
        (lan(netmask="255.0.255.0"), "netmask"),
        (lan(netmask="24"), "dotted netmask"),
        (lan(ipaddr="not-an-ip"), "IPv4"),
        (printer(mac="02:00:00:00:00"), "02:00:00:00:00:01"),
        (res("dhcp.pool", "lan", start="100"), "non-negative integer"),
        (res("dhcp.pool", "lan", leasetime="soon"), "leasetime"),
        (printer(leasetime="12 hours"), "leasetime"),
        (web(src_dport="abc"), "port"),
        (web(src_dport="9000-8000"), "ascending"),
        (web(dest_port=70000), "1-65535"),
        (web(target="ACCEPT"), "DNAT or SNAT"),
        (web(enabled="yes"), "true or false"),
        (lan(bogus=1), "unknown field"),
        (res("network.interface", "lan", ipaddr="192.0.2.1"), "netmask"),
        (res("dhcp.host", "x", mac="02:00:00:00:00:01"), "ip"),
        (lan(absent=True), "'absent' is not allowed"),
        (res("dhcp.pool", "lan", absent=True), "'absent' is not allowed"),
        (lan(confirm_management_change="yes"), "true or false"),
        (res("network.interface", "bad name"), "resource name"),
        (lan(interface="lan-1"), "letters, digits and '_'"),
        (printer(hostname="x\n- injected"), "control characters"),
        (printer(hostname="{{ lookup('pipe','id') }}"), "Jinja markers"),
        (printer(hostname="{% if x %}"), "Jinja markers"),
    ],
)
def test_invalid_resources_are_rejected(resource: Any, text: str) -> None:
    messages = _messages(resource)
    assert messages, "expected a finding"
    assert any(text in m for m in messages), messages


def test_findings_name_the_resource() -> None:
    findings = check_resources([lan(bogus=1)])
    assert findings[0].resource == "lan"
    assert "network.interface 'lan'" in findings[0].message


def test_duplicate_mac_in_yaml_is_rejected_ignoring_case() -> None:
    other = res("dhcp.host", "other", mac="02:00:00:00:00:0A", ip="192.0.2.51")
    assert any("duplicate mac" in m for m in _messages(printer(), other))


def test_duplicate_redirect_name_in_yaml_is_rejected() -> None:
    twin = ResourceConfig(
        name="web2",
        type="firewall.redirect",
        provider="openwrt",
        config={"name": "web", "src_dport": 9000, "dest_ip": "192.0.2.51"},
    )
    assert any("duplicate name 'web'" in m for m in _messages(web(), twin))


def test_absent_lease_needs_only_the_mac() -> None:
    absent = res("dhcp.host", "gone", mac="02:00:00:00:00:02", absent=True)
    assert _messages(absent) == []


def test_redirect_covering_ssh_port_on_wan_needs_the_flag() -> None:
    risky = web(src_dport=22)
    assert any("SSH port 22" in m for m in _messages(risky, settings=SETTINGS))
    assert _messages(web(src_dport=22, confirm_management_change=True), settings=SETTINGS) == []


def test_redirect_range_covering_ssh_port_is_caught_and_lan_side_is_not() -> None:
    assert any("SSH port" in m for m in _messages(web(src_dport="20-30"), settings=SETTINGS))
    assert _messages(web(src_dport=22, src="lan"), settings=SETTINGS) == []
    assert _messages(web(src_dport=2222), settings=SETTINGS) == []


def test_covers_port() -> None:
    assert covers_port("20-30", 22)
    assert covers_port("22 80", 80)
    assert covers_port(22, 22)
    assert not covers_port("23-30", 22)
    assert not covers_port("junk", 22)


def test_mac_variants() -> None:
    assert mac_variants("02:00:00:00:00:0a") == ("02:00:00:00:00:0A", "02:00:00:00:00:0a")


def test_specs_cover_the_four_types_and_only_two_are_deletable() -> None:
    assert list(SPECS) == ["network.interface", "dhcp.pool", "dhcp.host", "firewall.redirect"]
    assert {n for n, s in SPECS.items() if s.deletable} == {"dhcp.host", "firewall.redirect"}
