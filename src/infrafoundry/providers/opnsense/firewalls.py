"""Several OPNsense firewalls per environment (#1450, ADR-0024).

``provider_settings.opnsense`` is either the flat shape (``api_url``, ``api_key``,
``api_secret`` ...) describing one firewall, or a ``firewalls:`` map naming each one:

.. code-block:: yaml

    provider_settings:
      opnsense:
        verify_ssl: false          # shared default, an entry may override it
        primary: fw-a
        firewalls:
          fw-a: {api_url: ..., api_key: ..., api_secret: ..., ha_backup: fw-b}
          fw-b: {api_url: ..., api_key: ..., api_secret: ...}

Each firewall is a provider instance (``opnsense`` for the primary,
``opnsense@<name>`` for the others, see :mod:`infrafoundry.core.provider_instances`).
:func:`firewall_settings` turns the provider id back into the flat settings dict the
rest of the provider already understands, so the legacy path is untouched.
"""

from __future__ import annotations

from typing import Any

from infrafoundry.core.provider_instances import (
    INSTANCE_NAME_RE,
    primary_instance,
    split_provider_id,
)

BASE_PROVIDER = "opnsense"
FIREWALLS_KEY = "firewalls"
PRIMARY_KEY = "primary"
HA_BACKUP_KEY = "ha_backup"

#: Keys that identify one firewall; they cannot be shared defaults.
_PER_FIREWALL_KEYS = ("api_url", "api_key", "api_secret", "ssh_host")


def _raw_settings(settings_or_env_config: Any, provider_name: str) -> dict[str, Any] | None:
    """Return the base ``opnsense`` settings dict from a dict or an environment config."""
    if isinstance(settings_or_env_config, dict):
        return settings_or_env_config
    getter = getattr(settings_or_env_config, "get_provider_settings", None)
    if getter is None:
        return None
    base = split_provider_id(provider_name)[0]
    result = getter(base)
    return result if isinstance(result, dict) else None


def _firewalls_map(settings: dict[str, Any] | None) -> dict[str, Any] | None:
    firewalls = (settings or {}).get(FIREWALLS_KEY)
    return firewalls if isinstance(firewalls, dict) else None


def _instance_for(settings: dict[str, Any], provider_name: str) -> str | None:
    """Return the firewall name ``provider_name`` addresses, or ``None`` if unknown."""
    instance = split_provider_id(provider_name)[1]
    if instance is not None:
        return instance
    return primary_instance(BASE_PROVIDER, {BASE_PROVIDER: settings})


def firewall_settings(settings_or_env_config: Any, provider_name: str) -> dict[str, Any] | None:
    """Resolve the flat settings dict for one firewall.

    Args:
        settings_or_env_config: The ``opnsense`` provider settings dict, or an
            environment config exposing ``get_provider_settings``.
        provider_name: ``opnsense`` (the primary) or ``opnsense@<name>``.

    Returns:
        With no ``firewalls:`` map, the settings unchanged (``None`` stays ``None``).
        Otherwise the shared top-level defaults merged with the firewall's entry
        (the entry wins), minus ``firewalls``, ``primary`` and ``ha_backup``. An
        undeclared or ambiguous firewall yields an empty dict.
    """
    settings = _raw_settings(settings_or_env_config, provider_name)
    firewalls = _firewalls_map(settings)
    if settings is None or firewalls is None:
        return settings
    name = _instance_for(settings, provider_name)
    entry = firewalls.get(name) if name is not None else None
    if not isinstance(entry, dict):
        return {}
    merged = {
        k: v for k, v in settings.items() if k not in (FIREWALLS_KEY, PRIMARY_KEY, HA_BACKUP_KEY)
    }
    merged.update({k: v for k, v in entry.items() if k != HA_BACKUP_KEY})
    return merged


def allows_env_override(provider_name: str) -> bool:
    """Return whether ``OPNSENSE_*`` env vars may override this firewall's settings.

    Only the primary (the plain ``opnsense`` id) accepts them; an instance would
    otherwise be redirected to the same endpoint as the primary.
    """
    return split_provider_id(provider_name)[1] is None


def firewall_label(settings_or_env_config: Any, provider_name: str) -> str | None:
    """Return the firewall name to show in output, or ``None`` for a flat config."""
    settings = _raw_settings(settings_or_env_config, provider_name)
    if _firewalls_map(settings) is None or settings is None:
        return None
    return _instance_for(settings, provider_name)


def ha_backup_name(settings_or_env_config: Any, provider_name: str) -> str | None:
    """Return the ``ha_backup`` firewall name set on this firewall's entry, if any."""
    settings = _raw_settings(settings_or_env_config, provider_name)
    firewalls = _firewalls_map(settings)
    if settings is None or firewalls is None:
        return None
    name = _instance_for(settings, provider_name)
    entry = firewalls.get(name) if name is not None else None
    backup = entry.get(HA_BACKUP_KEY) if isinstance(entry, dict) else None
    return backup if isinstance(backup, str) and backup else None


def validate_firewalls_settings(settings: dict[str, Any] | None) -> list[str]:
    """Return the shape errors in ``provider_settings.opnsense`` (empty when valid).

    Args:
        settings: The ``opnsense`` provider settings; ``None`` or flat settings are valid.
    """
    if not isinstance(settings, dict) or FIREWALLS_KEY not in settings:
        return []
    errors: list[str] = []
    firewalls = settings[FIREWALLS_KEY]
    if not isinstance(firewalls, dict) or not firewalls:
        return [f"provider_settings.opnsense.{FIREWALLS_KEY} must be a non-empty mapping"]
    clash = [k for k in _PER_FIREWALL_KEYS if k in settings]
    if clash:
        errors.append(
            f"provider_settings.opnsense cannot combine '{FIREWALLS_KEY}' with top-level "
            f"{', '.join(clash)}; move them into a firewall entry"
        )
    for name, entry in firewalls.items():
        if not isinstance(name, str) or not INSTANCE_NAME_RE.match(name):
            errors.append(
                f"firewall name {name!r} is invalid; use lowercase letters, digits and '-' "
                "(1-32 characters)"
            )
        if not isinstance(entry, dict):
            errors.append(f"firewall '{name}' must be a mapping")
    names = [str(n) for n in firewalls]
    primary = settings.get(PRIMARY_KEY)
    if primary is None:
        if len(names) > 1:
            errors.append(f"'{PRIMARY_KEY}' is required when more than one firewall is declared")
    elif primary not in firewalls:
        errors.append(f"{PRIMARY_KEY} '{primary}' is not declared under {FIREWALLS_KEY}")
    for name, entry in firewalls.items():
        if not isinstance(entry, dict):
            continue
        backup = entry.get(HA_BACKUP_KEY)
        if backup is None:
            continue
        if backup not in firewalls:
            errors.append(f"firewall '{name}': {HA_BACKUP_KEY} '{backup}' is not declared")
        elif backup == name:
            errors.append(f"firewall '{name}': {HA_BACKUP_KEY} cannot name the firewall itself")
    return errors
