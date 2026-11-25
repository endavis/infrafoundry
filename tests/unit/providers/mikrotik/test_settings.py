"""Tests for MikroTik settings loading."""

from pathlib import Path
from unittest.mock import patch

import pytest

from infrafoundry.core.config.models import EnvironmentConfig
from infrafoundry.providers.mikrotik.settings import (
    MikroTikSettings,
    MikroTikSettingsError,
    load_settings,
    management_host,
    settings_from_mapping,
)

PASSWORD = "pw-example-0123"


def _env(settings: dict[str, object] | None, secrets: dict[str, object] | None = None) -> object:
    return EnvironmentConfig(
        name="test",
        provider_settings={"mikrotik": settings} if settings is not None else {},
        secrets=secrets,
    )


def _load(env: object) -> MikroTikSettings:
    with patch("infrafoundry.providers.mikrotik.settings.ConfigManager") as manager:
        manager.return_value.load_environment.return_value = env
        return load_settings(Path("."), "test")


def test_secret_uris_resolve() -> None:
    env = _env(
        {
            "api_url": "https://192.0.2.2/",
            "username": "secret://env_secrets/mikrotik/user",
            "password": "secret://env_secrets/mikrotik/password",
        },
        {"mikrotik": {"user": "admin", "password": PASSWORD}},
    )

    settings = _load(env)

    assert (settings.api_url, settings.username, settings.password) == (
        "https://192.0.2.2",
        "admin",
        PASSWORD,
    )
    assert settings.verify_ssl is True


def test_missing_settings_raises_clear_error() -> None:
    with pytest.raises(MikroTikSettingsError, match=r"provider_settings\.mikrotik"):
        _load(_env(None))


def test_missing_key_names_key_not_value() -> None:
    with pytest.raises(MikroTikSettingsError) as exc:
        settings_from_mapping({"api_url": "https://192.0.2.2", "password": PASSWORD})
    assert "username" in str(exc.value)
    assert PASSWORD not in str(exc.value)


def test_password_not_in_repr() -> None:
    settings = settings_from_mapping(
        {"api_url": "https://192.0.2.2", "username": "admin", "password": PASSWORD}
    )
    assert PASSWORD not in repr(settings)
    assert PASSWORD not in str(settings)


@pytest.mark.parametrize(
    ("url", "host"),
    [
        ("https://192.0.2.2", "192.0.2.2"),
        ("https://sw-wan.example.com:8443/", "sw-wan.example.com"),
        ("http://198.51.100.7:8080", "198.51.100.7"),
    ],
)
def test_management_host(url: str, host: str) -> None:
    assert management_host(url) == host


def test_management_host_without_host_raises() -> None:
    with pytest.raises(MikroTikSettingsError):
        management_host("not-a-url")


@pytest.mark.parametrize(
    ("url", "scheme", "port"),
    [
        ("https://192.0.2.2", "https", 443),
        ("http://192.0.2.2", "http", 80),
        ("https://192.0.2.2:8443", "https", 8443),
    ],
)
def test_scheme_and_port(url: str, scheme: str, port: int) -> None:
    settings = settings_from_mapping({"api_url": url, "username": "a", "password": "b"})
    assert (settings.scheme, settings.port) == (scheme, port)


def _mapping(**extra: object) -> dict[str, object]:
    return {"api_url": "https://192.0.2.2", "username": "admin", "password": PASSWORD, **extra}


def test_upgrade_timeout_default_and_valid() -> None:
    assert settings_from_mapping(_mapping()).upgrade_timeout == 900
    assert settings_from_mapping(_mapping(upgrade_timeout=120)).upgrade_timeout == 120
    assert settings_from_mapping(_mapping(upgrade_timeout=3600)).upgrade_timeout == 3600


@pytest.mark.parametrize("value", [119, 3601, "900", True, 1.5])
def test_upgrade_timeout_rejected_without_the_value(value: object) -> None:
    with pytest.raises(MikroTikSettingsError) as caught:
        settings_from_mapping(_mapping(upgrade_timeout=value))
    assert "upgrade_timeout" in str(caught.value)
    assert str(value) not in str(caught.value) or str(value) in ("1", "True")
