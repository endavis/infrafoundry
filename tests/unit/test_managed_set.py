"""Unit tests for the managed-set helpers (#1256, ADR-0018)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

from infrafoundry.core.managed_set import build_managed_resources


def _row(resource_type: str, name: str, config: Any) -> SimpleNamespace:
    return SimpleNamespace(resource_type=resource_type, name=name, config=config)


def test_groups_rows_by_type_and_rebuilds_resource_config() -> None:
    rows = [
        _row("unbound.forwards", "f1", {"server": "1.1.1.1"}),
        _row("unbound.forwards", "f2", {"server": "9.9.9.9"}),
        _row("firewall.aliases", "a1", {"name": "a1"}),
    ]

    managed = build_managed_resources(rows, "opnsense")

    assert sorted(managed) == ["firewall.aliases", "unbound.forwards"]
    assert [r.name for r in managed["unbound.forwards"]] == ["f1", "f2"]
    first = managed["unbound.forwards"][0]
    assert (first.type, first.provider, first.config) == (
        "unbound.forwards",
        "opnsense",
        {"server": "1.1.1.1"},
    )


def test_skips_rows_whose_config_is_not_a_dict() -> None:
    rows = [_row("t", "none", None), _row("t", "str", "x"), _row("t", "ok", {"a": 1})]
    managed = build_managed_resources(rows, "opnsense")
    assert [r.name for r in managed["t"]] == ["ok"]


def test_non_list_input_yields_empty_mapping() -> None:
    assert build_managed_resources(MagicMock(), "opnsense") == {}
    assert build_managed_resources(None, "opnsense") == {}


def test_does_not_alias_the_row_config() -> None:
    config = {"a": 1}
    managed = build_managed_resources([_row("t", "n", config)], "opnsense")
    managed["t"][0].config["a"] = 2
    assert config == {"a": 1}
