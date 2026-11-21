"""Connection settings for the OpenWrt provider, read from ``provider_settings.openwrt``.

The settings name one device per environment. Authentication is the SSH key the
controller already uses; the provider stores no password.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from infrafoundry.core.config import ConfigManager
from infrafoundry.core.exceptions import InfraFoundryError
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


def _int_setting(raw: dict[str, Any], key: str, default: int) -> int:
    value = raw.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise OpenWrtSettingsError(f"provider_settings.openwrt.{key} must be an integer")
    return value


_ADDRESS = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
"""A host name, IPv4 or IPv6 address: no spaces, quotes or option syntax."""


def settings_from_mapping(raw: dict[str, Any]) -> OpenWrtSettings:
    """Build settings from an already secret-resolved mapping.

    Args:
        raw: The ``provider_settings.openwrt`` mapping.

    Raises:
        OpenWrtSettingsError: If ``address`` is missing or a value is out of range.
            Names keys, never values.
    """
    if not raw.get("address"):
        raise OpenWrtSettingsError("provider_settings.openwrt is missing: address")
    if not _ADDRESS.match(str(raw["address"])):
        # The address also becomes an ssh option (HostKeyAlias), so it must be a
        # plain host name or IP address.
        raise OpenWrtSettingsError(
            "provider_settings.openwrt.address must be a host name or IP address"
        )
    port = _int_setting(raw, "ssh_port", DEFAULT_SSH_PORT)
    if not 1 <= port <= 65535:
        raise OpenWrtSettingsError("provider_settings.openwrt.ssh_port must be within 1-65535")
    timeout = _int_setting(raw, "rollback_timeout", DEFAULT_ROLLBACK_TIMEOUT)
    if not MIN_ROLLBACK_TIMEOUT <= timeout <= MAX_ROLLBACK_TIMEOUT:
        raise OpenWrtSettingsError(
            "provider_settings.openwrt.rollback_timeout must be within "
            f"{MIN_ROLLBACK_TIMEOUT}-{MAX_ROLLBACK_TIMEOUT}"
        )
    key_file = raw.get("ssh_private_key_file")
    return OpenWrtSettings(
        address=str(raw["address"]),
        ssh_user=str(raw.get("ssh_user") or DEFAULT_SSH_USER),
        ssh_port=port,
        ssh_private_key_file=str(key_file) if key_file else None,
        rollback_timeout=timeout,
        connect_timeout=_int_setting(raw, "connect_timeout", DEFAULT_CONNECT_TIMEOUT),
    )


def load_settings(config_dir: Path, env_name: str) -> OpenWrtSettings:
    """Load and secret-resolve ``provider_settings.openwrt`` for an environment.

    Args:
        config_dir: Configuration directory.
        env_name: Environment name.

    Raises:
        OpenWrtSettingsError: If the settings are absent or invalid.
        SecretResolutionError: If a ``secret://`` reference cannot be resolved.
    """
    env_config = ConfigManager(config_dir).load_environment(env_name)
    raw = env_config.provider_settings.get(PROVIDER_NAME) if env_config else None
    if not raw or env_config is None:
        raise OpenWrtSettingsError(
            f"No provider_settings.openwrt found for environment '{env_name}'"
        )
    resolved = resolved_provider_settings(env_config, PROVIDER_NAME) or {}
    return settings_from_mapping(resolved)
