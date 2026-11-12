"""Unit tests for ``AcmeClientValidator`` (#790)."""

from __future__ import annotations

from typing import Any

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.opnsense.validators import AcmeClientValidator, build_xref_index
from infrafoundry.providers.opnsense.validators.context import OPNsenseValidationContext

SECRET = (
    "secret://env_secrets/opnsense/acmeclient/validations/dns/dns_cf_token"  # fake fixture value
)
LITERAL = "literal-value-not-real"


def _res(type_name: str, name: str, **config: Any) -> ResourceConfig:
    config.setdefault("name", name)  # loader-injected
    return ResourceConfig(name=name, type=type_name, provider="opnsense", config=config)


def _account(name: str = "acct", **c: Any) -> ResourceConfig:
    c.setdefault("email", "admin@example.com")
    c.setdefault("ca", "letsencrypt_test")
    return _res("acmeclient.accounts", name, **c)


def _validation(name: str = "dns", **c: Any) -> ResourceConfig:
    c.setdefault("method", "dns01")
    c.setdefault("dns_service", "dns_cf")
    c.setdefault("dns_cf_token", SECRET)
    return _res("acmeclient.validations", name, **c)


def _action(name: str = "gui", **c: Any) -> ResourceConfig:
    c.setdefault("type", "configd_restart_gui")
    return _res("acmeclient.actions", name, **c)


def _cert(name: str = "web", **c: Any) -> ResourceConfig:
    c.setdefault("common_name", "fw-test.example.com")
    c.setdefault("account", "acct")
    c.setdefault("validation", "dns")
    return _res("acmeclient.certs", name, **c)


def _settings(**c: Any) -> ResourceConfig:
    return ResourceConfig(
        name="acmeclient.settings", type="acmeclient.settings", provider="opnsense", config=c
    )


def _base() -> list[ResourceConfig]:
    return [_account(), _validation(), _action(), _cert(restart_actions=["gui"])]


def _run(resources: list[ResourceConfig]) -> ValidationReport:
    report = ValidationReport()
    AcmeClientValidator(report).validate(
        OPNsenseValidationContext(resources=resources, index=build_xref_index(resources))
    )
    return report


def _level(report: ValidationReport, level: ValidationLevel) -> list[Any]:
    return [c for c in report.results if not c.passed and c.level == level]


def _errors(report: ValidationReport) -> list[Any]:
    return _level(report, ValidationLevel.ERROR)


def _warnings(report: ValidationReport) -> list[Any]:
    return _level(report, ValidationLevel.WARNING)


def _has(items: list[Any], fragment: str) -> bool:
    return any(fragment in c.check_name or fragment in c.message for c in items)


def test_valid_bundle_passes() -> None:
    report = _run([_settings(enabled=True), *_base()])
    assert _errors(report) == []
    assert _warnings(report) == []


def test_no_resources() -> None:
    assert _run([]).results == []


# -- settings ----------------------------------------------------------------------


def test_settings_errors() -> None:
    report = _run([_settings(enabled="x", log_level="loud", update_cron="x", challenge_port=0)])
    errors = _errors(report)
    assert _has(errors, "enabled")
    assert _has(errors, "log_level")
    assert _has(errors, "challenge_port")
    assert _has(errors, "plugin manages")


def test_settings_disabled_with_certs_warns() -> None:
    assert _has(_warnings(_run([_settings(enabled=False), *_base()])), "disabled_with_certs")
    assert not _has(_warnings(_run([_settings(enabled=False)])), "disabled_with_certs")


# -- shared list checks ----------------------------------------------------------------


def test_unknown_and_server_managed_keys() -> None:
    report = _run([_account(bogus=1, id="x", key="k")])
    errors = _errors(report)
    assert _has(errors, "unknown_key_bogus")
    assert any("the box assigns it" in c.message for c in errors)
    assert len([c for c in errors if "assigns" in c.message]) == 2


def test_handle_with_dot_is_an_error() -> None:
    assert _has(_errors(_run([_account("a.b")])), "handle")


def test_duplicate_identities_are_errors() -> None:
    errors = _errors(_run([_account("a"), _account("b", display_name="a")]))
    assert _has(errors, "unique_identity")
    certs = _errors(_run([*_base(), _cert("web2")]))
    assert _has(certs, "certs_unique_identity")


def test_type_enum_range_errors_without_values() -> None:
    report = _run(
        [
            _account(ca="nope", enabled="yes"),
            _validation("v2", dns_sleep=-1),
            _cert("c2", common_name="b.example.com", renew_interval=0, key_length="rsa"),
        ]
    )
    messages = " ".join(c.message for c in _errors(report))
    assert "yes" not in messages and "nope" not in messages
    errors = _errors(report)
    for key in ("ca", "enabled", "dns_sleep", "renew_interval", "key_length"):
        assert _has(errors, key)


def test_lock_must_be_boolean() -> None:
    assert _has(_errors(_run([_account(lock="yes")])), "lock")


# -- accounts ---------------------------------------------------------------------------


def test_account_requires_email_and_ca_and_custom_ca() -> None:
    errors = _errors(_run([_res("acmeclient.accounts", "a")]))
    assert _has(errors, "email_required") and _has(errors, "ca_required")
    assert _has(_errors(_run([_account(ca="custom")])), "custom_ca_required")
    assert not _has(
        _errors(_run([_account(ca="custom", custom_ca="https://ca.example.com")])), "custom"
    )


def test_duplicate_ca_email_is_a_warning() -> None:
    report = _run([_account("a"), _account("b")])
    assert _has(_warnings(report), "duplicate_registration")
    assert _errors(report) == []


def test_eab_hmac_literal_is_a_warning_without_echo() -> None:
    report = _run([_account(eab_hmac=LITERAL)])
    assert _has(_warnings(report), "eab_hmac_literal_secret")
    assert LITERAL not in " ".join(c.message for c in report.results)


# -- validations -------------------------------------------------------------------------


def test_dns01_requires_dns_service() -> None:
    assert _has(
        _errors(_run([_res("acmeclient.validations", "v", method="dns01")])), "dns_service_required"
    )


def test_dns_foreign_provider_fields_are_an_error() -> None:
    report = _run([_validation(dns_aws_secret=SECRET)])
    errors = _errors(report)
    assert _has(errors, "dns_foreign_fields")
    assert "dns_aws_secret" in " ".join(c.message for c in errors)


def test_dns_cf_requires_token_but_unlisted_provider_only_warns() -> None:
    cf = _res("acmeclient.validations", "v", method="dns01", dns_service="dns_cf")
    assert _has(_errors(_run([cf])), "dns_cf_token_required")
    other = _res(
        "acmeclient.validations",
        "v",
        method="dns01",
        dns_service="dns_aws",
        dns_aws_secret=SECRET,
    )
    report = _run([other])
    assert _errors(report) == []
    assert _has(_warnings(report), "dns_unchecked")


def test_http01_with_dns_fields_warns() -> None:
    report = _run([_validation(method="http01")])
    assert _has(_warnings(report), "dns_fields_ignored")
    assert _errors(report) == []


def test_validation_requires_method() -> None:
    assert _has(_errors(_run([_res("acmeclient.validations", "v")])), "method_required")


def test_dns_literal_secret_is_a_warning_without_echo() -> None:
    report = _run([_validation(dns_cf_token=LITERAL)])
    assert _has(_warnings(report), "dns_cf_token_literal_secret")
    assert _errors(report) == []
    assert LITERAL not in " ".join(c.message for c in report.results)


# -- actions -----------------------------------------------------------------------------


def test_action_type_required_and_passthrough_must_fit_type() -> None:
    assert _has(_errors(_run([_res("acmeclient.actions", "a")])), "type_required")
    bad = _action(type="configd_restart_gui", sftp_host="h")
    assert _has(_errors(_run([bad])), "sftp_host_type")
    good = _action(type="configd_upload_sftp", sftp_host="h", sftp_password=SECRET)
    assert _errors(_run([good])) == []


def test_action_credential_literal_is_a_warning() -> None:
    report = _run([_action(type="configd_upload_sftp", sftp_password=LITERAL)])
    assert _has(_warnings(report), "sftp_password_literal_secret")
    assert LITERAL not in " ".join(c.message for c in report.results)


# -- certs ---------------------------------------------------------------------------------


def test_cert_required_fields() -> None:
    errors = _errors(_run([_res("acmeclient.certs", "c")]))
    for key in ("common_name_required", "account_required", "validation_required"):
        assert _has(errors, key)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("account", "missing"),
        ("account", "validations.dns"),  # wrong target type
        ("validation", "accounts.acct"),
        ("account", "other.accounts.acct"),
        ("restart_actions", ["gui", "ghost"]),
    ],
)
def test_cert_refs_must_resolve(field: str, value: Any) -> None:
    resources = [_account(), _validation(), _action(), _cert(**{field: value})]
    assert _has(_errors(_run(resources)), f"{field}_ref")


@pytest.mark.parametrize("ref", ["acct", "accounts.acct", "acmeclient.accounts.acct"])
def test_cert_ref_forms_resolve(ref: str) -> None:
    assert _errors(_run([_account(), _validation(), _cert(account=ref)])) == []
