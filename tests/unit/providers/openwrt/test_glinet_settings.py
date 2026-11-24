"""GL.iNet web settings (#1655)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from infrafoundry.core.config.models import EnvironmentConfig
from infrafoundry.providers.openwrt.devices import validate_devices_settings
from infrafoundry.providers.openwrt.glinet.settings import (
    GlinetWebSettings,
    load_web_settings,
    normalize_fingerprint,
    web_settings_from_mapping,
    web_settings_problems,
)
from infrafoundry.providers.openwrt.settings import OpenWrtSettingsError

pytestmark = pytest.mark.unit

PIN = "ab" * 32
PASSWORD = "web-password-example"
BASE: dict[str, Any] = {
    "address": "192.0.2.2",
    "web_password": PASSWORD,
    "tls_fingerprint": PIN,
}


def _load(settings: dict[str, Any], provider: str = "openwrt", secrets: Any = None) -> Any:
    env = EnvironmentConfig(
        name="test", provider_settings={"openwrt": settings}, secrets=secrets or {}
    )
    with patch("infrafoundry.providers.openwrt.glinet.settings.ConfigManager") as manager:
        manager.return_value.load_environment.return_value = env
        return load_web_settings(Path("."), "test", provider)


def test_defaults() -> None:
    web = web_settings_from_mapping(BASE, "provider_settings.openwrt")
    assert web == GlinetWebSettings(
        address="192.0.2.2",
        password=PASSWORD,
        port=443,
        username="root",
        fingerprint=PIN,
        verify_ssl=True,
        upgrade_timeout=1200,
        connect_timeout=10,
    )


@pytest.mark.parametrize(
    "raw", [PIN, PIN.upper(), ":".join(PIN[i : i + 2] for i in range(0, 64, 2)), f" {PIN} "]
)
def test_fingerprint_normalization(raw: str) -> None:
    assert normalize_fingerprint(raw) == PIN


@pytest.mark.parametrize("raw", ["abcd", "zz" * 32, "ab" * 33, "", None, 5])
def test_fingerprint_rejection(raw: object) -> None:
    assert normalize_fingerprint(raw) is None


def test_neither_pin_nor_opt_out_names_both_keys() -> None:
    problems = web_settings_problems({"web_password": "x"}, "where")
    assert len(problems) == 1
    assert "tls_fingerprint" in problems[0] and "verify_ssl" in problems[0]


def test_verify_ssl_false_is_an_explicit_opt_out() -> None:
    web = web_settings_from_mapping(
        {"address": "192.0.2.2", "web_password": "x", "verify_ssl": False}, "where"
    )
    assert web.fingerprint is None and web.verify_ssl is False


def test_a_bad_pin_is_an_error_even_with_the_opt_out() -> None:
    problems = web_settings_problems(
        {"web_password": "x", "tls_fingerprint": "nope", "verify_ssl": False}, "where"
    )
    assert any("tls_fingerprint must be" in p for p in problems)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("web_port", 0),
        ("web_port", 65536),
        ("web_port", "443"),
        ("upgrade_timeout", 299),
        ("upgrade_timeout", 3601),
        ("upgrade_timeout", True),
    ],
)
def test_out_of_range_values_name_the_key(key: str, value: object) -> None:
    with pytest.raises(OpenWrtSettingsError, match=key):
        web_settings_from_mapping({**BASE, key: value}, "where")


def test_a_missing_password_is_a_problem_for_a_firmware_device() -> None:
    problems = web_settings_problems({"tls_fingerprint": PIN}, "where")
    assert problems == ["where.web_password is required for a glinet.firmware resource"]


def test_secret_password_resolves_through_load() -> None:
    web = _load(
        {**BASE, "web_password": "secret://env_secrets/openwrt/web"},
        secrets={"openwrt": {"web": "resolved-example"}},
    )
    assert web.password == "resolved-example"


def test_repr_and_errors_never_carry_the_password() -> None:
    web = web_settings_from_mapping(BASE, "where")
    assert PASSWORD not in repr(web)
    with pytest.raises(OpenWrtSettingsError) as exc:
        web_settings_from_mapping({**BASE, "web_port": 0}, "where")
    assert PASSWORD not in str(exc.value)


def test_device_entry_overrides_shared_password() -> None:
    settings = {
        "web_password": "shared-example",
        "primary": "office",
        "devices": {
            "office": {"address": "192.0.2.2", "tls_fingerprint": PIN},
            "travel": {
                "address": "198.51.100.2",
                "tls_fingerprint": PIN,
                "web_password": "own-example",
                "web_port": 8443,
            },
        },
    }
    assert _load(settings).password == "shared-example"
    travel = _load(settings, "openwrt@travel")
    assert (travel.password, travel.port, travel.address) == ("own-example", 8443, "198.51.100.2")


@pytest.mark.parametrize("key", ["tls_fingerprint", "verify_ssl"])
def test_pin_and_opt_out_cannot_be_top_level_defaults_with_devices(key: str) -> None:
    errors = validate_devices_settings({key: PIN, "devices": {"a": {"address": "192.0.2.2"}}})
    assert any("cannot combine" in e and key in e for e in errors)
    with pytest.raises(OpenWrtSettingsError, match="cannot combine"):
        _load({key: PIN, "devices": {"a": {"address": "192.0.2.2"}}})


def test_flat_shape_keeps_both_keys_at_the_top_level() -> None:
    assert validate_devices_settings(BASE) == []


def test_undeclared_device_raises() -> None:
    with pytest.raises(OpenWrtSettingsError, match="'lab' is not declared"):
        _load({"devices": {"a": {"address": "192.0.2.2"}}, "primary": "a"}, "openwrt@lab")
