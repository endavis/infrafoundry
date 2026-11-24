"""Several OpenWrt devices per environment (#1656, ADR-0035).

``provider_settings.openwrt`` is either the flat shape (``address`` and the SSH keys)
describing one device, or a ``devices:`` map naming each one. Shared defaults sit
beside the map and an entry overrides them:

.. code-block:: yaml

    provider_settings:
      openwrt:
        ssh_user: root
        primary: office
        devices:
          office: {address: 192.0.2.2}
          travel: {address: 198.51.100.2, ssh_port: 2222}

Each device is a provider instance (``openwrt`` for the primary, ``openwrt@<name>`` for
the others, see :mod:`infrafoundry.core.provider_instances`). :func:`device_settings`
turns the provider id back into the flat settings dict the rest of the provider
already understands.
"""

from __future__ import annotations

from typing import Any

from infrafoundry.core.provider_instances import (
    instance_label,
    instance_settings,
    raw_provider_settings,
    validate_instance_map,
)

BASE_PROVIDER = "openwrt"
DEVICES_KEY = "devices"
PRIMARY_KEY = "primary"

#: Keys that identify one device; they cannot be shared defaults.
_PER_DEVICE_KEYS = ("address",)


def device_settings(settings_or_env_config: Any, provider_name: str) -> dict[str, Any] | None:
    """Resolve the flat settings dict for one device.

    Args:
        settings_or_env_config: The ``openwrt`` provider settings dict, or an
            environment config exposing ``get_provider_settings``.
        provider_name: ``openwrt`` (the primary) or ``openwrt@<name>``.

    Returns:
        With no ``devices:`` map, the settings unchanged (``None`` stays ``None``).
        Otherwise the shared defaults merged with the device's entry (the entry wins).
        An undeclared or ambiguous device yields an empty dict.
    """
    return instance_settings(BASE_PROVIDER, settings_or_env_config, provider_name)


def devices_declared(settings_or_env_config: Any) -> bool:
    """Return whether ``provider_settings.openwrt`` declares a ``devices:`` map."""
    settings = raw_provider_settings(settings_or_env_config, BASE_PROVIDER)
    return isinstance(settings, dict) and DEVICES_KEY in settings


def device_label(settings_or_env_config: Any, provider_name: str) -> str | None:
    """Return the device name to show in output, or ``None`` for a flat configuration."""
    return instance_label(BASE_PROVIDER, settings_or_env_config, provider_name)


def validate_devices_settings(settings: dict[str, Any] | None) -> list[str]:
    """Return the shape errors in ``provider_settings.openwrt`` (empty when valid).

    Args:
        settings: The ``openwrt`` provider settings; ``None`` or flat settings are valid.
    """
    return validate_instance_map(BASE_PROVIDER, settings, _PER_DEVICE_KEYS)
