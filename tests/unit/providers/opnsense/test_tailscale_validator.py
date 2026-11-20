"""Unit tests for ``TailscaleValidator`` (#787)."""

from __future__ import annotations

from typing import Any

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.opnsense.validators import TailscaleValidator
from infrafoundry.providers.opnsense.validators.context import OPNsenseValidationContext

URI = "secret://env_secrets/opnsense/tailscale/auth/pre_auth_key"
SENTINEL = "tskey-auth-SENTINEL-0001"


def _errors(*resources: ResourceConfig) -> list[str]:
    report = ValidationReport()
    TailscaleValidator(report).validate(OPNsenseValidationContext(resources=list(resources)))
    return [r.message for r in report.results if r.level == ValidationLevel.ERROR]


def _settings(**config: Any) -> ResourceConfig:
    return ResourceConfig(
        name="tailscale.settings", type="tailscale.settings", provider="opnsense", config=config
    )


def _auth(**config: Any) -> ResourceConfig:
    return ResourceConfig(
        name="tailscale.auth", type="tailscale.auth", provider="opnsense", config=config
    )


def _subnet(name: str, /, **config: Any) -> ResourceConfig:
    return ResourceConfig(name=name, type="tailscale.subnets", provider="opnsense", config=config)


def test_valid_resources_have_no_errors() -> None:
    assert (
        _errors(
            _settings(enabled=False, listen_port=0, enable_snat=True, use_exit_node=""),
            _auth(login_server="https://c.example.com", pre_auth_key=URI, update_pre_auth_key=True),
            _subnet("a", name="a", subnet="192.0.2.0/24", description="d", lock=False),
            _subnet("b", subnet="2001:db8::/64"),
        )
        == []
    )


def test_settings_unknown_and_refused_keys() -> None:
    errors = _errors(_settings(subnets=[], disable_snat=True, hostname="x", exit_node="y", zz=1))
    assert len(errors) == 5
    assert any("tailscale.subnets" in e for e in errors)
    assert any("enable_snat" in e for e in errors)


def test_settings_bad_types_and_ranges() -> None:
    errors = _errors(_settings(enabled="yes", listen_port=70000, login_timeout=-1, use_exit_node=1))
    assert len(errors) == 4


def test_auth_literal_key_is_error_without_the_value() -> None:
    errors = _errors(_auth(pre_auth_key=SENTINEL))
    assert len(errors) == 1
    assert "secret://" in errors[0]
    assert SENTINEL not in errors[0]


def test_auth_flag_rules() -> None:
    assert len(_errors(_auth(update_pre_auth_key=True))) == 1
    assert len(_errors(_auth(update_pre_auth_key="yes", pre_auth_key=URI))) == 1


def test_auth_login_server_and_unknown_key() -> None:
    assert len(_errors(_auth(login_server="ftp://x"))) == 1
    assert len(_errors(_auth(login_server=3))) == 1
    assert len(_errors(_auth(api_key_ref="x"))) == 1


def test_subnet_errors() -> None:
    assert len(_errors(_subnet("a"))) == 1
    assert len(_errors(_subnet("a", subnet="not-a-cidr"))) == 1
    assert len(_errors(_subnet("a", subnet="192.0.2.1/24"))) == 1
    assert len(_errors(_subnet("a", subnet="192.0.2.0/24", description=3))) == 1
    assert len(_errors(_subnet("a", subnet="192.0.2.0/24", lock="x"))) == 1
    uuid_errors = _errors(_subnet("a", subnet="192.0.2.0/24", uuid="u"))
    assert len(uuid_errors) == 1
    assert "box assigns" in uuid_errors[0]


def test_duplicate_normalized_cidrs() -> None:
    assert (
        len(_errors(_subnet("a", subnet="192.0.2.0/24"), _subnet("b", subnet="192.0.2.0/24"))) == 1
    )
    assert (
        len(_errors(_subnet("a", subnet="2001:DB8::/64"), _subnet("b", subnet="2001:db8::/64")))
        == 1
    )


CID = "secret://env_secrets/opnsense/tailscale/auth/oauth_client_id"
CSEC = "secret://env_secrets/opnsense/tailscale/auth/oauth_client_secret"
FAKE_SECRET = "tskey-client-FAKE-0003"


def _mint(**overrides: Any) -> dict[str, Any]:
    block: dict[str, Any] = {
        "oauth_client_id": CID,
        "oauth_client_secret": CSEC,
        "tags": ["tag:example"],
    }
    block.update(overrides)
    return block


def _warnings(*resources: ResourceConfig) -> list[str]:
    report = ValidationReport()
    TailscaleValidator(report).validate(OPNsenseValidationContext(resources=list(resources)))
    return [r.message for r in report.results if r.level == ValidationLevel.WARNING]


def test_mint_valid_has_no_errors_or_warnings() -> None:
    resource = _auth(
        login_server="https://controlplane.tailscale.com",
        mint=_mint(ephemeral=True, preauthorized=False, expiry_seconds=600),
    )
    assert _errors(resource) == []
    assert _warnings(resource) == []


def test_mint_excludes_pre_auth_key_and_update_flag() -> None:
    assert len(_errors(_auth(mint=_mint(), pre_auth_key=URI))) == 1
    assert len(_errors(_auth(mint=_mint(), update_pre_auth_key=True))) == 1


def test_mint_literal_credentials_are_errors_without_the_value() -> None:
    errors = _errors(
        _auth(mint=_mint(oauth_client_secret=FAKE_SECRET, oauth_client_id="literal-id"))
    )
    assert len(errors) == 2
    assert not any(FAKE_SECRET in e or "literal-id" in e for e in errors)


@pytest.mark.parametrize(
    "overrides",
    [
        {"tags": []},
        {"tags": "tag:example"},
        {"tags": ["example"]},
        {"tags": [3]},
        {"ephemeral": "yes"},
        {"preauthorized": 1},
        {"expiry_seconds": 0},
        {"expiry_seconds": 7776001},
        {"expiry_seconds": "60"},
        {"expiry_seconds": True},
        {"bogus": 1},
        {"oauth_client_id": ""},
    ],
)
def test_mint_field_rules(overrides: dict[str, Any]) -> None:
    assert len(_errors(_auth(mint=_mint(**overrides)))) == 1


def test_mint_missing_tags_and_non_mapping() -> None:
    block = _mint()
    del block["tags"]
    assert len(_errors(_auth(mint=block))) == 1
    assert len(_errors(_auth(mint="nope"))) == 1


def test_mint_expiry_bounds_accepted() -> None:
    assert _errors(_auth(mint=_mint(expiry_seconds=1))) == []
    assert _errors(_auth(mint=_mint(expiry_seconds=7776000))) == []


def test_mint_with_foreign_login_server_warns() -> None:
    resource = _auth(login_server="https://hs.example.com", mint=_mint())
    assert _errors(resource) == []
    assert len(_warnings(resource)) == 1
