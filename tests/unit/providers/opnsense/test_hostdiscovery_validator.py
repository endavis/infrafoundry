"""Unit tests for ``HostDiscoveryValidator`` (#792)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.opnsense.validator import OPNsenseValidator
from infrafoundry.providers.opnsense.validators import HostDiscoveryValidator
from infrafoundry.providers.opnsense.validators.context import OPNsenseValidationContext


def _run(
    config: dict[str, Any],
    *,
    managed: set[str] | None = None,
    live: dict[str, Any] | None = None,
) -> ValidationReport:
    report = ValidationReport()
    HostDiscoveryValidator(report).validate(
        OPNsenseValidationContext(
            resources=[
                ResourceConfig(
                    name="hostdiscovery",
                    type="hostdiscovery",
                    provider="opnsense",
                    config=config,
                )
            ],
            interface_assignment_names=managed or set(),
            existing_interfaces=live or {},
        )
    )
    return report


def _errors(report: ValidationReport) -> list[str]:
    return [r.message for r in report.results if r.level == ValidationLevel.ERROR]


def test_valid_config_passes() -> None:
    report = _run(
        {
            "enabled": True,
            "promisc": False,
            "verbose": False,
            "skip_nets": ["192.0.2.0/24"],
            "interface": ["lan"],
            "expire4_interval": 0,
            "expire6_interval": 60,
        },
        managed={"lan"},
    )
    assert not _errors(report)


def test_empty_config_passes() -> None:
    assert not _errors(_run({}))


def test_live_interface_passes() -> None:
    assert not _errors(_run({"interface": ["opt1"]}, live={"opt1": {}}))


@pytest.mark.parametrize(
    ("config", "needle"),
    [
        ({"bogus": 1}, "unknown key 'bogus'"),
        ({"verbose": "yes"}, "verbose must be a boolean"),
        ({"expire4_interval": "5"}, "non-negative integer"),
        ({"expire6_interval": -1}, "non-negative integer"),
        ({"expire6_interval": True}, "non-negative integer"),
        ({"skip_nets": "192.0.2.0/24"}, "must be a list"),
        ({"skip_nets": ["bad"]}, "not a valid CIDR"),
        ({"skip_nets": ["192.0.2.0/24,198.51.100.0/24"]}, "must not contain a comma"),
        ({"skip_nets": [5]}, "non-empty string"),
        ({"interface": ["nowhere"]}, "is unknown"),
        ({"interface": "lan"}, "must be a list"),
    ],
)
def test_one_error_per_bad_input(config: dict[str, Any], needle: str) -> None:
    errors = _errors(_run(config))
    assert len(errors) == 1
    assert needle in errors[0]


def test_validator_is_wired_into_opnsense_validator() -> None:
    validator = OPNsenseValidator(MagicMock(), ValidationReport())
    assert isinstance(validator.hostdiscovery_validator, HostDiscoveryValidator)
    refs = validator._collect_resource_references(
        [ResourceConfig(name="hostdiscovery", type="hostdiscovery", provider="opnsense", config={})]
    )
    assert len(refs["hostdiscovery"]) == 1
