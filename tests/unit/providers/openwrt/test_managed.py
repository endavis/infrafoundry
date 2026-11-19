"""Tests for the managed-set handling (ADR-0018)."""

import logging

import pytest

from infrafoundry.core.managed_set import ReleasedResource
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.openwrt.components._managed import managed_index
from infrafoundry.providers.openwrt.schema import Desired, desired_from_resources

from .conftest import lan, printer, res, web


def _declared(*resources: ResourceConfig) -> list[Desired]:
    return desired_from_resources(list(resources))


def test_no_managed_set_means_nothing_is_removed() -> None:
    index = managed_index(None, _declared(lan()))
    assert (index.names, index.removals, index.forgotten) == (set(), [], [])


def test_declared_rows_are_neither_removed_nor_forgotten() -> None:
    managed = {"dhcp.host": [printer()], "network.interface": [lan()]}
    index = managed_index(managed, _declared(printer(), lan()))
    assert index.names == {("dhcp.host", "printer"), ("network.interface", "lan")}
    assert index.removals == []
    assert index.forgotten == []


def test_undeclared_deletable_rows_become_absent_objects() -> None:
    managed = {"dhcp.host": [printer()], "firewall.redirect": [web()]}
    index = managed_index(managed, _declared(lan()))
    assert [(r.type_name, r.name, r.key, r.absent) for r in index.removals] == [
        ("dhcp.host", "printer", "02:00:00:00:00:0a", True),
        ("firewall.redirect", "web", "web", True),
    ]


def test_undeclared_interfaces_and_pools_are_only_forgotten() -> None:
    pool = res("dhcp.pool", "lan", start=100)
    managed = {"network.interface": [lan()], "dhcp.pool": [pool]}
    index = managed_index(managed, _declared(printer()))
    assert index.removals == []
    assert index.forgotten == [
        ReleasedResource(resource_type="network.interface", name="lan"),
        ReleasedResource(resource_type="dhcp.pool", name="lan"),
    ]


def test_a_renamed_resource_with_the_same_key_is_not_removed() -> None:
    renamed = res("dhcp.host", "label", mac="02:00:00:00:00:0a", ip="192.0.2.50")
    index = managed_index({"dhcp.host": [printer()]}, _declared(renamed))
    assert index.removals == []


def test_an_unparsable_row_is_skipped_and_never_released(
    caplog: pytest.LogCaptureFixture,
) -> None:
    broken = ResourceConfig(
        name="bad", type="dhcp.host", provider="openwrt", config={"mac": "not-a-mac", "ip": "x"}
    )
    with caplog.at_level(logging.WARNING):
        index = managed_index({"dhcp.host": [broken, printer()]}, _declared())
    assert [r.name for r in index.removals] == ["printer"]
    assert ("dhcp.host", "bad") not in index.names
    assert "bad" in caplog.text
    assert "not-a-mac" not in caplog.text


def test_unknown_types_are_ignored() -> None:
    other = ResourceConfig(name="x", type="vm", provider="openwrt", config={})
    assert managed_index({"vm": [other]}, _declared()).names == set()
