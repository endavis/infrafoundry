"""QNAP validator: offline findings and connectivity with a fake client."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from infrafoundry.core.validation import ValidationReport
from infrafoundry.providers.qnap import validator as qnap_validator
from infrafoundry.providers.qnap.client import QnapAuthError, QnapTlsPinError
from infrafoundry.providers.qnap.validator import QnapValidator

from .conftest import RAW_SETTINGS, SETTINGS, firmware, lag, make_env, vlan
from .update_fake import FakeQnapSwitch

pytestmark = pytest.mark.unit

SECRETS = {"qnap": {"username": "u", "password": "p"}}


def _names(report: ValidationReport) -> list[str]:
    return [c.check_name for c in report.results if not c.passed]


def test_valid_offline_has_no_findings() -> None:
    report = ValidationReport()
    env = make_env(dict(RAW_SETTINGS), SECRETS)
    QnapValidator(env, report).validate_offline([firmware()])
    assert _names(report) == []


def test_plaintext_secret_is_a_finding() -> None:
    report = ValidationReport()
    env = make_env({**RAW_SETTINGS, "password": "plain"}, SECRETS)
    QnapValidator(env, report).validate_offline([firmware()])
    assert _names(report)


def test_missing_env_secret_is_a_finding() -> None:
    report = ValidationReport()
    env = make_env(dict(RAW_SETTINGS), {"qnap": {"username": "u"}})
    QnapValidator(env, report).validate_offline([firmware()])
    assert "qnap_secret_password" in _names(report)


def test_schema_finding() -> None:
    report = ValidationReport()
    env = make_env(dict(RAW_SETTINGS), SECRETS)
    QnapValidator(env, report).validate_offline([firmware(version="2.6")])
    assert "qnap_schema_sw-fw" in _names(report)


def _connect(factory: Any, **settings: Any) -> ValidationReport:
    report = ValidationReport()
    env = make_env(dict(RAW_SETTINGS), SECRETS)
    validator = QnapValidator(env, report, Path("/unused"), client_factory=factory)
    with patch.object(
        qnap_validator,
        "load_settings",
        return_value=SETTINGS.__class__(**{**SETTINGS.__dict__, **settings}),
    ):
        validator.validate_connectivity()
    return report


def test_connectivity_passes() -> None:
    report = _connect(lambda settings: FakeQnapSwitch())
    assert _names(report) == []
    assert any("QNAP firmware 2.5.0 reachable" in c.message for c in report.results)


def test_connectivity_pin_failure() -> None:
    def factory(settings: Any) -> Any:
        class Bad(FakeQnapSwitch):
            def about(self) -> dict[str, Any]:
                raise QnapTlsPinError("pin mismatch")

        return Bad()

    assert _names(_connect(factory)) == ["qnap_connectivity"]


def test_connectivity_auth_failure() -> None:
    def factory(settings: Any) -> Any:
        switch = FakeQnapSwitch()
        switch.login_errors = [QnapAuthError("refused")]
        return switch

    assert _names(_connect(factory)) == ["qnap_connectivity"]


def test_verify_ssl_false_warns() -> None:
    report = _connect(lambda settings: FakeQnapSwitch(), verify_ssl=False)
    assert any(c.check_name == "qnap_verify_ssl" for c in report.results)


def test_vlan_and_lag_schema_findings_surface() -> None:
    report = ValidationReport()
    env = make_env(dict(RAW_SETTINGS), SECRETS)
    QnapValidator(env, report).validate_offline(
        [vlan("bad", id=5000), lag("lag", group=1, mode="lacp", members=["lag2"])]
    )
    assert _names(report) == ["qnap_schema_bad", "qnap_schema_lag"]


def test_valid_vlan_and_lag_have_no_findings() -> None:
    report = ValidationReport()
    env = make_env(dict(RAW_SETTINGS), SECRETS)
    QnapValidator(env, report).validate_offline(
        [vlan(id=10, tagged=[1]), lag(group=1, mode="lacp", members=[5, 6])]
    )
    assert _names(report) == []


def test_doctor_warns_when_the_lockout_override_is_set() -> None:
    report = _connect(lambda settings: FakeQnapSwitch(), allow_lockout_risk=True)
    [warning] = [c for c in report.results if c.check_name == "qnap_allow_lockout_risk"]
    assert not warning.passed and "allow_lockout_risk" in warning.message
    assert not any(
        c.check_name == "qnap_allow_lockout_risk"
        for c in _connect(lambda settings: FakeQnapSwitch()).results
    )
