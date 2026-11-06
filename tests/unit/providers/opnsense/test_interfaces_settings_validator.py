"""Unit tests for ``InterfacesSettingsValidator`` (#1092)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.opnsense.validator import OPNsenseValidator
from infrafoundry.providers.opnsense.validators import InterfacesSettingsValidator


def _run(config: dict[str, Any]) -> ValidationReport:
    report = ValidationReport()
    InterfacesSettingsValidator(report).validate(
        [
            ResourceConfig(
                name="interfaces.settings",
                type="interfaces.settings",
                provider="opnsense",
                config=config,
            )
        ]
    )
    return report


def _errors(report: ValidationReport) -> list[str]:
    return [r.message for r in report.results if r.level == ValidationLevel.ERROR]


def test_valid_config_passes() -> None:
    report = _run(
        {
            "disable_checksum_offloading": True,
            "vlan_hardware_filtering": "default",
            "dhcp6_duid": "00:01",
            "dhcp6_ra_timeout": 0,
        }
    )
    assert not _errors(report)


def test_empty_config_passes() -> None:
    assert not _errors(_run({}))


@pytest.mark.parametrize(
    ("config", "needle"),
    [
        ({"bogus": 1}, "unknown key 'bogus'"),
        ({"dhcp6_debug": "yes"}, "dhcp6_debug must be a boolean"),
        ({"disable_ipv6": 1}, "disable_ipv6 must be a boolean"),
        ({"vlan_hardware_filtering": "off"}, "vlan_hardware_filtering must be one of"),
        ({"vlan_hardware_filtering": True}, "vlan_hardware_filtering must be one of"),
        ({"dhcp6_duid": 12}, "dhcp6_duid must be a string"),
        ({"dhcp6_ra_timeout": "10"}, "non-negative integer"),
        ({"dhcp6_ra_timeout": True}, "non-negative integer"),
        ({"dhcp6_ra_timeout": -5}, "non-negative integer"),
    ],
)
def test_one_error_per_bad_input(config: dict[str, Any], needle: str) -> None:
    errors = _errors(_run(config))
    assert len(errors) == 1
    assert needle in errors[0]


def test_validator_is_wired_into_opnsense_validator() -> None:
    validator = OPNsenseValidator(MagicMock(), ValidationReport())
    assert isinstance(validator.interfaces_settings_validator, InterfacesSettingsValidator)
