"""QNAP provider settings: offline checks, defaults and loading."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from infrafoundry.providers.qnap import settings as qnap_settings
from infrafoundry.providers.qnap.settings import (
    QnapSettings,
    QnapSettingsError,
    load_settings,
    raw_settings_problems,
    settings_from_mapping,
)

from .conftest import RAW_SETTINGS

pytestmark = pytest.mark.unit

RESOLVED: dict[str, Any] = {
    **RAW_SETTINGS,
    "username": "user-example",
    "password": "pw-example",
}


def _problems(**changes: Any) -> list[str]:
    raw = {**RAW_SETTINGS, **changes}
    return raw_settings_problems({k: v for k, v in raw.items() if v is not None})


def test_valid_settings_have_no_problems() -> None:
    assert raw_settings_problems(dict(RAW_SETTINGS)) == []


@pytest.mark.parametrize("key", ["username", "password"])
def test_plaintext_credential_is_rejected_without_echoing_it(key: str) -> None:
    problems = _problems(**{key: "plain-value-example"})
    assert any(key in p and "secret://" in p for p in problems)
    assert "plain-value-example" not in " ".join(problems)


def test_missing_keys_are_named() -> None:
    problems = raw_settings_problems({"tls_fingerprint": RAW_SETTINGS["tls_fingerprint"]})
    assert "api_url" in problems[0] and "username" in problems[0] and "password" in problems[0]


def test_http_api_url_is_rejected() -> None:
    assert any("https://" in p for p in _problems(api_url="http://192.0.2.10"))


def test_api_url_without_host_is_rejected() -> None:
    assert any("no host" in p for p in _problems(api_url="https://"))


def test_missing_pin_needs_verify_ssl_false() -> None:
    assert any("tls_fingerprint" in p for p in _problems(tls_fingerprint=None))
    assert _problems(tls_fingerprint=None, verify_ssl=False) == []


def test_bad_pin_is_rejected() -> None:
    assert any("SHA-256" in p for p in _problems(tls_fingerprint="abc"))


def test_verify_ssl_must_be_bool() -> None:
    assert any("verify_ssl" in p for p in _problems(verify_ssl="no"))


@pytest.mark.parametrize(
    ("key", "bad"),
    [
        ("timeout", 0),
        ("timeout", 121),
        ("timeout", True),
        ("timeout", "10"),
        ("check_timeout", 9),
        ("check_timeout", 601),
        ("upgrade_timeout", 299),
        ("upgrade_timeout", 3601),
        ("upgrade_timeout", False),
    ],
)
def test_timeouts_out_of_range_or_not_int_are_rejected(key: str, bad: Any) -> None:
    assert any(key in p for p in _problems(**{key: bad}))


def test_defaults_are_applied() -> None:
    settings = settings_from_mapping(dict(RESOLVED))
    assert (settings.timeout, settings.check_timeout, settings.upgrade_timeout) == (10, 90, 1200)
    assert settings.fingerprint == "ab" * 32
    assert settings.verify_ssl is True
    assert (settings.host, settings.port) == ("192.0.2.10", 443)


def test_explicit_port_and_trailing_slash() -> None:
    settings = settings_from_mapping({**RESOLVED, "api_url": "https://192.0.2.10:8443/"})
    assert settings.port == 8443 and settings.api_url == "https://192.0.2.10:8443"


def test_invalid_resolved_settings_raise() -> None:
    with pytest.raises(QnapSettingsError):
        settings_from_mapping({**RESOLVED, "timeout": 0})


def test_repr_hides_credentials() -> None:
    text = repr(QnapSettings("https://192.0.2.10", "user-example", "pw-example"))
    assert "user-example" not in text and "pw-example" not in text


def test_load_settings_resolves_secrets_after_the_raw_check(tmp_path: Path) -> None:
    env = MagicMock()
    env.provider_settings = {"qnap": dict(RAW_SETTINGS)}
    with (
        patch.object(qnap_settings, "ConfigManager") as manager,
        patch.object(
            qnap_settings, "resolved_provider_settings", return_value=dict(RESOLVED)
        ) as resolve,
    ):
        manager.return_value.load_environment.return_value = env
        loaded = load_settings(tmp_path, "dev")
    resolve.assert_called_once_with(env, "qnap")
    assert loaded.username == "user-example"


def test_load_settings_rejects_raw_problems_before_resolving(tmp_path: Path) -> None:
    env = MagicMock()
    env.provider_settings = {"qnap": {**RAW_SETTINGS, "password": "plain"}}
    with (
        patch.object(qnap_settings, "ConfigManager") as manager,
        patch.object(qnap_settings, "resolved_provider_settings") as resolve,
    ):
        manager.return_value.load_environment.return_value = env
        with pytest.raises(QnapSettingsError, match="password"):
            load_settings(tmp_path, "dev")
    resolve.assert_not_called()


def test_load_settings_without_block_raises(tmp_path: Path) -> None:
    with patch.object(qnap_settings, "ConfigManager") as manager:
        manager.return_value.load_environment.return_value = None
        with pytest.raises(QnapSettingsError, match=r"No provider_settings\.qnap"):
            load_settings(tmp_path, "dev")
