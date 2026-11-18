"""Tests for OpenWrt settings loading."""

from pathlib import Path
from unittest.mock import patch

import pytest

from infrafoundry.core.config.models import EnvironmentConfig
from infrafoundry.providers.openwrt.settings import (
    OpenWrtSettings,
    OpenWrtSettingsError,
    load_settings,
    settings_from_mapping,
)


def _load(env: EnvironmentConfig) -> OpenWrtSettings:
    with patch("infrafoundry.providers.openwrt.settings.ConfigManager") as manager:
        manager.return_value.load_environment.return_value = env
        return load_settings(Path("."), "test")


def test_defaults() -> None:
    settings = settings_from_mapping({"address": "192.0.2.2"})
    assert settings == OpenWrtSettings(
        address="192.0.2.2",
        ssh_user="root",
        ssh_port=22,
        ssh_private_key_file=None,
        rollback_timeout=90,
        connect_timeout=10,
    )
    assert settings.reconnect_timeout == 75


def test_missing_address_names_key_only() -> None:
    with pytest.raises(OpenWrtSettingsError) as exc:
        settings_from_mapping({"ssh_user": "admin-example"})
    assert "address" in str(exc.value)
    assert "admin-example" not in str(exc.value)


@pytest.mark.parametrize("timeout", [29, 601, "90", True])
def test_rollback_timeout_out_of_range_rejected(timeout: object) -> None:
    with pytest.raises(OpenWrtSettingsError, match="rollback_timeout"):
        settings_from_mapping({"address": "192.0.2.2", "rollback_timeout": timeout})


@pytest.mark.parametrize("port", [0, 65536])
def test_ssh_port_out_of_range_rejected(port: int) -> None:
    with pytest.raises(OpenWrtSettingsError, match="ssh_port"):
        settings_from_mapping({"address": "192.0.2.2", "ssh_port": port})


def test_timeout_bounds_accepted() -> None:
    low = settings_from_mapping({"address": "a", "rollback_timeout": 30})
    high = settings_from_mapping({"address": "a", "rollback_timeout": 600})
    assert (low.rollback_timeout, high.rollback_timeout) == (30, 600)


def test_secret_uris_resolve() -> None:
    env = EnvironmentConfig(
        name="test",
        provider_settings={"openwrt": {"address": "secret://env_secrets/openwrt/address"}},
        secrets={"openwrt": {"address": "198.51.100.7"}},
    )
    assert _load(env).address == "198.51.100.7"


def test_absent_settings_raise_clear_error() -> None:
    with pytest.raises(OpenWrtSettingsError, match=r"provider_settings\.openwrt"):
        _load(EnvironmentConfig(name="test", provider_settings={}))


def test_key_file_and_user_are_kept() -> None:
    settings = settings_from_mapping(
        {
            "address": "192.0.2.2",
            "ssh_user": "admin-example",
            "ssh_port": 2222,
            "ssh_private_key_file": "/keys/example",
        }
    )
    assert (settings.ssh_user, settings.ssh_port, settings.ssh_private_key_file) == (
        "admin-example",
        2222,
        "/keys/example",
    )
