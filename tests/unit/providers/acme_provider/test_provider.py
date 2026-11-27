"""The ACME provider: types, empty Terraform, and offline validation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from infrafoundry.core.config.models import EnvironmentConfig
from infrafoundry.core.protocols import InstallsCertificate, ValidatesOffline
from infrafoundry.core.validation import ValidationReport
from infrafoundry.providers.acme import AcmeProvider, register
from infrafoundry.providers.host import HostProvider
from tests.unit.core.certs.fakes import TOKEN, certificate_resource

pytestmark = pytest.mark.unit

TOKEN_REF = "secret://env_secrets/acme/cloudflare_api_token"
ZONE_REF = "secret://env_secrets/acme/cloudflare_zone_id"


def make_env(settings: dict[str, Any] | None = None, secrets: dict[str, Any] | None = None) -> Any:
    return EnvironmentConfig(
        name="test",
        provider_settings={"acme": settings} if settings is not None else {},
        secrets={"acme": {"cloudflare_api_token": TOKEN, "cloudflare_zone_id": "z"}}
        if secrets is None
        else secrets,
    )


GOOD = {"agree_tos": True, "cloudflare": {"api_token": TOKEN_REF, "zone_id": ZONE_REF}}


@pytest.fixture
def provider(tmp_path: Path) -> AcmeProvider:
    p = AcmeProvider(tmp_path / "envs", tmp_path / "output")
    p.set_environment("test")
    return p


def offline(provider: AcmeProvider, resources: list[Any], env: Any) -> ValidationReport:
    report = ValidationReport()
    provider.validate_offline(resources, resources, env, report)
    return report


def test_types_dependencies_and_terraform_map(provider: AcmeProvider) -> None:
    assert provider.get_resource_types() == ["certificate"]
    assert provider.get_dependencies() == {"certificate": []}
    assert provider.get_terraform_resource_types() == {"certificate": ["certificate"]}
    assert provider.validate_config({"names": []})


def test_generate_terraform_writes_only_an_empty_block(provider: AcmeProvider) -> None:
    provider.generate_terraform([certificate_resource()])
    assert [p.name for p in provider.terraform_dir.iterdir()] == ["main.tf"]
    content = (provider.terraform_dir / "main.tf").read_text()
    assert "terraform {}" in content
    assert "resource" not in content.replace("not by Terraform", "")


def test_generate_ansible_only_creates_directories(provider: AcmeProvider) -> None:
    provider.generate_ansible([certificate_resource()])
    assert list(provider.ansible_dir.iterdir()) == []


def test_it_opts_into_offline_validation_and_the_host_into_installs(
    provider: AcmeProvider, tmp_path: Path
) -> None:
    assert isinstance(provider, ValidatesOffline)
    assert isinstance(HostProvider(tmp_path / "envs", tmp_path / "out"), InstallsCertificate)
    assert not isinstance(provider, InstallsCertificate)


def test_a_valid_declaration_and_settings_pass(provider: AcmeProvider) -> None:
    report = offline(provider, [certificate_resource()], make_env(GOOD))
    assert not report.has_errors()


def test_schema_errors_are_reported_per_resource(provider: AcmeProvider) -> None:
    report = offline(provider, [certificate_resource(names=["192.0.2.1"])], make_env(GOOD))
    assert report.has_errors()
    assert any("acme_schema_proxy-cert" in r.check_name for r in report.results)


def test_missing_settings_are_an_error_when_a_certificate_is_declared(
    provider: AcmeProvider,
) -> None:
    report = offline(provider, [certificate_resource()], make_env())
    assert report.has_errors()
    assert any("provider_settings.acme is missing" in r.message for r in report.results)


def test_no_certificates_means_no_settings_check(provider: AcmeProvider) -> None:
    assert not offline(provider, [], make_env()).has_errors()


def test_plain_text_credentials_are_refused_without_echoing_them(provider: AcmeProvider) -> None:
    settings = {"agree_tos": True, "cloudflare": {"api_token": TOKEN, "zone_id": ZONE_REF}}
    report = offline(provider, [certificate_resource()], make_env(settings))
    assert report.has_errors()
    assert TOKEN not in " ".join(r.message for r in report.results)


def test_an_unresolvable_secret_reference_is_reported(provider: AcmeProvider) -> None:
    report = offline(provider, [certificate_resource()], make_env(GOOD, secrets={}))
    messages = " ".join(r.message for r in report.results)
    assert "cloudflare.api_token" in messages
    assert "not present" in messages


def test_the_references_can_point_at_an_existing_secret_path(provider: AcmeProvider) -> None:
    settings = {
        "agree_tos": True,
        "cloudflare": {
            "api_token": "secret://env_secrets/opnsense/dns_token",
            "zone_id": "secret://env_secrets/opnsense/dns_zone",
        },
    }
    env = make_env(settings, secrets={"opnsense": {"dns_token": "t", "dns_zone": "z"}})
    assert not offline(provider, [certificate_resource()], env).has_errors()


def test_validate_references_and_connectivity_use_the_same_checks(provider: AcmeProvider) -> None:
    for call in ("validate_references", "validate_connectivity"):
        report = ValidationReport()
        if call == "validate_references":
            provider.validate_references([certificate_resource()], make_env(), report)
        else:
            provider.validate_connectivity(make_env(), report)
        assert report.has_errors()


def test_register_describes_the_provider() -> None:
    meta = register()
    assert (meta.name, meta.provider_class, meta.resource_types) == (
        "acme",
        AcmeProvider,
        ["certificate"],
    )
