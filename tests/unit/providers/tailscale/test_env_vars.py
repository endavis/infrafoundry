"""Tests for TF_VAR_* construction and secret handling."""

import logging

import pytest

from infrafoundry.providers.tailscale import TailscaleProvider

from .conftest import (
    API_KEY_VALUE,
    OAUTH_SECRETS,
    OAUTH_URIS,
    SECRET_ID,
    SECRET_VALUE,
    make_env,
)


def _use(provider: TailscaleProvider, monkeypatch: pytest.MonkeyPatch, env: object) -> None:
    monkeypatch.setattr(provider, "_load_environment_config", lambda: env)


def test_oauth_uris_resolved_into_tf_vars(
    provider: TailscaleProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use(provider, monkeypatch, make_env(OAUTH_URIS, OAUTH_SECRETS))
    assert provider.get_terraform_env_vars() == {
        "TF_VAR_tailscale_oauth_client_id": SECRET_ID,
        "TF_VAR_tailscale_oauth_client_secret": SECRET_VALUE,
        "TF_VAR_tailscale_tailnet": "-",
    }


def test_scopes_become_json_list_and_unset_keys_absent(
    provider: TailscaleProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use(
        provider,
        monkeypatch,
        make_env({**OAUTH_URIS, "scopes": ["policy_file", "dns"]}, OAUTH_SECRETS),
    )
    result = provider.get_terraform_env_vars()
    assert result["TF_VAR_tailscale_scopes"] == '["policy_file", "dns"]'
    assert "TF_VAR_tailscale_api_key" not in result
    assert "TF_VAR_tailscale_base_url" not in result


def test_api_key_alternative(provider: TailscaleProvider, monkeypatch: pytest.MonkeyPatch) -> None:
    _use(
        provider,
        monkeypatch,
        make_env(
            {"api_key": "secret://env_secrets/tailscale/api_key"},
            {"tailscale": {"api_key": API_KEY_VALUE}},
        ),
    )
    assert provider.get_terraform_env_vars() == {"TF_VAR_tailscale_api_key": API_KEY_VALUE}


def test_no_environment_gives_empty(
    provider: TailscaleProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use(provider, monkeypatch, None)
    assert provider.get_terraform_env_vars() == {}


def test_env_override_wins_when_gated(
    provider: TailscaleProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("INFRAFOUNDRY_ALLOW_ENV_OVERRIDE", "1")
    monkeypatch.setenv("TAILSCALE_OAUTH_CLIENT_ID", "override-id-870")
    _use(provider, monkeypatch, make_env(OAUTH_URIS, OAUTH_SECRETS))
    result = provider.get_terraform_env_vars()
    assert result["TF_VAR_tailscale_oauth_client_id"] == "override-id-870"
    assert result["TF_VAR_tailscale_oauth_client_secret"] == SECRET_VALUE


def test_override_ignored_without_gate(
    provider: TailscaleProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TAILSCALE_OAUTH_CLIENT_ID", "override-id-870")
    _use(provider, monkeypatch, make_env(OAUTH_URIS, OAUTH_SECRETS))
    assert provider.get_terraform_env_vars()["TF_VAR_tailscale_oauth_client_id"] == SECRET_ID


def test_unresolvable_uri_error_names_uri_not_value(
    provider: TailscaleProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    from infrafoundry.secrets.resolver import SecretResolutionError

    _use(provider, monkeypatch, make_env(OAUTH_URIS, {"tailscale": {"oauth_client_id": SECRET_ID}}))
    with pytest.raises(SecretResolutionError) as excinfo:
        provider.get_terraform_env_vars()
    assert SECRET_ID not in str(excinfo.value)
    assert SECRET_VALUE not in str(excinfo.value)


def test_debug_logs_hold_no_secret(
    provider: TailscaleProvider,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    _use(provider, monkeypatch, make_env(OAUTH_URIS, OAUTH_SECRETS))
    provider.get_terraform_env_vars()
    provider.generate_terraform([])
    assert SECRET_ID not in caplog.text
    assert SECRET_VALUE not in caplog.text
