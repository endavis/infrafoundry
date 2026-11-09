"""Unit tests for ``SourceNatValidator`` (#1333)."""

from __future__ import annotations

from typing import Any

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.opnsense.validators import SourceNatValidator
from infrafoundry.providers.opnsense.validators.context import OPNsenseValidationContext


def _errors(config: dict[str, Any]) -> list[str]:
    report = ValidationReport()
    SourceNatValidator(report).validate(
        OPNsenseValidationContext(
            resources=[
                ResourceConfig(
                    name="firewall.source_nat",
                    type="firewall.source_nat",
                    provider="opnsense",
                    config=config,
                )
            ]
        )
    )
    return [r.message for r in report.results if r.level == ValidationLevel.ERROR]


@pytest.mark.parametrize("mode", ["automatic", "hybrid", "advanced", "disabled"])
def test_valid_modes_pass(mode: str) -> None:
    assert _errors({"snat_mode": mode}) == []


def test_empty_config_passes() -> None:
    assert _errors({}) == []


def test_unknown_key_is_an_error() -> None:
    errors = _errors({"snat_mod": "hybrid"})
    assert len(errors) == 1
    assert "unknown key 'snat_mod'" in errors[0]


def test_non_string_mode_is_an_error() -> None:
    errors = _errors({"snat_mode": True})
    assert len(errors) == 1
    assert "must be a string" in errors[0]


def test_bad_mode_is_an_error() -> None:
    errors = _errors({"snat_mode": "manual"})
    assert len(errors) == 1
    assert "must be one of" in errors[0]
