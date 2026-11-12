"""Unit tests for ``OpenVpnInstanceValidator`` (#808)."""

from __future__ import annotations

from typing import Any

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationReport
from infrafoundry.providers.opnsense.validators import build_xref_index
from infrafoundry.providers.opnsense.validators.context import OPNsenseValidationContext
from infrafoundry.providers.opnsense.validators.openvpn_instances_validator import (
    OpenVpnInstanceValidator,
)

SECRET_USER = "secret://env_secrets/vpn/user"  # fake fixture value
SECRET_PW = "secret://env_secrets/vpn/pw"  # fake fixture value
LITERAL = "literal-value-not-real"


def _inst(name: str = "vpn-a", /, **overrides: Any) -> ResourceConfig:
    config: dict[str, Any] = {
        "remote": ["vpn.example.com"],
        "ca_ref": "vpn-ca",
        "username": SECRET_USER,
        "password": SECRET_PW,
    }
    config.update(overrides)
    return ResourceConfig(name=name, type="openvpn.instances", provider="opnsense", config=config)


def _ca(name: str = "vpn-ca") -> ResourceConfig:
    return ResourceConfig(name=name, type="trust.cas", provider="opnsense", config={"crt": "x"})


def _cert(name: str = "vpn-cert") -> ResourceConfig:
    return ResourceConfig(
        name=name, type="trust.certs", provider="opnsense", config={"crt": "x", "ca_ref": "vpn-ca"}
    )


def _run(resources: list[ResourceConfig]) -> ValidationReport:
    report = ValidationReport()
    OpenVpnInstanceValidator(report).validate(
        OPNsenseValidationContext(resources=resources, index=build_xref_index(resources))
    )
    return report


def _failed(report: ValidationReport) -> list[Any]:
    return [c for c in report.results if not c.passed]


def _fails(report: ValidationReport, check: str) -> list[Any]:
    return [c for c in _failed(report) if c.check_name == check]


def test_valid_passes() -> None:
    assert _failed(_run([_ca(), _inst()])) == []


def test_no_resources() -> None:
    assert _run([]).results == []


def test_literal_credentials_error_without_echo() -> None:
    report = _run([_ca(), _inst(username=LITERAL, password=LITERAL)])
    assert _fails(report, "openvpn_instance_vpn-a_username_literal_secret")
    assert _fails(report, "openvpn_instance_vpn-a_password_literal_secret")
    assert all(LITERAL not in c.message for c in _failed(report))


def test_empty_credentials_ok() -> None:
    assert _failed(_run([_ca(), _inst(username="", password="")])) == []


def test_update_password_without_password() -> None:
    report = _run([_ca(), _inst(password="", update_password=True)])
    assert _fails(report, "openvpn_instance_vpn-a_update_password")


def test_box_assigned_refused_and_unknown_keys() -> None:
    report = _run([_ca(), _inst(uuid="x", role="server", cert="c", tls_key="k", ca="r", bogus=1)])
    for key in ("uuid", "role", "cert", "tls_key", "ca", "bogus"):
        assert _fails(report, f"openvpn_instance_vpn-a_unknown_key_{key}"), key


def test_vpnid_valid_and_invalid() -> None:
    assert _failed(_run([_ca(), _inst(vpnid=3)])) == []
    for bad in ("1", 0, -1, True):
        report = _run([_ca(), _inst(vpnid=bad)])
        assert _fails(report, "openvpn_instance_vpn-a_vpnid"), bad


def test_duplicate_vpnid_errors() -> None:
    report = _run([_ca(), _inst("a", vpnid=2), _inst("b", vpnid=2)])
    assert _fails(report, "openvpn_instances_unique_vpnids")
    assert _failed(_run([_ca(), _inst("a", vpnid=2), _inst("b", vpnid=3), _inst("c")])) == []


def test_hyphenated_wire_spelling_hint() -> None:
    report = _run([_ca(), _inst(**{"reneg-sec": 5})])
    (failure,) = _fails(report, "openvpn_instance_vpn-a_unknown_key_reneg-sec")
    assert "reneg_sec" in failure.message


def test_remote_required() -> None:
    assert _fails(_run([_ca(), _inst(remote=[])]), "openvpn_instance_vpn-a_remote_required")


def test_ca_ref_required_and_xref() -> None:
    assert _fails(_run([_inst(ca_ref="")]), "openvpn_instance_vpn-a_ca_ref_required")
    assert _fails(_run([_inst(ca_ref="missing")]), "openvpn_instance_vpn-a_ca_ref")
    assert _fails(_run([_ca(), _inst(ca_ref=5)]), "openvpn_instance_vpn-a_ca_ref_type")


def test_enum_and_range_checks() -> None:
    report = _run([_ca(), _inst(proto="sctp", port=0, verb=12, enabled="yes", route="a")])
    for key in ("proto", "port", "verb", "enabled", "route"):
        assert _fails(report, f"openvpn_instance_vpn-a_{key}"), key


def test_flag_types() -> None:
    report = _run([_ca(), _inst(lock="x", update_password="y", description=5)])
    for key in ("lock", "update_password", "description"):
        assert _fails(report, f"openvpn_instance_vpn-a_{key}"), key


def test_duplicate_descriptions() -> None:
    report = _run([_ca(), _inst("a", description="Same"), _inst("b", description="Same")])
    assert _fails(report, "openvpn_instances_unique_descriptions")


def test_cert_ref_valid_bare_and_absolute_forms() -> None:
    for ref in ("vpn-cert", "trust.certs.vpn-cert"):
        assert _failed(_run([_ca(), _cert(), _inst(cert_ref=ref)])) == [], ref


def test_cert_ref_unknown_or_wrong_type_fails() -> None:
    assert _fails(_run([_ca(), _inst(cert_ref="missing")]), "openvpn_instance_vpn-a_cert_ref")
    # A name that only exists as a CA is not a certificate.
    assert _fails(_run([_ca(), _inst(cert_ref="vpn-ca")]), "openvpn_instance_vpn-a_cert_ref")


def test_cert_ref_type_errors() -> None:
    for bad in ("", 5):
        report = _run([_ca(), _cert(), _inst(cert_ref=bad)])
        assert _fails(report, "openvpn_instance_vpn-a_cert_ref_type"), bad


def test_cert_ref_absent_adds_no_check() -> None:
    assert _failed(_run([_ca(), _inst()])) == []
    assert _failed(_run([_ca(), _inst(cert_ref=None)])) == []


def _static_key(name: str = "vpn-key") -> ResourceConfig:
    return ResourceConfig(
        name=name,
        type="openvpn.static_keys",
        provider="opnsense",
        config={"mode": "crypt", "key": "secret://env_secrets/vpn/key"},
    )


def test_tls_key_ref_valid_bare_and_absolute_forms() -> None:
    for ref in ("vpn-key", "openvpn.static_keys.vpn-key"):
        assert _failed(_run([_ca(), _static_key(), _inst(tls_key_ref=ref)])) == [], ref


def test_tls_key_ref_unknown_or_wrong_type_fails() -> None:
    assert _fails(_run([_ca(), _inst(tls_key_ref="missing")]), "openvpn_instance_vpn-a_tls_key_ref")
    assert _fails(_run([_ca(), _inst(tls_key_ref="vpn-ca")]), "openvpn_instance_vpn-a_tls_key_ref")


def test_tls_key_ref_type_errors() -> None:
    for bad in ("", 5):
        report = _run([_ca(), _static_key(), _inst(tls_key_ref=bad)])
        assert _fails(report, "openvpn_instance_vpn-a_tls_key_ref_type"), bad


def test_tls_key_ref_absent_adds_no_check() -> None:
    assert _failed(_run([_ca(), _inst()])) == []
    assert _failed(_run([_ca(), _inst(tls_key_ref=None)])) == []
