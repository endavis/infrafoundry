"""Offline checks for ``certificate`` resources and ``provider_settings.acme``."""

from __future__ import annotations

from typing import Any

import pytest

from infrafoundry.core.certs.models import CertificateSchemaError
from infrafoundry.core.certs.schema import (
    check_certificates,
    directory_id,
    parse_spec,
    raw_settings_problems,
    settings_from_mapping,
)

from .fakes import TOKEN, ZONE, certificate_resource, settings

pytestmark = pytest.mark.unit

GOOD_SETTINGS: dict[str, Any] = {
    "agree_tos": True,
    "cloudflare": {
        "api_token": "secret://env_secrets/acme/cloudflare_api_token",
        "zone_id": "secret://env_secrets/acme/cloudflare_zone_id",
    },
}


def messages(**kwargs: Any) -> list[str]:
    return [f.message for f in check_certificates([certificate_resource(**kwargs)])]


def test_a_valid_certificate_has_no_findings() -> None:
    assert messages() == []


@pytest.mark.parametrize(
    "names",
    [
        [],
        ["192.0.2.1"],
        ["a.*.example.com"],
        ["**.example.com"],
        ["example"],
        ["a.example.com"] * 2,
    ],
)
def test_bad_names_are_rejected(names: list[str]) -> None:
    assert any("names" in m for m in messages(names=names))


def test_more_than_100_names_are_rejected() -> None:
    names = [f"h{i}.example.com" for i in range(101)]
    assert any("1-100" in m for m in messages(names=names))


def test_key_type_and_renew_days_are_checked() -> None:
    assert any("key_type" in m for m in messages(key_type="rsa-1024"))
    assert any("renew_before_days" in m for m in messages(renew_before_days=0))
    assert messages(key_type="rsa-2048", renew_before_days=21) == []


def test_unknown_key_is_rejected() -> None:
    assert any("unknown keys" in m for m in messages(extra=1))


def test_a_certificate_outside_a_package_is_rejected() -> None:
    assert any("inside a package" in m for m in messages(package=None))


def test_server_name_is_required_when_every_name_is_a_wildcard() -> None:
    resource = certificate_resource(names=["*.example.com"])
    del resource.config["target"]["verify"]["server_name"]
    found = [f.message for f in check_certificates([resource])]
    assert any("server_name is required" in m for m in found)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("key_path", "relative.key"),
        ("key_path", "/etc/ssl/a b"),
        ("cert_mode", "rw-r--r--"),
        ("owner", "root;rm"),
        ("reload", "systemctl reload caddy"),
        ("reload", ["ok", ""]),
        ("provider", "opnsense"),
        ("sudo", "yes"),
    ],
)
def test_target_fields_are_validated(key: str, value: Any) -> None:
    resource = certificate_resource()
    resource.config["target"][key] = value
    assert check_certificates([resource])


def test_target_needs_a_certificate_path() -> None:
    resource = certificate_resource()
    del resource.config["target"]["fullchain_path"]
    assert any(
        "cert_path and/or fullchain_path" in f.message for f in check_certificates([resource])
    )


def test_duplicate_names_are_reported() -> None:
    found = check_certificates([certificate_resource(), certificate_resource()])
    assert any("declared 2 times" in f.message for f in found)


def test_parse_spec_returns_the_declaration_and_rejects_invalid_ones() -> None:
    spec = parse_spec(certificate_resource(key_type="rsa-2048"))
    assert spec.names == ("*.example.com", "example.com")
    assert spec.key_type == "rsa-2048"
    with pytest.raises(CertificateSchemaError):
        parse_spec(certificate_resource(names=[]))


def test_valid_settings_have_no_problems() -> None:
    assert raw_settings_problems(GOOD_SETTINGS) == []


@pytest.mark.parametrize(
    ("change", "fragment"),
    [
        ({"agree_tos": False}, "agree_tos"),
        ({"directory": "http://x"}, "directory"),
        ({"email": "nope"}, "email"),
        ({"renew_before_days": 99}, "renew_before_days"),
        ({"cloudflare": {"api_token": "plain", "zone_id": "secret://env_secrets/z"}}, "secret://"),
        ({"cloudflare": {"zone_id": "secret://env_secrets/z"}}, "api_token is required"),
        ({"propagation": {"timeout": 1}}, "propagation.timeout"),
        ({"doh": ["http://insecure"]}, "doh"),
        ({"extra": 1}, "unknown keys"),
    ],
)
def test_settings_problems(change: dict[str, Any], fragment: str) -> None:
    problems = raw_settings_problems({**GOOD_SETTINGS, **change})
    assert any(fragment in p for p in problems)


def test_settings_problems_never_echo_the_value() -> None:
    problems = raw_settings_problems(
        {**GOOD_SETTINGS, "cloudflare": {"api_token": TOKEN, "zone_id": ZONE}}
    )
    assert problems
    assert TOKEN not in " ".join(problems)
    assert ZONE not in " ".join(problems)


def test_missing_settings() -> None:
    assert raw_settings_problems(None) == ["provider_settings.acme is missing"]


def test_settings_from_mapping_defaults_to_staging_and_hides_secrets_from_repr() -> None:
    result = settings_from_mapping(
        {"agree_tos": True, "cloudflare": {"api_token": TOKEN, "zone_id": ZONE}}
    )
    assert result.directory.startswith("https://acme-staging-v02")
    assert result.directory_id == "staging"
    assert result.renew_before_days == 30
    assert TOKEN not in repr(result)
    assert ZONE not in repr(result)


def test_settings_from_mapping_rejects_invalid_settings() -> None:
    with pytest.raises(CertificateSchemaError, match="agree_tos"):
        settings_from_mapping({"cloudflare": {"api_token": "t", "zone_id": "z"}})


def test_directory_id_is_stable_for_custom_urls() -> None:
    assert directory_id("production") == "production"
    assert directory_id("https://ca.example.test/dir") == directory_id(
        "https://ca.example.test/dir"
    )
    assert directory_id("https://ca.example.test/dir").startswith("custom-")
    assert settings().directory_id == "staging"


def test_doh_is_off_by_default() -> None:
    from infrafoundry.core.certs.schema import settings_from_mapping

    resolved = {
        "agree_tos": True,
        "cloudflare": {"api_token": "tok", "zone_id": "zone"},
    }
    assert settings_from_mapping(resolved).doh_urls == ()


def test_a_proxmox_node_target_is_valid_without_file_keys() -> None:
    resource = certificate_resource(names=["pve1.example.com"])
    resource.config["target"] = {"provider": "proxmox", "kind": "node", "resource": "pve1"}
    assert check_certificates([resource]) == []


def test_a_proxmox_node_target_rejects_a_key_path() -> None:
    resource = certificate_resource(names=["pve1.example.com"])
    resource.config["target"] = {
        "provider": "proxmox",
        "kind": "node",
        "resource": "pve1",
        "key_path": "/etc/ssl/a.key",
    }
    assert any("do not apply" in f.message for f in check_certificates([resource]))
