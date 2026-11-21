"""Tests for the MikroTik validator."""

from pathlib import Path
from unittest.mock import patch

from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.mikrotik.client import RouterOSConnectionError
from infrafoundry.providers.mikrotik.validator import MikroTikValidator

from .conftest import SETTINGS, FakeRouterOS, make_env, resource

GOOD = {
    "api_url": "https://192.0.2.2",
    "username": "admin",
    "password": "secret://env_secrets/mikrotik/password",
}
SECRETS = {"mikrotik": {"password": "pw-example"}}


def _validator(
    fake: FakeRouterOS | None = None, settings: dict[str, object] | None = None
) -> tuple[MikroTikValidator, ValidationReport]:
    report = ValidationReport()
    env = make_env(GOOD if settings is None else settings, SECRETS)
    validator = MikroTikValidator(
        env, report, Path("."), client_factory=lambda s: fake or FakeRouterOS({})
    )
    return validator, report


def _failed(report: ValidationReport) -> list[str]:
    return [r.check_name for r in report.results if not r.passed]


def test_offline_schema_findings_become_report_errors() -> None:
    validator, report = _validator()
    validator.validate_offline([resource("interface.bridge", "b", bogus=1)])
    assert _failed(report) == ["mikrotik_schema_b"]


def test_offline_clean_config_passes() -> None:
    validator, report = _validator()
    validator.validate_offline([resource("interface.bridge", "b")])
    assert _failed(report) == []


def test_offline_missing_settings_and_secret() -> None:
    validator, report = _validator(settings={"api_url": "https://192.0.2.2"})
    validator.validate_offline([])
    assert _failed(report) == ["mikrotik_settings"]

    report = ValidationReport()
    env = make_env(GOOD, {})
    MikroTikValidator(env, report).validate_offline([])
    assert _failed(report) == ["mikrotik_secret_password"]


def _connect(
    fake: FakeRouterOS, version: str, api_url: str = "https://192.0.2.2"
) -> ValidationReport:
    fake.tables["system/resource"] = [{"version": version}]
    validator, report = _validator(fake)
    settings = SETTINGS.__class__(api_url, "admin", "pw")
    with patch("infrafoundry.providers.mikrotik.validator.load_settings", return_value=settings):
        validator.validate_connectivity()
    return report


def test_connectivity_version_7_passes() -> None:
    report = _connect(FakeRouterOS({}), "7.14 (stable)")
    assert _failed(report) == []


def test_connectivity_version_6_errors() -> None:
    assert _failed(_connect(FakeRouterOS({}), "6.49.10 (long-term)")) == ["mikrotik_version"]


def test_connectivity_http_warns() -> None:
    report = _connect(FakeRouterOS({}), "7.14", "http://192.0.2.2")
    warnings = [r for r in report.results if not r.passed]
    assert [(r.check_name, r.level) for r in warnings] == [
        ("mikrotik_http", ValidationLevel.WARNING)
    ]


def test_connectivity_failure_is_reported() -> None:
    validator, report = _validator()
    with patch(
        "infrafoundry.providers.mikrotik.validator.load_settings",
        side_effect=RouterOSConnectionError("down"),
    ):
        validator.validate_connectivity()
    assert _failed(report) == ["mikrotik_connectivity"]


def test_reference_to_unknown_interface_is_flagged(factory: FakeRouterOS) -> None:
    validator, report = _validator(factory)
    resources = [
        resource("interface.vlan", "vlan10", interface="bridge", **{"vlan-id": 10}),
        resource("ip.address", "a", address="192.0.2.2/24", interface="vlan10"),
        resource("ip.address", "b", address="198.51.100.2/24", interface="ether9"),
    ]
    with patch("infrafoundry.providers.mikrotik.validator.load_settings", return_value=SETTINGS):
        validator.validate_references(resources)
    assert _failed(report) == ["mikrotik_reference_b"]


def test_reference_to_interface_declared_in_another_package(factory: FakeRouterOS) -> None:
    """A scoped run counts an interface declared in the reference set as existing (#1568)."""
    vlan = resource("interface.vlan", "vlan10", interface="bridge", **{"vlan-id": 10})
    addr = resource("ip.address", "a", address="192.0.2.2/24", interface="vlan10")
    validator, report = _validator(factory)
    with patch("infrafoundry.providers.mikrotik.validator.load_settings", return_value=SETTINGS):
        validator.validate_references([addr], [vlan, addr])
    assert _failed(report) == []

    validator, report = _validator(factory)
    with patch("infrafoundry.providers.mikrotik.validator.load_settings", return_value=SETTINGS):
        validator.validate_references([addr])
    assert _failed(report) == ["mikrotik_reference_a"]
