"""Unit tests for ``SystemFirmwareValidator`` update settings (#1452)."""

from __future__ import annotations

from typing import Any

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.opnsense.validators import SystemFirmwareValidator
from infrafoundry.providers.opnsense.validators.context import OPNsenseValidationContext


def _run(**config: Any) -> ValidationReport:
    report = ValidationReport()
    resource = ResourceConfig(
        name="system.firmware", type="system.firmware", provider="opnsense", config=config
    )
    SystemFirmwareValidator(report).validate(OPNsenseValidationContext(resources=[resource]))
    return report


def _failed(report: ValidationReport) -> list[tuple[str, ValidationLevel]]:
    return [(c.check_name, c.level) for c in report.results if not c.passed]


def test_update_true_with_timeout_passes() -> None:
    assert _failed(_run(update=True, update_timeout=900)) == []


def test_update_absent_passes() -> None:
    assert _failed(_run(plugins=["os-tailscale"])) == []


def test_update_must_be_bool() -> None:
    failed = _failed(_run(update="yes"))
    assert failed == [("system_firmware_system.firmware_update", ValidationLevel.ERROR)]


def test_timeout_must_be_positive_int() -> None:
    for bad in (0, -5, "300", 1.5, True):
        failed = _failed(_run(update=True, update_timeout=bad))
        assert failed == [("system_firmware_system.firmware_update_timeout", ValidationLevel.ERROR)]


def test_timeout_without_update_warns() -> None:
    failed = _failed(_run(update_timeout=900))
    assert failed == [
        ("system_firmware_system.firmware_update_timeout_unused", ValidationLevel.WARNING)
    ]


def test_timeout_with_update_false_warns() -> None:
    failed = _failed(_run(update=False, update_timeout=900))
    assert [level for _, level in failed] == [ValidationLevel.WARNING]
