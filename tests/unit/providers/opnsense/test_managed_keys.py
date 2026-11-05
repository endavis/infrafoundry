"""Unit tests for the managed-key helpers (#1256, ADR-0018)."""

from __future__ import annotations

import logging

import pytest

from infrafoundry.core.exceptions import InvalidConfigurationError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.components._managed import managed_keys, subnet_cidr_keys
from infrafoundry.providers.opnsense.services.unbound_forward import (
    unbound_forward_configs_from_resources,
)


def _forward(name: str, **config: object) -> ResourceConfig:
    base = {"type": "dot", "domain": "x.lan", "server": "1.1.1.1", "port": 853}
    base.update(config)
    return ResourceConfig(name=name, type="unbound.forwards", provider="opnsense", config=base)


def test_none_means_no_managed_set() -> None:
    assert managed_keys(None, unbound_forward_configs_from_resources, type_name="t") is None


def test_empty_list_is_an_empty_set() -> None:
    assert managed_keys([], unbound_forward_configs_from_resources, type_name="t") == set()


def test_derives_one_key_per_row() -> None:
    rows = [_forward("a"), _forward("b", domain="y.lan")]
    keys = managed_keys(rows, unbound_forward_configs_from_resources, type_name="unbound.forwards")
    assert keys == {("dot", "x.lan", "1.1.1.1", "853"), ("dot", "y.lan", "1.1.1.1", "853")}


def test_bad_row_is_skipped_and_warning_omits_config(caplog: pytest.LogCaptureFixture) -> None:
    def parse(rows: list[ResourceConfig]) -> list[object]:
        if rows[0].config.get("secret_field") == "boom":
            raise InvalidConfigurationError("bad row")
        return unbound_forward_configs_from_resources(rows)  # type: ignore[return-value]

    rows = [_forward("good"), _forward("bad", secret_field="boom", password="hunter2")]
    with caplog.at_level(logging.WARNING):
        keys = managed_keys(rows, parse, type_name="unbound.forwards")

    assert keys == {("dot", "x.lan", "1.1.1.1", "853")}
    assert "bad" in caplog.text
    assert "unbound.forwards" in caplog.text
    assert "hunter2" not in caplog.text
    assert "boom" not in caplog.text


def test_value_error_is_also_skipped() -> None:
    def parse(rows: list[ResourceConfig]) -> list[object]:
        raise ValueError("nope")

    assert managed_keys([_forward("a")], parse, type_name="t") == set()


def test_config_without_diff_key_adds_nothing() -> None:
    assert managed_keys([_forward("a")], lambda rows: [object()], type_name="t") == set()


def test_subnet_cidr_keys() -> None:
    rows = [
        ResourceConfig(
            name="a",
            type="kea.dhcp4.subnets",
            provider="opnsense",
            config={"subnet": "172.21.0.0/24"},
        ),
        ResourceConfig(name="b", type="kea.dhcp4.subnets", provider="opnsense", config={}),
    ]
    assert subnet_cidr_keys(rows) == {"172.21.0.0/24"}
    assert subnet_cidr_keys(None) is None
    assert subnet_cidr_keys([]) == set()


def test_unparseable_rows_are_reported_as_unresolved() -> None:
    def parse(rows: list[ResourceConfig]) -> list[object]:
        if rows[0].name == "bad":
            raise ValueError("nope")
        return unbound_forward_configs_from_resources(rows)  # type: ignore[return-value]

    unresolved: set[str] = set()
    keys = managed_keys(
        [_forward("good"), _forward("bad")], parse, type_name="t", unresolved=unresolved
    )
    assert keys == {("dot", "x.lan", "1.1.1.1", "853")}
    assert unresolved == {"bad"}


def test_row_without_a_key_is_reported_as_unresolved() -> None:
    unresolved: set[str] = set()
    managed_keys([_forward("a")], lambda rows: [object()], type_name="t", unresolved=unresolved)
    assert unresolved == {"a"}


def test_subnet_rows_without_a_cidr_are_reported_as_unresolved() -> None:
    rows = [
        ResourceConfig(
            name="a",
            type="kea.dhcp4.subnets",
            provider="opnsense",
            config={"subnet": "172.21.0.0/24"},
        ),
        ResourceConfig(name="b", type="kea.dhcp4.subnets", provider="opnsense", config={}),
    ]
    unresolved: set[str] = set()
    assert subnet_cidr_keys(rows, unresolved) == {"172.21.0.0/24"}
    assert unresolved == {"b"}
