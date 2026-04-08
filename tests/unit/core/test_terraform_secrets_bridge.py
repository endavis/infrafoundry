"""Integration tests for the secrets→TF_VAR_* bridge.

Phase 1 of issue #212. Verifies the end-to-end flow:

    EnvironmentConfig(secrets=...) + ResourceConfig(terraform_secrets=...)
        --[build_terraform_env_vars]-->
            {"TF_VAR_<sanitized>": "<plaintext>"}

The validator path is also covered: a resource that references an
unknown dotted secret key must produce a clear validation error rather
than silently returning an empty value at terraform invocation time.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from infrafoundry.core.config.models import EnvironmentConfig
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.provider_mixins import (
    TerraformGeneratorMixin,
    sanitize_secret_ref_to_tf_var,
)
from infrafoundry.core.validation import ValidationReport
from infrafoundry.core.validation_helpers import validate_terraform_secrets_references

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _BridgeHarness(TerraformGeneratorMixin):
    """Minimal mixin host that lets us call ``build_terraform_env_vars``.

    The mixin's only env-config dependency is its ``_load_environment_config``
    helper, which we override to inject a synthetic env. That keeps the test
    free of filesystem and SOPS dependencies.
    """

    name = "test"

    def __init__(self, env_config: EnvironmentConfig | None) -> None:
        self.config_dir = Path("/nonexistent")
        self.terraform_dir = Path("/nonexistent/terraform")
        self._env_config = env_config

    def _load_environment_config(self) -> EnvironmentConfig | None:  # type: ignore[override]
        return self._env_config

    def _write_terraform_file(self, filename: str, content: str) -> None:  # pragma: no cover
        raise AssertionError("Should not be called in these tests")


def _make_env(
    *, secrets: dict | None = None, provider_settings: dict | None = None
) -> EnvironmentConfig:
    """Build a minimal EnvironmentConfig with optional secrets/settings."""
    return EnvironmentConfig(
        name="test",
        provider_settings=provider_settings or {},
        secrets=secrets,
    )


def _resource(name: str, terraform_secrets: list[str] | None = None) -> ResourceConfig:
    config: dict = {}
    if terraform_secrets is not None:
        config["terraform_secrets"] = terraform_secrets
    return ResourceConfig(name=name, type="instance", provider="test", config=config)


# ---------------------------------------------------------------------------
# sanitize_secret_ref_to_tf_var
# ---------------------------------------------------------------------------


class TestSanitization:
    """Sanitization rules for dotted secret refs → TF variable names."""

    def test_basic(self):
        assert (
            sanitize_secret_ref_to_tf_var("tailscale.oauth_client_secret")
            == "tailscale_oauth_client_secret"
        )

    def test_lowercases(self):
        assert sanitize_secret_ref_to_tf_var("Tailscale.OAuthSecret") == "tailscale_oauthsecret"

    def test_deeply_nested(self):
        assert sanitize_secret_ref_to_tf_var("a.b.c.d") == "a_b_c_d"

    def test_rejects_leading_digit(self):
        with pytest.raises(ValueError, match="not a valid Terraform variable name"):
            sanitize_secret_ref_to_tf_var("1bad.key")

    def test_rejects_special_chars(self):
        with pytest.raises(ValueError, match="not a valid Terraform variable name"):
            sanitize_secret_ref_to_tf_var("bad-key.x")


# ---------------------------------------------------------------------------
# build_terraform_env_vars resource secrets path
# ---------------------------------------------------------------------------


class TestBuildTerraformEnvVarsSecrets:
    """Resource ``terraform_secrets`` are resolved into ``TF_VAR_*`` entries."""

    def test_no_resources_no_secret_vars(self):
        env = _make_env(secrets={"tailscale": {"oauth_client_secret": "abc"}})
        harness = _BridgeHarness(env)

        result = harness.build_terraform_env_vars(provider_name="test", mapping={}, resources=None)
        assert result == {}

    def test_resource_without_terraform_secrets_emits_nothing(self):
        env = _make_env(secrets={"tailscale": {"oauth_client_secret": "abc"}})
        harness = _BridgeHarness(env)

        result = harness.build_terraform_env_vars(
            provider_name="test",
            mapping={},
            resources=[_resource("vm-1")],
        )
        assert result == {}

    def test_single_secret_reference_emits_tf_var(self):
        env = _make_env(secrets={"tailscale": {"oauth_client_secret": "abc-secret"}})
        harness = _BridgeHarness(env)

        result = harness.build_terraform_env_vars(
            provider_name="test",
            mapping={},
            resources=[_resource("vm-1", terraform_secrets=["tailscale.oauth_client_secret"])],
        )
        assert result == {"TF_VAR_tailscale_oauth_client_secret": "abc-secret"}

    def test_multiple_resources_dedupe_secret_refs(self):
        env = _make_env(
            secrets={
                "tailscale": {
                    "oauth_client_id": "id-value",
                    "oauth_client_secret": "secret-value",
                }
            }
        )
        harness = _BridgeHarness(env)

        result = harness.build_terraform_env_vars(
            provider_name="test",
            mapping={},
            resources=[
                _resource(
                    "vm-1",
                    terraform_secrets=[
                        "tailscale.oauth_client_id",
                        "tailscale.oauth_client_secret",
                    ],
                ),
                _resource(
                    "vm-2",
                    terraform_secrets=[
                        "tailscale.oauth_client_id",  # duplicate
                    ],
                ),
            ],
        )
        assert result == {
            "TF_VAR_tailscale_oauth_client_id": "id-value",
            "TF_VAR_tailscale_oauth_client_secret": "secret-value",
        }

    def test_unknown_secret_raises_keyerror(self):
        env = _make_env(secrets={"tailscale": {"oauth_client_id": "id"}})
        harness = _BridgeHarness(env)

        with pytest.raises(KeyError, match=r"tailscale\.oauth_client_secret"):
            harness.build_terraform_env_vars(
                provider_name="test",
                mapping={},
                resources=[_resource("vm-1", terraform_secrets=["tailscale.oauth_client_secret"])],
            )

    def test_secret_ref_with_no_secrets_loaded_raises(self):
        env = _make_env(secrets=None)
        harness = _BridgeHarness(env)

        with pytest.raises(KeyError, match=r"tailscale\.oauth_client_secret"):
            harness.build_terraform_env_vars(
                provider_name="test",
                mapping={},
                resources=[_resource("vm-1", terraform_secrets=["tailscale.oauth_client_secret"])],
            )

    def test_provider_settings_and_secrets_coexist(self):
        env = _make_env(
            provider_settings={"test": {"api_url": "https://api.example.com"}},
            secrets={"tailscale": {"auth_key": "tskey-xyz"}},
        )
        harness = _BridgeHarness(env)

        result = harness.build_terraform_env_vars(
            provider_name="test",
            mapping={"api_url": "test_api_url"},
            resources=[_resource("vm-1", terraform_secrets=["tailscale.auth_key"])],
        )
        assert result == {
            "TF_VAR_test_api_url": "https://api.example.com",
            "TF_VAR_tailscale_auth_key": "tskey-xyz",
        }

    def test_collect_terraform_secret_refs_rejects_non_list(self):
        bad = ResourceConfig(
            name="vm-1",
            type="instance",
            provider="test",
            config={"terraform_secrets": "not-a-list"},
        )
        with pytest.raises(TypeError, match="non-list"):
            TerraformGeneratorMixin.collect_terraform_secret_refs([bad])

    def test_collect_terraform_secret_refs_rejects_non_string_entries(self):
        bad = ResourceConfig(
            name="vm-1",
            type="instance",
            provider="test",
            config={"terraform_secrets": ["ok.path", 42]},
        )
        with pytest.raises(TypeError, match="non-string"):
            TerraformGeneratorMixin.collect_terraform_secret_refs([bad])


# ---------------------------------------------------------------------------
# validate_terraform_secrets_references
# ---------------------------------------------------------------------------


class TestTerraformSecretsValidator:
    """Validator surfaces missing/invalid refs as ValidationReport entries."""

    def test_resource_without_terraform_secrets_is_skipped(self):
        env = _make_env(secrets={"tailscale": {"auth_key": "x"}})
        report = ValidationReport()

        validate_terraform_secrets_references("test", [_resource("vm-1")], env, report)

        # No checks should have been added.
        assert all("terraform_secrets" not in c.check_name for c in report.results)

    def test_valid_reference_passes(self):
        env = _make_env(secrets={"tailscale": {"oauth_client_secret": "abc"}})
        report = ValidationReport()

        validate_terraform_secrets_references(
            "test",
            [_resource("vm-1", terraform_secrets=["tailscale.oauth_client_secret"])],
            env,
            report,
        )

        matching = [c for c in report.results if "terraform_secrets" in c.check_name]
        assert len(matching) == 1
        assert matching[0].passed is True

    def test_missing_reference_fails(self):
        env = _make_env(secrets={"tailscale": {"oauth_client_id": "id"}})
        report = ValidationReport()

        validate_terraform_secrets_references(
            "test",
            [_resource("vm-1", terraform_secrets=["tailscale.oauth_client_secret"])],
            env,
            report,
        )

        matching = [c for c in report.results if "terraform_secrets" in c.check_name]
        assert len(matching) == 1
        assert matching[0].passed is False
        assert "tailscale.oauth_client_secret" in matching[0].message

    def test_non_list_terraform_secrets_fails(self):
        env = _make_env(secrets={"tailscale": {"auth_key": "x"}})
        report = ValidationReport()
        bad = ResourceConfig(
            name="vm-1",
            type="instance",
            provider="test",
            config={"terraform_secrets": "tailscale.auth_key"},  # string, not list
        )

        validate_terraform_secrets_references("test", [bad], env, report)

        matching = [c for c in report.results if "terraform_secrets" in c.check_name]
        assert len(matching) == 1
        assert matching[0].passed is False
        assert "non-list" in matching[0].message

    def test_non_string_entry_fails(self):
        env = _make_env(secrets={"tailscale": {"auth_key": "x"}})
        report = ValidationReport()
        bad = ResourceConfig(
            name="vm-1",
            type="instance",
            provider="test",
            config={"terraform_secrets": ["tailscale.auth_key", 99]},
        )

        validate_terraform_secrets_references("test", [bad], env, report)

        matching = [c for c in report.results if "terraform_secrets" in c.check_name]
        assert len(matching) == 1
        assert matching[0].passed is False
        assert "non-string" in matching[0].message
