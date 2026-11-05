"""Unit tests for ``UnboundAdvancedValidator`` (#1254)."""

from __future__ import annotations

import copy
from typing import Any

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.opnsense.validators import UnboundAdvancedValidator


def _run(config: dict[str, Any]) -> ValidationReport:
    report = ValidationReport()
    UnboundAdvancedValidator(report).validate(
        [
            ResourceConfig(
                name="unbound.advanced",
                type="unbound.advanced",
                provider="opnsense",
                config=config,
            )
        ]
    )
    return report


def test_valid_config_passes() -> None:
    report = _run(
        {
            "private_domains": ["a.example"],
            "insecure_domains": [],
            "private_addresses": ["10.0.0.0/8", "fd00::/8"],
        }
    )
    assert not report.has_errors()


@pytest.mark.parametrize(
    "config",
    [
        {"bogus": []},
        {"private_domains": "a.example"},
        {"private_domains": [""]},
        {"private_domains": [5]},
        {"insecure_domains": ["a.example,b.example"]},
        {"insecure_domains": ["a b"]},
        {"private_addresses": ["not-a-cidr"]},
    ],
)
def test_invalid_config_is_error(config: dict[str, Any]) -> None:
    report = _run(config)
    failed = [c for c in report.results if not c.passed]
    assert failed
    assert all(c.level == ValidationLevel.ERROR for c in failed)


def test_validator_does_not_mutate_config() -> None:
    config = {"private_domains": [" a.example"], "private_addresses": ["10.0.0.1/8"]}
    before = copy.deepcopy(config)
    _run(config)
    assert config == before
