"""Unit tests for ``SyslogSettingsValidator`` (#804)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.opnsense.validator import OPNsenseValidator
from infrafoundry.providers.opnsense.validators import SyslogSettingsValidator
from infrafoundry.providers.opnsense.validators.context import OPNsenseValidationContext


def _run(config: dict[str, Any]) -> ValidationReport:
    report = ValidationReport()
    SyslogSettingsValidator(report).validate(
        OPNsenseValidationContext(
            resources=[
                ResourceConfig(
                    name="syslog.settings",
                    type="syslog.settings",
                    provider="opnsense",
                    config=config,
                )
            ]
        )
    )
    return report


def _errors(report: ValidationReport) -> list[str]:
    return [r.message for r in report.results if r.level == ValidationLevel.ERROR]


def test_valid_and_empty_config_pass() -> None:
    assert not _errors(
        _run({"enabled": True, "log_local": False, "max_preserve": 0, "max_file_size": 10})
    )
    assert not _errors(_run({}))


@pytest.mark.parametrize(
    ("config", "needle"),
    [
        ({"bogus": 1}, "unknown key 'bogus'"),
        ({"enabled": "yes"}, "enabled must be a boolean"),
        ({"log_local": 1}, "log_local must be a boolean"),
        ({"max_preserve": "5"}, "non-negative integer"),
        ({"max_preserve": True}, "non-negative integer"),
        ({"max_file_size": -1}, "non-negative integer"),
    ],
)
def test_one_error_per_bad_input(config: dict[str, Any], needle: str) -> None:
    errors = _errors(_run(config))
    assert len(errors) == 1
    assert needle in errors[0]


def test_validator_is_wired_into_opnsense_validator() -> None:
    validator = OPNsenseValidator(MagicMock(), ValidationReport())
    assert isinstance(validator.syslog_settings_validator, SyslogSettingsValidator)
