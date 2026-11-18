"""Tests for the management-path refusal."""

from typing import Any

import pytest

from infrafoundry.providers.openwrt.components.management import (
    interfaces_of,
    management_refusals,
    resolve_ipv4,
)
from infrafoundry.providers.openwrt.schema import Desired, desired_from_resources

from .conftest import lan

OLD = {"ipaddr": "192.0.2.1", "netmask": "255.255.255.0"}


def _item(**config: Any) -> Desired:
    return desired_from_resources([lan(**config)])[0]


def _literal(host: str) -> str | None:
    return host if host[0].isdigit() else None


def _check(address: str, before: Any, after: Any, **config: Any) -> tuple[list[str], str | None]:
    return management_refusals(address, [(_item(**config), before, after)], resolve=_literal)


def test_change_with_the_management_address_in_the_old_subnet_is_refused() -> None:
    new = {"ipaddr": "198.51.100.1", "netmask": "255.255.255.0"}
    refusals, reconnect = _check("192.0.2.2", OLD, new)
    assert len(refusals) == 1
    assert "confirm_management_change" in refusals[0]
    assert "192.0.2.2" in refusals[0]
    assert reconnect is None


def test_change_with_the_management_address_in_the_new_subnet_is_refused() -> None:
    new = {"ipaddr": "198.51.100.1", "netmask": "255.255.255.0"}
    refusals, _ = _check("198.51.100.77", OLD, new)
    assert len(refusals) == 1


def test_the_flag_allows_the_change() -> None:
    new = {"ipaddr": "192.0.2.9", "netmask": "255.255.255.0"}
    refusals, reconnect = _check("192.0.2.2", OLD, new, confirm_management_change=True)
    assert refusals == []
    assert reconnect is None


def test_the_flag_with_the_current_interface_address_reconnects_to_the_new_one() -> None:
    new = {"ipaddr": "198.51.100.1", "netmask": "255.255.255.0"}
    refusals, reconnect = _check("192.0.2.1", OLD, new, confirm_management_change=True)
    assert refusals == []
    assert reconnect == "198.51.100.1"


def test_a_change_outside_the_management_subnet_is_allowed() -> None:
    before = {"ipaddr": "203.0.113.1", "netmask": "255.255.255.0"}
    after = {"ipaddr": "203.0.113.5", "netmask": "255.255.255.0"}
    assert _check("192.0.2.2", before, after) == ([], None)


def test_a_new_interface_outside_the_management_subnet_is_allowed() -> None:
    after = {"ipaddr": "203.0.113.1", "netmask": "255.255.255.0"}
    assert _check("192.0.2.2", {}, after) == ([], None)


def test_an_unresolvable_settings_address_is_refused() -> None:
    new = {"ipaddr": "203.0.113.5", "netmask": "255.255.255.0"}
    refusals, _ = _check("router.example.com", {}, new)
    assert "cannot be resolved" in refusals[0]


def test_an_unreadable_change_is_refused() -> None:
    refusals, _ = _check("192.0.2.2", None, None)
    assert "cannot be read" in refusals[0]


def test_a_live_cidr_ipaddr_is_parsed() -> None:
    new = {"ipaddr": "203.0.113.5", "netmask": "255.255.255.0"}
    refusals, _ = _check("192.0.2.2", {"ipaddr": "192.0.2.1/24"}, new)
    assert len(refusals) == 1


def test_a_live_list_ipaddr_is_parsed() -> None:
    before = {"ipaddr": ["203.0.113.1/24", "192.0.2.1/24"]}
    new = {"ipaddr": "203.0.113.5", "netmask": "255.255.255.0"}
    refusals, _ = _check("192.0.2.2", before, new)
    assert len(refusals) == 1


def test_interfaces_of() -> None:
    assert interfaces_of({}) == []
    assert interfaces_of("junk") is None
    assert interfaces_of({"ipaddr": "not-an-ip"}) is None
    parsed = interfaces_of(OLD)
    assert parsed is not None and str(parsed[0].network) == "192.0.2.0/24"
    bare = interfaces_of({"ipaddr": "192.0.2.1"})
    assert bare is not None and str(bare[0].network) == "192.0.2.1/32"


@pytest.mark.parametrize(
    ("host", "expected"), [("192.0.2.2", "192.0.2.2"), ("nonexistent.invalid", None)]
)
def test_resolve_ipv4(host: str, expected: str | None) -> None:
    assert resolve_ipv4(host) == expected
