"""Unit tests for ``infrafoundry.providers.opnsense.services._credentials``.

Coverage:
    - Gate semantics: unset / falsy values leave behavior unchanged.
    - Override precedence: env-FIRST when gate is truthy, settings fallback
      otherwise; per-field overrides honored individually.
    - Empty-string env vars treated as "unset" (fall back to settings).
    - ``OPNSENSE_VERIFY_SSL`` parsing for the project's full truthy/falsy set.
    - One-time-per-process warning behavior, including suppression and the
      ``reset_warning_state_for_tests`` test affordance.
    - Warning suppressed when override active but resolved URL matches
      settings (no endpoint redirect to flag).
"""

from __future__ import annotations

import logging

import pytest

from infrafoundry.providers.opnsense.services._credentials import (
    API_KEY_ENV_VAR,
    API_SECRET_ENV_VAR,
    API_URL_ENV_VAR,
    GATE_ENV_VAR,
    VERIFY_SSL_ENV_VAR,
    reset_warning_state_for_tests,
    resolve_credentials,
)

CREDENTIALS_LOGGER = "infrafoundry.providers.opnsense.services._credentials"


def _settings(
    *,
    api_url: str = "https://settings.example",
    api_key: str = "settings-key",
    api_secret: str = "settings-secret",
    verify_ssl: bool = True,
) -> dict[str, object]:
    """Build a representative ``provider_settings`` dict for test inputs."""
    return {
        "api_url": api_url,
        "api_key": api_key,
        "api_secret": api_secret,
        "verify_ssl": verify_ssl,
    }


@pytest.fixture(autouse=True)
def _reset_warning_state() -> None:
    """Clear the module-level warning-tracking set before every test."""
    reset_warning_state_for_tests()


@pytest.fixture(autouse=True)
def _scrub_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure no test sees inherited OPNSENSE_* / gate state from the shell.

    Tests opt back in via ``monkeypatch.setenv`` per-case.
    """
    for var in (
        GATE_ENV_VAR,
        API_URL_ENV_VAR,
        API_KEY_ENV_VAR,
        API_SECRET_ENV_VAR,
        VERIFY_SSL_ENV_VAR,
    ):
        monkeypatch.delenv(var, raising=False)


# ---------------------------------------------------------------------------
# Gate semantics: gate unset / falsy → behavior unchanged
# ---------------------------------------------------------------------------


class TestGateSemantics:
    def test_gate_unset_returns_settings_verbatim(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        # Even with OPNSENSE_API_URL set, the gate being unset means env
        # vars are not consulted.
        monkeypatch.setenv(API_URL_ENV_VAR, "https://override.example")
        with caplog.at_level(logging.WARNING, logger=CREDENTIALS_LOGGER):
            result = resolve_credentials(_settings())
        assert result == ("https://settings.example", "settings-key", "settings-secret", True)
        assert caplog.records == []

    @pytest.mark.parametrize("gate_value", ["", "0", "false", "no", "off", "FALSE", "Off"])
    def test_gate_falsy_values_leave_behavior_unchanged(
        self,
        monkeypatch: pytest.MonkeyPatch,
        gate_value: str,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        monkeypatch.setenv(GATE_ENV_VAR, gate_value)
        monkeypatch.setenv(API_URL_ENV_VAR, "https://override.example")
        with caplog.at_level(logging.WARNING, logger=CREDENTIALS_LOGGER):
            result = resolve_credentials(_settings())
        assert result == ("https://settings.example", "settings-key", "settings-secret", True)
        assert caplog.records == []

    def test_gate_set_no_overrides_returns_settings(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        # Gate active but no OPNSENSE_* env vars present — fall back to
        # settings for every field; no warning fires.
        monkeypatch.setenv(GATE_ENV_VAR, "1")
        with caplog.at_level(logging.WARNING, logger=CREDENTIALS_LOGGER):
            result = resolve_credentials(_settings())
        assert result == ("https://settings.example", "settings-key", "settings-secret", True)
        assert caplog.records == []


# ---------------------------------------------------------------------------
# Override precedence: per-field overrides honored when gate is active
# ---------------------------------------------------------------------------


class TestOverrideBehavior:
    def test_url_override_only(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        monkeypatch.setenv(GATE_ENV_VAR, "1")
        monkeypatch.setenv(API_URL_ENV_VAR, "https://mirror.example")
        with caplog.at_level(logging.WARNING, logger=CREDENTIALS_LOGGER):
            result = resolve_credentials(_settings())
        assert result == ("https://mirror.example", "settings-key", "settings-secret", True)
        # URL changed → warning fires once and names the resolved URL.
        warnings = [r for r in caplog.records if r.name == CREDENTIALS_LOGGER]
        assert len(warnings) == 1
        assert "https://mirror.example" in warnings[0].getMessage()

    def test_key_override_only(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        monkeypatch.setenv(GATE_ENV_VAR, "1")
        monkeypatch.setenv(API_KEY_ENV_VAR, "env-key")
        with caplog.at_level(logging.WARNING, logger=CREDENTIALS_LOGGER):
            result = resolve_credentials(_settings())
        assert result == ("https://settings.example", "env-key", "settings-secret", True)
        # URL unchanged → no warning.
        assert [r for r in caplog.records if r.name == CREDENTIALS_LOGGER] == []

    def test_secret_override_only(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        monkeypatch.setenv(GATE_ENV_VAR, "1")
        monkeypatch.setenv(API_SECRET_ENV_VAR, "env-secret")
        with caplog.at_level(logging.WARNING, logger=CREDENTIALS_LOGGER):
            result = resolve_credentials(_settings())
        assert result == ("https://settings.example", "settings-key", "env-secret", True)
        assert [r for r in caplog.records if r.name == CREDENTIALS_LOGGER] == []

    def test_verify_ssl_override_only(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        monkeypatch.setenv(GATE_ENV_VAR, "1")
        monkeypatch.setenv(VERIFY_SSL_ENV_VAR, "false")
        with caplog.at_level(logging.WARNING, logger=CREDENTIALS_LOGGER):
            result = resolve_credentials(_settings(verify_ssl=True))
        assert result == ("https://settings.example", "settings-key", "settings-secret", False)
        assert [r for r in caplog.records if r.name == CREDENTIALS_LOGGER] == []

    def test_all_four_overrides(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        monkeypatch.setenv(GATE_ENV_VAR, "1")
        monkeypatch.setenv(API_URL_ENV_VAR, "https://mirror.example")
        monkeypatch.setenv(API_KEY_ENV_VAR, "env-key")
        monkeypatch.setenv(API_SECRET_ENV_VAR, "env-secret")
        monkeypatch.setenv(VERIFY_SSL_ENV_VAR, "no")
        with caplog.at_level(logging.WARNING, logger=CREDENTIALS_LOGGER):
            result = resolve_credentials(_settings(verify_ssl=True))
        assert result == ("https://mirror.example", "env-key", "env-secret", False)
        warnings = [r for r in caplog.records if r.name == CREDENTIALS_LOGGER]
        assert len(warnings) == 1
        assert "https://mirror.example" in warnings[0].getMessage()


# ---------------------------------------------------------------------------
# Empty-string env vars are treated as "unset" — fall back to settings.
# ---------------------------------------------------------------------------


class TestEmptyEnvFallback:
    def test_empty_url_falls_back_to_settings(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        monkeypatch.setenv(GATE_ENV_VAR, "1")
        monkeypatch.setenv(API_URL_ENV_VAR, "")
        with caplog.at_level(logging.WARNING, logger=CREDENTIALS_LOGGER):
            result = resolve_credentials(_settings())
        assert result == ("https://settings.example", "settings-key", "settings-secret", True)
        # URL effectively unchanged → no warning.
        assert [r for r in caplog.records if r.name == CREDENTIALS_LOGGER] == []

    def test_empty_key_falls_back_to_settings(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv(GATE_ENV_VAR, "1")
        monkeypatch.setenv(API_KEY_ENV_VAR, "")
        result = resolve_credentials(_settings())
        assert result[1] == "settings-key"

    def test_empty_secret_falls_back_to_settings(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv(GATE_ENV_VAR, "1")
        monkeypatch.setenv(API_SECRET_ENV_VAR, "")
        result = resolve_credentials(_settings())
        assert result[2] == "settings-secret"

    def test_empty_verify_ssl_falls_back_to_settings(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv(GATE_ENV_VAR, "1")
        monkeypatch.setenv(VERIFY_SSL_ENV_VAR, "")
        # settings says False — empty env var must fall back to that, not flip.
        result = resolve_credentials(_settings(verify_ssl=False))
        assert result[3] is False


# ---------------------------------------------------------------------------
# OPNSENSE_VERIFY_SSL parsing: full truthy / falsy matrix per project convention
# ---------------------------------------------------------------------------


class TestVerifySSLParsing:
    @pytest.mark.parametrize("value", ["true", "1", "yes", "on", "True", "YES", "On", "anything"])
    def test_truthy_values_resolve_true(
        self,
        monkeypatch: pytest.MonkeyPatch,
        value: str,
    ) -> None:
        monkeypatch.setenv(GATE_ENV_VAR, "1")
        monkeypatch.setenv(VERIFY_SSL_ENV_VAR, value)
        # Settings says False; env var truthy must override to True.
        result = resolve_credentials(_settings(verify_ssl=False))
        assert result[3] is True

    @pytest.mark.parametrize("value", ["false", "0", "no", "off", "FALSE", "No", "OFF"])
    def test_falsy_values_resolve_false(
        self,
        monkeypatch: pytest.MonkeyPatch,
        value: str,
    ) -> None:
        monkeypatch.setenv(GATE_ENV_VAR, "1")
        monkeypatch.setenv(VERIFY_SSL_ENV_VAR, value)
        # Settings says True; env var falsy must override to False.
        result = resolve_credentials(_settings(verify_ssl=True))
        assert result[3] is False


# ---------------------------------------------------------------------------
# Warning behavior: one-time per process per resolved-URL
# ---------------------------------------------------------------------------


class TestWarningBehavior:
    def test_warning_fires_once_for_two_calls_with_same_state(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        monkeypatch.setenv(GATE_ENV_VAR, "1")
        monkeypatch.setenv(API_URL_ENV_VAR, "https://mirror.example")
        with caplog.at_level(logging.WARNING, logger=CREDENTIALS_LOGGER):
            resolve_credentials(_settings())
            resolve_credentials(_settings())
        warnings = [r for r in caplog.records if r.name == CREDENTIALS_LOGGER]
        assert len(warnings) == 1

    def test_reset_warning_state_re_arms_warning(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        monkeypatch.setenv(GATE_ENV_VAR, "1")
        monkeypatch.setenv(API_URL_ENV_VAR, "https://mirror.example")
        with caplog.at_level(logging.WARNING, logger=CREDENTIALS_LOGGER):
            resolve_credentials(_settings())
            assert len([r for r in caplog.records if r.name == CREDENTIALS_LOGGER]) == 1
            reset_warning_state_for_tests()
            resolve_credentials(_settings())
        warnings = [r for r in caplog.records if r.name == CREDENTIALS_LOGGER]
        # Two warnings total: one before reset, one after.
        assert len(warnings) == 2

    def test_no_warning_when_resolved_url_matches_settings(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        # Gate active + only OPNSENSE_API_KEY set + no URL override → the
        # resolved URL still matches settings, so no endpoint-redirect
        # warning fires.
        monkeypatch.setenv(GATE_ENV_VAR, "1")
        monkeypatch.setenv(API_KEY_ENV_VAR, "env-key")
        with caplog.at_level(logging.WARNING, logger=CREDENTIALS_LOGGER):
            resolve_credentials(_settings())
        assert [r for r in caplog.records if r.name == CREDENTIALS_LOGGER] == []

    def test_no_warning_when_url_env_matches_settings(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        # Operator sets OPNSENSE_API_URL to the same value as settings.yaml
        # (e.g., a direnv shell that re-asserts the production URL). No
        # endpoint redirect → no warning.
        monkeypatch.setenv(GATE_ENV_VAR, "1")
        monkeypatch.setenv(API_URL_ENV_VAR, "https://settings.example")
        with caplog.at_level(logging.WARNING, logger=CREDENTIALS_LOGGER):
            resolve_credentials(_settings(api_url="https://settings.example"))
        assert [r for r in caplog.records if r.name == CREDENTIALS_LOGGER] == []

    def test_distinct_urls_each_get_one_warning(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        monkeypatch.setenv(GATE_ENV_VAR, "1")
        with caplog.at_level(logging.WARNING, logger=CREDENTIALS_LOGGER):
            monkeypatch.setenv(API_URL_ENV_VAR, "https://mirror-a.example")
            resolve_credentials(_settings())
            monkeypatch.setenv(API_URL_ENV_VAR, "https://mirror-b.example")
            resolve_credentials(_settings())
            # Repeat each URL — should not re-warn.
            monkeypatch.setenv(API_URL_ENV_VAR, "https://mirror-a.example")
            resolve_credentials(_settings())
        warnings = [r for r in caplog.records if r.name == CREDENTIALS_LOGGER]
        # One warning per distinct resolved URL.
        assert len(warnings) == 2
        messages = sorted(w.getMessage() for w in warnings)
        assert "https://mirror-a.example" in messages[0]
        assert "https://mirror-b.example" in messages[1]


# ---------------------------------------------------------------------------
# Defensive: settings with missing keys
# ---------------------------------------------------------------------------


class TestDefaultsForMissingSettings:
    def test_empty_settings_dict_returns_defaults(self) -> None:
        # Gate unset; missing keys default to ("", "", "", True).
        result = resolve_credentials({})
        assert result == ("", "", "", True)

    def test_gate_set_with_empty_settings_uses_env_when_present(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv(GATE_ENV_VAR, "1")
        monkeypatch.setenv(API_URL_ENV_VAR, "https://only-from-env.example")
        monkeypatch.setenv(API_KEY_ENV_VAR, "env-only-key")
        result = resolve_credentials({})
        assert result[0] == "https://only-from-env.example"
        assert result[1] == "env-only-key"
        # api_secret unset; defaults to "" via settings fallback.
        assert result[2] == ""
        # verify_ssl unset; defaults to True via settings fallback.
        assert result[3] is True
