"""Connection settings for the OpenWrt provider, read from ``provider_settings.openwrt``.

The settings name one device, or a ``devices:`` map naming several (see
:mod:`infrafoundry.providers.openwrt.devices`). Authentication is the SSH key the
controller already uses; the provider stores no password.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from infrafoundry.core.config import ConfigManager
from infrafoundry.core.exceptions import InfraFoundryError
from infrafoundry.core.provider_instances import instance_name, split_provider_id
from infrafoundry.providers.openwrt.devices import (
    device_settings,
    devices_declared,
    validate_devices_settings,
)
from infrafoundry.secrets.environment import resolved_provider_settings

PROVIDER_NAME = "openwrt"
DEFAULT_SSH_USER = "root"
DEFAULT_SSH_PORT = 22
DEFAULT_ROLLBACK_TIMEOUT = 90
MIN_ROLLBACK_TIMEOUT = 30
MAX_ROLLBACK_TIMEOUT = 600
DEFAULT_CONNECT_TIMEOUT = 10
RECONNECT_MARGIN = 15
"""Seconds kept free of the rollback timeout for the confirm call after reconnecting."""


class OpenWrtSettingsError(InfraFoundryError):
    """The OpenWrt provider settings are missing or invalid. Names keys, never values."""


@dataclass(frozen=True)
class OpenWrtSettings:
    """How to reach one OpenWrt device over SSH."""

    address: str
    ssh_user: str = DEFAULT_SSH_USER
    ssh_port: int = DEFAULT_SSH_PORT
    ssh_private_key_file: str | None = None
    rollback_timeout: int = DEFAULT_ROLLBACK_TIMEOUT
    connect_timeout: int = DEFAULT_CONNECT_TIMEOUT

    @property
    def reconnect_timeout(self) -> int:
        """Seconds to wait for the device after the apply (rollback timeout minus a margin)."""
        return self.rollback_timeout - RECONNECT_MARGIN


def _int_setting(raw: dict[str, Any], key: str, default: int, where: str) -> int:
    value = raw.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise OpenWrtSettingsError(f"{where}.{key} must be an integer")
    return value


_ADDRESS = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
"""A host name, IPv4 or IPv6 address: no spaces, quotes or option syntax."""


def settings_from_mapping(
    raw: dict[str, Any], where: str = "provider_settings.openwrt"
) -> OpenWrtSettings:
    """Build settings from an already secret-resolved mapping.

    Args:
        raw: The ``provider_settings.openwrt`` mapping (or one device's merged settings).
        where: Settings path used in error messages.

    Raises:
        OpenWrtSettingsError: If ``address`` is missing or a value is out of range.
            Names keys, never values.
    """
    if not raw.get("address"):
        raise OpenWrtSettingsError(f"{where} is missing: address")
    if not _ADDRESS.match(str(raw["address"])):
        # The address also becomes an ssh option (HostKeyAlias), so it must be a
        # plain host name or IP address.
        raise OpenWrtSettingsError(f"{where}.address must be a host name or IP address")
    port = _int_setting(raw, "ssh_port", DEFAULT_SSH_PORT, where)
    if not 1 <= port <= 65535:
        raise OpenWrtSettingsError(f"{where}.ssh_port must be within 1-65535")
    timeout = _int_setting(raw, "rollback_timeout", DEFAULT_ROLLBACK_TIMEOUT, where)
    if not MIN_ROLLBACK_TIMEOUT <= timeout <= MAX_ROLLBACK_TIMEOUT:
        raise OpenWrtSettingsError(
            f"{where}.rollback_timeout must be within {MIN_ROLLBACK_TIMEOUT}-{MAX_ROLLBACK_TIMEOUT}"
        )
    key_file = raw.get("ssh_private_key_file")
    return OpenWrtSettings(
        address=str(raw["address"]),
        ssh_user=str(raw.get("ssh_user") or DEFAULT_SSH_USER),
        ssh_port=port,
        ssh_private_key_file=str(key_file) if key_file else None,
        rollback_timeout=timeout,
        connect_timeout=_int_setting(raw, "connect_timeout", DEFAULT_CONNECT_TIMEOUT, where),
    )


def device_where(raw: dict[str, Any] | None, provider_name: str) -> str:
    """Return the settings path error messages use for the device ``provider_name`` addresses."""
    if not devices_declared(raw):
        return "provider_settings.openwrt"
    name = instance_name(PROVIDER_NAME, raw or {}, provider_name)
    return f"provider_settings.openwrt.devices.{name}"


def load_settings(
    config_dir: Path, env_name: str, provider_name: str = PROVIDER_NAME
) -> OpenWrtSettings:
    """Load and secret-resolve one device's settings for an environment.

    Args:
        config_dir: Configuration directory.
        env_name: Environment name.
        provider_name: ``openwrt`` (the primary or the only device) or ``openwrt@<name>``.

    Raises:
        OpenWrtSettingsError: If the settings are absent or invalid, or the device is
            not declared.
        SecretResolutionError: If a ``secret://`` reference of this device cannot be resolved.
    """
    env_config = ConfigManager(config_dir).load_environment(env_name)
    raw = env_config.provider_settings.get(PROVIDER_NAME) if env_config else None
    if not raw or env_config is None:
        raise OpenWrtSettingsError(
            f"No provider_settings.openwrt found for environment '{env_name}'"
        )
    shape = validate_devices_settings(raw)
    if shape:
        raise OpenWrtSettingsError("; ".join(shape))
    resolved = resolved_provider_settings(env_config, provider_name) or {}
    merged = device_settings(resolved, provider_name)
    if not merged:
        device = split_provider_id(provider_name)[1] or "primary"
        raise OpenWrtSettingsError(
            f"openwrt device '{device}' is not declared under provider_settings.openwrt.devices"
        )
    return settings_from_mapping(merged, device_where(raw, provider_name))
