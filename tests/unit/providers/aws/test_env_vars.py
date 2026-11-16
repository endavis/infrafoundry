"""Tests for TF_VAR_* construction."""

import pytest

from infrafoundry.providers.aws import AWSProvider

from .conftest import instance, make_env


def _use(provider: AWSProvider, monkeypatch: pytest.MonkeyPatch, env: object) -> None:
    monkeypatch.setattr(provider, "_load_environment_config", lambda: env)


def test_region_and_profile_only(provider: AWSProvider, monkeypatch: pytest.MonkeyPatch) -> None:
    _use(
        provider,
        monkeypatch,
        make_env({"region": "us-east-1", "profile": "dev", "access_key": "nope"}),
    )
    assert provider.get_terraform_env_vars() == {
        "TF_VAR_aws_region": "us-east-1",
        "TF_VAR_aws_profile": "dev",
    }


def test_unset_settings_give_nothing(
    provider: AWSProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use(provider, monkeypatch, make_env({}))
    assert provider.get_terraform_env_vars() == {}


def test_gated_env_override(provider: AWSProvider, monkeypatch: pytest.MonkeyPatch) -> None:
    _use(provider, monkeypatch, make_env({"region": "us-east-1"}))
    monkeypatch.setenv("INFRAFOUNDRY_ALLOW_ENV_OVERRIDE", "1")
    monkeypatch.setenv("AWS_REGION", "us-west-2")
    monkeypatch.setenv("AWS_PROFILE", "other")
    assert provider.get_terraform_env_vars() == {
        "TF_VAR_aws_region": "us-west-2",
        "TF_VAR_aws_profile": "other",
    }


def test_env_override_ignored_without_gate(
    provider: AWSProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use(provider, monkeypatch, make_env({"region": "us-east-1"}))
    monkeypatch.setenv("AWS_REGION", "us-west-2")
    assert provider.get_terraform_env_vars() == {"TF_VAR_aws_region": "us-east-1"}


def test_tailscale_secrets_resolve_to_tf_vars(
    provider: AWSProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use(
        provider,
        monkeypatch,
        make_env({"region": "us-east-1"}, {"tailscale": {"auth_key": "sentinel-key"}}),
    )
    provider.generate_terraform(
        [
            instance(
                "app",
                tailscale={"hostname": "app", "auth": {"auth_key_secret": "tailscale.auth_key"}},
            )
        ]
    )
    assert provider.get_terraform_env_vars()["TF_VAR_tailscale_auth_key"] == "sentinel-key"
