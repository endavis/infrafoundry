"""Unit tests for ``TrustValidator`` (#807)."""

from __future__ import annotations

from typing import Any

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.opnsense.validators import build_xref_index
from infrafoundry.providers.opnsense.validators.context import OPNsenseValidationContext
from infrafoundry.providers.opnsense.validators.trust_validator import TrustValidator

CRT = "-----BEGIN CERTIFICATE-----\nFAKE\n-----END CERTIFICATE-----"
KEY = "-----BEGIN PRIVATE" + " KEY-----\nFAKEKEY\n-----END PRIVATE" + " KEY-----"
SECRET_CRT = "secret://env_secrets/trust/vpn/crt"
SECRET_PRV = "secret://env_secrets/trust/vpn/prv"


def _ca(name: str = "vpn-ca", **overrides: Any) -> ResourceConfig:
    config: dict[str, Any] = {"crt": SECRET_CRT, "prv": SECRET_PRV}
    config.update(overrides)
    return ResourceConfig(name=name, type="trust.cas", provider="opnsense", config=config)


def _cert(name: str = "web-cert", **overrides: Any) -> ResourceConfig:
    config: dict[str, Any] = {"crt": SECRET_CRT, "prv": SECRET_PRV, "ca_ref": "vpn-ca"}
    config.update(overrides)
    return ResourceConfig(name=name, type="trust.certs", provider="opnsense", config=config)


def _run(resources: list[ResourceConfig]) -> ValidationReport:
    report = ValidationReport()
    TrustValidator(report).validate(
        OPNsenseValidationContext(resources=resources, index=build_xref_index(resources))
    )
    return report


def _failures(report: ValidationReport, check: str) -> list[Any]:
    return [c for c in report.results if c.check_name == check and not c.passed]


def test_valid_secrets_pass() -> None:
    report = _run([_ca(), _cert()])
    assert not [c for c in report.results if not c.passed]


def test_no_resources_no_checks() -> None:
    assert _run([]).results == []


def test_unknown_key_with_hint() -> None:
    report = _run([_ca(descr="x", refid="y", bogus=1)])
    assert _failures(report, "trust_ca_vpn-ca_unknown_key_descr")
    assert _failures(report, "trust_ca_vpn-ca_unknown_key_refid")
    assert _failures(report, "trust_ca_vpn-ca_unknown_key_bogus")


def test_crt_required() -> None:
    report = _run([_ca(crt="")])
    assert _failures(report, "trust_ca_vpn-ca_crt_required")


def test_literal_prv_is_error_and_not_echoed() -> None:
    report = _run([_ca(prv=KEY)])
    failed = _failures(report, "trust_ca_vpn-ca_prv_literal")
    assert failed
    assert failed[0].level == ValidationLevel.ERROR
    assert all("FAKEKEY" not in c.message for c in report.results)


def test_literal_crt_and_csr_are_warnings() -> None:
    report = _run([_cert(crt=CRT, csr=CRT)])
    for key in ("crt", "csr"):
        failed = _failures(report, f"trust_cert_web-cert_{key}_literal")
        assert failed
        assert failed[0].level == ValidationLevel.WARNING
    assert not report.has_errors() or not _failures(report, "trust_cert_web-cert_crt_pem")


def test_non_pem_literal() -> None:
    report = _run([_ca(crt="not a pem")])
    assert _failures(report, "trust_ca_vpn-ca_crt_pem")


def test_duplicate_descriptions() -> None:
    report = _run([_ca("a", description="same"), _ca("b", description="same")])
    assert _failures(report, "trust.cas_unique_descriptions")
    assert not _failures(_run([_ca("a"), _cert("a")]), "trust.cas_unique_descriptions")


def test_acme_ca_description_error() -> None:
    report = _run([_ca(description="R10")])
    assert _failures(report, "trust_ca_vpn-ca_acme_owned")
    assert not _failures(_run([_cert(description="R10"), _ca()]), "trust_cert_web-cert_acme_owned")


def test_ca_ref_resolves_and_misses() -> None:
    assert not _failures(_run([_ca(), _cert()]), "trust_cert_web-cert_ca_ref")
    assert _failures(_run([_cert()]), "trust_cert_web-cert_ca_ref")
    assert _failures(_run([_ca(), _cert(ca_ref="nope")]), "trust_cert_web-cert_ca_ref")


def test_type_values() -> None:
    for good in ("server", "client", "combined"):
        assert not _failures(_run([_ca(), _cert(type=good)]), "trust_cert_web-cert_type")
    assert _failures(_run([_ca(), _cert(type="bogus")]), "trust_cert_web-cert_type")
