"""Connection settings for the MikroTik provider, read from ``provider_settings.mikrotik``."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from infrafoundry.core.config import ConfigManager
from infrafoundry.core.exceptions import InfraFoundryError
from infrafoundry.secrets.resolver import SecretResolver

PROVIDER_NAME = "mikrotik"
DEFAULT_TIMEOUT = 10
_REQUIRED = ("api_url", "username", "password")


class MikroTikSettingsError(InfraFoundryError):
    """The MikroTik provider settings are missing or incomplete. Never carries a secret."""


@dataclass(frozen=True)
class MikroTikSettings:
    """How to reach one RouterOS device over its REST API."""

    api_url: str
    username: str
    password: str = field(repr=False)
    verify_ssl: bool = True
    timeout: int = DEFAULT_TIMEOUT

    @property
    def scheme(self) -> str:
        """URL scheme of ``api_url`` (``http`` or ``https``)."""
        return urlparse(self.api_url).scheme or "https"

    @property
    def port(self) -> int:
        """Port of ``api_url``, defaulting to 80 for http and 443 for https."""
        return urlparse(self.api_url).port or (80 if self.scheme == "http" else 443)


def management_host(api_url: str) -> str:
    """Return the host part of ``api_url`` (an IP literal or a hostname).

    Args:
        api_url: The device's REST base URL.

    Raises:
        MikroTikSettingsError: If the URL has no host.
    """
    host = urlparse(api_url).hostname
    if not host:
        raise MikroTikSettingsError(f"mikrotik api_url '{api_url}' has no host")
    return host


def settings_from_mapping(raw: dict[str, Any]) -> MikroTikSettings:
    """Build settings from an already secret-resolved mapping.

    Args:
        raw: The ``provider_settings.mikrotik`` mapping.

    Raises:
        MikroTikSettingsError: If a required key is missing. Names keys, never values.
    """
    missing = [key for key in _REQUIRED if not raw.get(key)]
    if missing:
        raise MikroTikSettingsError("provider_settings.mikrotik is missing: " + ", ".join(missing))
    management_host(str(raw["api_url"]))
    return MikroTikSettings(
        api_url=str(raw["api_url"]).rstrip("/"),
        username=str(raw["username"]),
        password=str(raw["password"]),
        verify_ssl=bool(raw.get("verify_ssl", True)),
        timeout=int(raw.get("timeout", DEFAULT_TIMEOUT)),
    )


def load_settings(config_dir: Path, env_name: str) -> MikroTikSettings:
    """Load and secret-resolve ``provider_settings.mikrotik`` for an environment.

    Args:
        config_dir: Configuration directory.
        env_name: Environment name.

    Raises:
        MikroTikSettingsError: If the settings are absent or incomplete.
        SecretResolutionError: If a ``secret://`` reference cannot be resolved.
    """
    env_config = ConfigManager(config_dir).load_environment(env_name)
    raw = env_config.provider_settings.get(PROVIDER_NAME) if env_config else None
    if not raw:
        raise MikroTikSettingsError(
            f"No provider_settings.mikrotik found for environment '{env_name}'"
        )
    resolver = SecretResolver()
    resolver.configure_backend("env_secrets", {"secrets": env_config.secrets or {}})
    try:
        resolved = resolver.resolve_config(dict(raw))
    finally:
        resolver.close()
    return settings_from_mapping(resolved)
