"""ONTAP provider settings: offline checks, trust modes, paths and loading."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from infrafoundry.providers.ontap import settings as ontap_settings
from infrafoundry.providers.ontap.settings import (
    DEFAULT_SPEC_DIR,
    OntapSettings,
    OntapSettingsError,
    load_settings,
    settings_from_mapping,
    settings_problems,
    spec_file_for,
)

from .conftest import RAW_SETTINGS

pytestmark = pytest.mark.unit

RESOLVED: dict[str, Any] = {**RAW_SETTINGS, "username": "user-example", "password": "pw-example"}


def _problems(**changes: Any) -> list[str]:
    raw = {**RAW_SETTINGS, **changes}
    return settings_problems({k: v for k, v in raw.items() if v is not None})


def test_valid_settings_have_no_problems() -> None:
    assert settings_problems(dict(RAW_SETTINGS)) == []


@pytest.mark.parametrize("key", ["username", "password"])
def test_plaintext_credential_is_rejected_without_echoing_it(key: str) -> None:
    problems = _problems(**{key: "plain-value-example"})
    assert any(key in p and "secret://" in p for p in problems)
    assert "plain-value-example" not in " ".join(problems)


def test_missing_keys_are_named() -> None:
    problems = settings_problems({"tls_fingerprint": RAW_SETTINGS["tls_fingerprint"]})
    assert "host" in problems[0] and "username" in problems[0] and "password" in problems[0]


def test_unknown_key_is_named() -> None:
    assert any("verify_tls" in p for p in _problems(verify_tls=True))


@pytest.mark.parametrize("host", ["https://cluster1.example.com", "cluster1.example.com/api"])
def test_host_must_not_carry_a_scheme_or_path(host: str) -> None:
    assert any("host" in p for p in _problems(host=host))


def test_trust_is_required_and_the_opt_out_is_explicit() -> None:
    assert any("tls_fingerprint" in p for p in _problems(tls_fingerprint=None))
    assert _problems(tls_fingerprint=None, verify_ssl=False) == []
    assert _problems(tls_fingerprint=None, verify_ssl=True) == []
    assert _problems(tls_fingerprint=None, ca_bundle="certs/ca.pem") == []


def test_bad_pin_is_rejected() -> None:
    assert any("SHA-256" in p for p in _problems(tls_fingerprint="abc"))


def test_ca_bundle_with_verify_false_is_rejected() -> None:
    problems = _problems(tls_fingerprint=None, ca_bundle="ca.pem", verify_ssl=False)
    assert any("ca_bundle" in p and "verify_ssl" in p for p in problems)


@pytest.mark.parametrize("extra", [{"ca_bundle": "ca.pem"}, {"verify_ssl": True}])
def test_pin_with_chain_validation_is_rejected(extra: dict[str, Any]) -> None:
    assert any("tls_fingerprint cannot be combined" in p for p in _problems(**extra))


def test_verify_ssl_must_be_bool() -> None:
    assert any("verify_ssl" in p for p in _problems(verify_ssl="no"))


@pytest.mark.parametrize("bad", [0, 601, True, "10"])
def test_timeout_is_checked(bad: Any) -> None:
    assert any("timeout" in p for p in _problems(timeout=bad))


def test_defaults_and_pin_normalization() -> None:
    settings = settings_from_mapping(RESOLVED)
    assert settings.fingerprint == "ab" * 32
    assert settings.timeout == 30
    assert settings.api_spec_dir == Path(DEFAULT_SPEC_DIR).expanduser()
    assert not settings.unverified
    assert settings.spec_file == settings.api_spec_dir / "ontap" / "all.json"


def test_opt_out_is_recorded() -> None:
    raw = {k: v for k, v in RESOLVED.items() if k != "tls_fingerprint"}
    assert settings_from_mapping({**raw, "verify_ssl": False}).unverified
    assert not settings_from_mapping({**raw, "verify_ssl": True}).unverified


def test_relative_paths_resolve_against_the_config_dir(tmp_path: Path) -> None:
    raw = {k: v for k, v in RESOLVED.items() if k != "tls_fingerprint"}
    settings = settings_from_mapping(
        {**raw, "ca_bundle": "certs/ca.pem", "api_spec_dir": "apis"}, config_dir=tmp_path
    )
    assert settings.ca_bundle == tmp_path / "certs" / "ca.pem"
    assert settings.api_spec_dir == tmp_path / "apis"
    assert spec_file_for({"api_spec_dir": "apis"}, tmp_path) == tmp_path / "apis/ontap/all.json"


def test_repr_hides_the_credentials() -> None:
    text = repr(settings_from_mapping(RESOLVED))
    assert "pw-example" not in text and "user-example" not in text


def test_invalid_mapping_error_names_keys_not_values() -> None:
    with pytest.raises(OntapSettingsError) as caught:
        settings_from_mapping({**RESOLVED, "timeout": "secret-looking-value"})
    assert "timeout" in str(caught.value)
    assert "secret-looking-value" not in str(caught.value)


def _env(raw: dict[str, Any] | None) -> MagicMock:
    env = MagicMock()
    env.provider_settings = {"ontap": raw} if raw is not None else {}
    return env


def test_load_resolves_secret_references(tmp_path: Path) -> None:
    with (
        patch.object(ontap_settings, "ConfigManager") as manager,
        patch.object(ontap_settings, "resolved_provider_settings", return_value=dict(RESOLVED)),
    ):
        manager.return_value.load_environment.return_value = _env(dict(RAW_SETTINGS))
        loaded = load_settings(tmp_path, "test")
    assert isinstance(loaded, OntapSettings)
    assert loaded.password == "pw-example"


def test_load_without_settings_raises(tmp_path: Path) -> None:
    with patch.object(ontap_settings, "ConfigManager") as manager:
        manager.return_value.load_environment.return_value = _env(None)
        with pytest.raises(OntapSettingsError, match=r"provider_settings\.ontap"):
            load_settings(tmp_path, "test")


def test_load_with_plaintext_secret_raises_before_resolving(tmp_path: Path) -> None:
    with (
        patch.object(ontap_settings, "ConfigManager") as manager,
        patch.object(ontap_settings, "resolved_provider_settings") as resolve,
    ):
        manager.return_value.load_environment.return_value = _env(
            {**RAW_SETTINGS, "password": "plain"}
        )
        with pytest.raises(OntapSettingsError, match="secret://"):
            load_settings(tmp_path, "test")
    resolve.assert_not_called()
