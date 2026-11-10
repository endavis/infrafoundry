"""Unit tests for ``OpenVpnStaticKeyValidator`` (#1319)."""

from __future__ import annotations

from typing import Any

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationReport
from infrafoundry.providers.opnsense.validators import build_xref_index
from infrafoundry.providers.opnsense.validators.context import OPNsenseValidationContext
from infrafoundry.providers.opnsense.validators.openvpn_static_keys_validator import (
    OpenVpnStaticKeyValidator,
)

SECRET_KEY = "secret://env_secrets/vpn/key"  # nosec B105
LITERAL = "literal-key-material-not-real"  # nosec B105


def _key(name: str = "vpn-key", /, **overrides: Any) -> ResourceConfig:
    config: dict[str, Any] = {"mode": "crypt", "key": SECRET_KEY}
    config.update(overrides)
    config = {k: v for k, v in config.items() if v is not ...}
    return ResourceConfig(name=name, type="openvpn.static_keys", provider="opnsense", config=config)


def _run(resources: list[ResourceConfig]) -> ValidationReport:
    report = ValidationReport()
    OpenVpnStaticKeyValidator(report).validate(
        OPNsenseValidationContext(resources=resources, index=build_xref_index(resources))
    )
    return report


def _failed(report: ValidationReport) -> list[Any]:
    return [c for c in report.results if not c.passed]


def _fails(report: ValidationReport, check: str) -> list[Any]:
    return [c for c in _failed(report) if c.check_name == check]


def test_valid_passes() -> None:
    assert _failed(_run([_key()])) == []


def test_no_resources_is_a_noop() -> None:
    assert _run([]).results == []


def test_literal_key_is_error_and_not_echoed() -> None:
    report = _run([_key(key=LITERAL)])
    assert _fails(report, "openvpn_static_key_vpn-key_key_literal_secret")
    assert all(LITERAL not in c.message for c in report.results)


def test_missing_key_is_error() -> None:
    assert _fails(_run([_key(key=...)]), "openvpn_static_key_vpn-key_key_required")


def test_missing_or_bad_mode() -> None:
    assert _fails(_run([_key(mode=...)]), "openvpn_static_key_vpn-key_mode_required")
    assert _fails(_run([_key(mode="tls")]), "openvpn_static_key_vpn-key_mode")


def test_all_modes_pass() -> None:
    for mode in ("auth", "crypt", "crypt-v2"):
        assert _failed(_run([_key(mode=mode)])) == [], mode


def test_unknown_key_and_uuid_hint() -> None:
    report = _run([_key(bogus=1, uuid="x")])
    assert _fails(report, "openvpn_static_key_vpn-key_unknown_key_bogus")
    uuid_fail = _fails(report, "openvpn_static_key_vpn-key_unknown_key_uuid")
    assert "box assigns" in uuid_fail[0].message


def test_duplicate_descriptions() -> None:
    report = _run([_key("a", description="same"), _key("b", description="same")])
    assert _fails(report, "openvpn_static_keys_unique_descriptions")


def test_bad_flag_types_and_description() -> None:
    report = _run([_key(lock="yes", update_key=1, description=5)])
    assert _fails(report, "openvpn_static_key_vpn-key_lock")
    assert _fails(report, "openvpn_static_key_vpn-key_update_key")
    assert _fails(report, "openvpn_static_key_vpn-key_description")
