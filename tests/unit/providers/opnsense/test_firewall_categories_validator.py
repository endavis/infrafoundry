"""Unit tests for ``FirewallCategoryValidator`` (#1286)."""

from __future__ import annotations

from typing import Any

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationReport
from infrafoundry.providers.opnsense.validators import build_xref_index
from infrafoundry.providers.opnsense.validators.context import OPNsenseValidationContext
from infrafoundry.providers.opnsense.validators.firewall_categories_validator import (
    FirewallCategoryValidator,
)


def _cat(name: str = "lab-servers", /, **config: Any) -> ResourceConfig:
    return ResourceConfig(name=name, type="firewall.categories", provider="opnsense", config=config)


def _run(resources: list[ResourceConfig]) -> ValidationReport:
    report = ValidationReport()
    FirewallCategoryValidator(report).validate(
        OPNsenseValidationContext(resources=resources, index=build_xref_index(resources))
    )
    return report


def _failed(report: ValidationReport) -> list[Any]:
    return [c for c in report.results if not c.passed]


def test_clean_entry_passes() -> None:
    assert _failed(_run([_cat(auto=True, color="#336699", lock=False)])) == []
    assert _failed(_run([_cat(color="336699"), _cat("b", color="")])) == []


def test_no_resources_is_a_noop() -> None:
    assert _run([]).results == []


def test_unknown_key() -> None:
    (check,) = _failed(_run([_cat(bogus=1)]))
    assert check.check_name == "firewall_category_lab-servers_unknown_key_bogus"


def test_uuid_hint() -> None:
    (check,) = _failed(_run([_cat(uuid="x")]))
    assert "box assigns it" in check.message


@pytest.mark.parametrize("name", ["", "   ", 5])
def test_bad_name(name: Any) -> None:
    assert [c.check_name for c in _failed(_run([_cat(name=name)]))] == [
        "firewall_category_lab-servers_name"
    ]


def test_reserved_name_by_config_and_handle() -> None:
    assert _failed(_run([_cat(name="infrafoundry")]))[0].check_name.endswith("_reserved_name")
    assert _failed(_run([_cat("infrafoundry")]))[0].check_name.endswith("_reserved_name")


@pytest.mark.parametrize("flag", ["auto", "lock"])
def test_non_bool_flags(flag: str) -> None:
    (check,) = _failed(_run([_cat(**{flag: "yes"})]))
    assert check.check_name == f"firewall_category_lab-servers_{flag}"


@pytest.mark.parametrize("color", [5, "blue", "#12345", "#1234567", "##123456"])
def test_bad_color(color: Any) -> None:
    (check,) = _failed(_run([_cat(color=color)]))
    assert check.check_name == "firewall_category_lab-servers_color"


def test_duplicate_effective_names() -> None:
    report = _run([_cat("a", name="same"), _cat("b", name="same")])
    assert [c.check_name for c in _failed(report)] == ["firewall_categories_unique_names"]
