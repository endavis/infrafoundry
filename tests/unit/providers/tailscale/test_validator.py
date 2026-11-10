"""Tests for TailscaleValidator and auth-mode detection."""

import pytest

from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.tailscale import TailscaleProvider
from infrafoundry.providers.tailscale.validator import TailscaleValidator, detect_auth_mode

from .conftest import OAUTH_URIS, make_env, res


class TestDetectAuthMode:
    def test_oauth_from_settings(self) -> None:
        assert detect_auth_mode({"oauth_client_id": "x"}, {}) == "oauth"

    def test_oauth_from_environment(self) -> None:
        assert detect_auth_mode({}, {"TAILSCALE_OAUTH_CLIENT_ID": "x"}) == "oauth"

    def test_oauth_wins_over_api_key_env(self) -> None:
        assert detect_auth_mode({"oauth_client_id": "x"}, {"TAILSCALE_API_KEY": "k"}) == "oauth"

    def test_api_key(self) -> None:
        assert detect_auth_mode({"api_key": "k"}, {}) == "api_key"
        assert detect_auth_mode({}, {"TAILSCALE_API_KEY": "k"}) == "api_key"

    def test_unset(self) -> None:
        assert detect_auth_mode({}, {}) == "unset"

    def test_defaults_to_process_environment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TAILSCALE_API_KEY", "k")
        assert detect_auth_mode({}) == "api_key"


def test_connectivity_makes_config_checks_only() -> None:
    report = ValidationReport()
    TailscaleValidator(make_env(OAUTH_URIS), report).validate_connectivity()
    assert not report.has_errors()
    assert any(r.check_name == "tailscale_credentials" for r in report.results)


def test_connectivity_warns_without_credentials() -> None:
    report = ValidationReport()
    TailscaleValidator(make_env(), report).validate_connectivity()
    assert report.has_warnings()
    assert not report.has_errors()


def test_references_use_oauth_mode_from_settings() -> None:
    report = ValidationReport()
    TailscaleValidator(make_env(OAUTH_URIS), report).validate_references([res("k", "tailnet_key")])
    assert [r.check_name for r in report.results if not r.passed] == ["tailscale_key_tags_k"]


def test_references_warn_for_tag_missing_from_policy() -> None:
    report = ValidationReport()
    TailscaleValidator(make_env(OAUTH_URIS), report).validate_references(
        [
            res("a", "acl", policy={"tagOwners": {}}),
            res("k", "tailnet_key", tags=["tag:server"]),
        ]
    )
    levels = {r.check_name: r.level for r in report.results if not r.passed}
    assert levels == {"tailscale_tag_owners_k": ValidationLevel.WARNING}


def test_provider_delegates(provider: TailscaleProvider) -> None:
    env = make_env(OAUTH_URIS)
    report = ValidationReport()
    provider.validate_connectivity(env, report)
    provider.validate_references([res("k", "tailnet_key")], env, report)
    assert report.has_errors()
