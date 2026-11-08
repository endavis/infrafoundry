"""Unit tests for ``UnboundSettingsValidator`` (#1091)."""

from __future__ import annotations

from typing import Any

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.opnsense.validators import UnboundSettingsValidator
from infrafoundry.providers.opnsense.validators.context import OPNsenseValidationContext


def _run(config: dict[str, Any]) -> ValidationReport:
    report = ValidationReport()
    UnboundSettingsValidator(report).validate(
        OPNsenseValidationContext(
            resources=[
                ResourceConfig(
                    name="unbound.settings",
                    type="unbound.settings",
                    provider="opnsense",
                    config=config,
                )
            ]
        )
    )
    return report


def test_valid_config_passes() -> None:
    report = _run({"general": {"enabled": True, "port": 53}, "advanced": {"prefetch": True}})
    assert not report.results


@pytest.mark.parametrize(
    ("config", "check_suffix"),
    [
        ({"bogus": {}}, "section_bogus"),
        ({"general": {"nope": 1}}, "general_nope"),
        ({"general": {"port": 0}}, "general_port"),
        ({"advanced": {"privatedomain": []}}, "advanced_privatedomain"),
        ({"advanced": {"private_addresses": []}}, "advanced_private_addresses"),
        ({"general": 5}, "general"),
    ],
)
def test_invalid_config_is_an_error(config: dict[str, Any], check_suffix: str) -> None:
    report = _run(config)
    names = [r.check_name for r in report.results]
    assert f"unbound_settings_unbound.settings_{check_suffix}" in names
    assert all(r.level == ValidationLevel.ERROR and not r.passed for r in report.results)


def test_owned_field_message_points_at_unbound_advanced() -> None:
    report = _run({"advanced": {"privateaddress": []}})
    assert "unbound.advanced" in report.results[0].message
