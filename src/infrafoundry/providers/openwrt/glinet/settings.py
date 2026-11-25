"""Web-API settings of a GL.iNet router (ADR-0036).

The firmware upgrade talks to the router's web JSON-RPC API, not SSH. The settings sit
beside the SSH ones in ``provider_settings.openwrt`` (or in a ``devices:`` entry):

.. code-block:: yaml

    provider_settings:
      openwrt:
        devices:
          office:
            address: 192.0.2.2
            web_password: secret://openwrt/office-web
            tls_fingerprint: "AB:CD:..."   # SHA-256 of the router's certificate

``tls_fingerprint`` and ``verify_ssl`` identify one router, so they are per-device only.
Messages name keys, never values.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from infrafoundry.core.config import ConfigManager
from infrafoundry.core.provider_instances import split_provider_id
from infrafoundry.core.tls_pin import FINGERPRINT_HEX_LENGTH, normalize_fingerprint
from infrafoundry.providers.openwrt.devices import (
    device_settings,
    validate_devices_settings,
)
from infrafoundry.providers.openwrt.settings import (
    PROVIDER_NAME,
    OpenWrtSettingsError,
    device_where,
    settings_from_mapping,
)
from infrafoundry.secrets.environment import resolved_provider_settings

DEFAULT_WEB_USERNAME = "root"
DEFAULT_WEB_PORT = 443
DEFAULT_UPGRADE_TIMEOUT = 1200
MIN_UPGRADE_TIMEOUT = 300
MAX_UPGRADE_TIMEOUT = 3600


@dataclass(frozen=True)
class GlinetWebSettings:
    """How to reach one router's web API. The password is hidden from ``repr``."""

    address: str
    password: str = field(repr=False)
    port: int = DEFAULT_WEB_PORT
    username: str = DEFAULT_WEB_USERNAME
    fingerprint: str | None = None
    verify_ssl: bool = True
    upgrade_timeout: int = DEFAULT_UPGRADE_TIMEOUT
    connect_timeout: int = 10


def _int_problem(raw: dict[str, Any], key: str, low: int, high: int, where: str) -> str | None:
    if key not in raw:
        return None
    value = raw[key]
    if isinstance(value, bool) or not isinstance(value, int):
        return f"{where}.{key} must be an integer"
    if not low <= value <= high:
        return f"{where}.{key} must be within {low}-{high}"
    return None


def web_settings_problems(merged: dict[str, Any], where: str) -> list[str]:
    """Return what is wrong with one device's web settings (empty when valid).

    The check is offline: a ``secret://`` password counts as present.

    Args:
        merged: The device's merged settings (shared defaults plus its entry).
        where: Settings path used in the messages.
    """
    problems: list[str] = []
    if not merged.get("web_password"):
        problems.append(f"{where}.web_password is required for a glinet.firmware resource")
    for message in (
        _int_problem(merged, "web_port", 1, 65535, where),
        _int_problem(merged, "upgrade_timeout", MIN_UPGRADE_TIMEOUT, MAX_UPGRADE_TIMEOUT, where),
    ):
        if message:
            problems.append(message)
    pin = merged.get("tls_fingerprint")
    verify = merged.get("verify_ssl", True)
    if verify is not True and verify is not False:
        problems.append(f"{where}.verify_ssl must be true or false")
    if pin not in (None, ""):
        if normalize_fingerprint(pin) is None:
            problems.append(
                f"{where}.tls_fingerprint must be a SHA-256 fingerprint "
                f"({FINGERPRINT_HEX_LENGTH} hex characters, ':' separators allowed)"
            )
    elif verify is not False:
        problems.append(
            f"{where} needs tls_fingerprint (the router's SHA-256 certificate pin) "
            "or, unsafely, verify_ssl: false"
        )
    return problems


def web_settings_from_mapping(merged: dict[str, Any], where: str) -> GlinetWebSettings:
    """Build web settings from an already secret-resolved mapping.

    Raises:
        OpenWrtSettingsError: On any problem from :func:`web_settings_problems`, or a
            missing address. Names keys, never values.
    """
    problems = web_settings_problems(merged, where)
    ssh = settings_from_mapping(merged, where)  # validates the address
    if problems:
        raise OpenWrtSettingsError("; ".join(problems))
    pin = normalize_fingerprint(merged.get("tls_fingerprint"))
    return GlinetWebSettings(
        address=ssh.address,
        password=str(merged["web_password"]),
        port=int(merged.get("web_port", DEFAULT_WEB_PORT)),
        username=str(merged.get("web_username") or DEFAULT_WEB_USERNAME),
        fingerprint=pin,
        verify_ssl=merged.get("verify_ssl", True) is not False,
        upgrade_timeout=int(merged.get("upgrade_timeout", DEFAULT_UPGRADE_TIMEOUT)),
        connect_timeout=ssh.connect_timeout,
    )


def load_web_settings(
    config_dir: Path, env_name: str, provider_name: str = PROVIDER_NAME
) -> GlinetWebSettings:
    """Load and secret-resolve one device's web settings for an environment.

    Args:
        config_dir: Configuration directory.
        env_name: Environment name.
        provider_name: ``openwrt`` (the primary or the only device) or ``openwrt@<name>``.

    Raises:
        OpenWrtSettingsError: If the settings are absent or invalid. Names keys only.
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
    return web_settings_from_mapping(merged, device_where(raw, provider_name))
