"""Unit tests for ``SystemTuningValidator`` duplicate detection and wiring (#1149)."""

from __future__ import annotations

from unittest.mock import MagicMock

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.opnsense.validator import OPNsenseValidator
from infrafoundry.providers.opnsense.validators import SystemTuningValidator
from infrafoundry.providers.opnsense.validators.context import OPNsenseValidationContext


def _res(items: list[dict[str, object]]) -> ResourceConfig:
    return ResourceConfig(
        name="settings", type="system.tuning", provider="opnsense", config={"items": items}
    )


def test_duplicate_tunable_is_error() -> None:
    report = ValidationReport()
    SystemTuningValidator(report).validate(
        OPNsenseValidationContext(
            resources=[_res([{"tunable": "a", "value": 1}, {"tunable": "a", "value": 2}])]
        )
    )
    failed = [c for c in report.results if not c.passed]
    assert [c.check_name for c in failed] == ["system_tuning_settings_items_duplicate"]
    assert failed[0].level == ValidationLevel.ERROR


def test_distinct_tunables_pass() -> None:
    report = ValidationReport()
    SystemTuningValidator(report).validate(
        OPNsenseValidationContext(
            resources=[_res([{"tunable": "a", "value": 1}, {"tunable": "b", "value": 2}])]
        )
    )
    assert not report.has_errors()


def test_opnsense_validator_wires_firmware_and_tuning() -> None:
    validator = OPNsenseValidator(MagicMock(), ValidationReport())
    assert validator.system_firmware_validator is not None
    assert validator.system_tuning_validator is not None
