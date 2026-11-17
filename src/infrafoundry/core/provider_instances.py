"""Provider instances: several firewalls of one provider in one environment (#1450).

A provider that supports instances (currently ``opnsense``) is configured with a
``firewalls:`` map in ``provider_settings``. Each extra firewall is a separate
provider instance whose id is ``<provider>@<name>``. The primary firewall keeps the
plain provider id, so a flat configuration and state rows written before instances
existed keep working unchanged.

Everything keyed by provider id (duplicate check, state rows, dependency graph
nodes, executor batches, post-apply hooks, validation reports) therefore becomes
per-firewall without a change to ``ResourceConfig`` or the state schema.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable, MutableMapping
from typing import Any, Protocol

from infrafoundry.core.exceptions import InvalidConfigurationError

logger = logging.getLogger(__name__)

INSTANCE_SEPARATOR = "@"

#: provider id -> (settings key holding the instance map, settings key naming the primary)
INSTANCE_SETTINGS: dict[str, tuple[str, str]] = {"opnsense": ("firewalls", "primary")}

#: Instance names stay short so ``<provider>@<name>`` fits the 50-character provider column.
INSTANCE_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")


class _Stampable(Protocol):
    """Anything with a mutable ``provider`` attribute (a ``ResourceConfig``)."""

    provider: str


def split_provider_id(provider_id: str) -> tuple[str, str | None]:
    """Split ``base@instance`` into ``(base, instance)``.

    Args:
        provider_id: A provider id, with or without an instance suffix.

    Returns:
        ``(base, instance)``; ``instance`` is ``None`` for a plain id.
    """
    base, sep, instance = provider_id.partition(INSTANCE_SEPARATOR)
    return (base, instance) if sep else (provider_id, None)


def qualified_provider_id(base: str, instance: str | None) -> str:
    """Return ``base@instance``, or ``base`` when there is no instance."""
    return f"{base}{INSTANCE_SEPARATOR}{instance}" if instance else base


def validate_instance_name(base: str, instance: str, source: str) -> None:
    """Check that ``base`` supports instances and ``instance`` is a valid name.

    Args:
        base: Base provider id.
        instance: Candidate instance name.
        source: Where the name came from, for the error message.

    Raises:
        InvalidConfigurationError: If the provider has no instance support or the
            name does not match ``INSTANCE_NAME_RE``.
    """
    if base not in INSTANCE_SETTINGS:
        raise InvalidConfigurationError(
            f"{source}: 'firewall' is only supported for provider "
            f"{sorted(INSTANCE_SETTINGS)!r}, not '{base}'"
        )
    if not isinstance(instance, str) or not INSTANCE_NAME_RE.match(instance):
        raise InvalidConfigurationError(
            f"{source}: invalid firewall name {instance!r}; use lowercase letters, "
            "digits and '-' (1-32 characters, starting with a letter or digit)"
        )


def stamp_instance(resource: _Stampable, instance: str, source: str) -> None:
    """Point an unstamped resource at ``instance`` of its provider.

    A resource whose provider already carries an instance is left alone, so the
    most specific selection wins.

    Args:
        resource: Resource to stamp; its ``provider`` is rewritten in place.
        instance: Instance (firewall) name.
        source: Where the selection came from, for error messages.

    Raises:
        InvalidConfigurationError: If the provider does not support instances or the
            name is invalid.
    """
    base, existing = split_provider_id(resource.provider)
    if existing is not None:
        return
    validate_instance_name(base, instance, source)
    resource.provider = qualified_provider_id(base, instance)


def declared_instances(base: str, provider_settings: dict[str, Any] | None) -> list[str]:
    """Return the instance names declared for ``base`` in ``provider_settings``.

    Args:
        base: Base provider id.
        provider_settings: ``EnvironmentConfig.provider_settings`` (may be ``None``).

    Returns:
        Names in declaration order; empty when the provider has no instance map.
    """
    keys = INSTANCE_SETTINGS.get(base)
    if keys is None or not isinstance(provider_settings, dict):
        return []
    settings = provider_settings.get(base)
    if not isinstance(settings, dict):
        return []
    instances = settings.get(keys[0])
    if not isinstance(instances, dict):
        return []
    return [str(name) for name in instances]


def primary_instance(base: str, provider_settings: dict[str, Any] | None) -> str | None:
    """Return the primary instance name, or ``None`` without a declared instance map.

    A single declared instance is the primary without naming it.
    """
    names = declared_instances(base, provider_settings)
    if not names:
        return None
    keys = INSTANCE_SETTINGS[base]
    settings = (provider_settings or {}).get(base) or {}
    named = settings.get(keys[1])
    if isinstance(named, str) and named:
        return named
    return names[0] if len(names) == 1 else None


def instance_provider_id(base: str, instance: str, provider_settings: dict[str, Any] | None) -> str:
    """Return the provider id for ``instance``: the plain ``base`` for the primary."""
    if instance == primary_instance(base, provider_settings):
        return base
    return qualified_provider_id(base, instance)


def normalize_instance_providers(
    resources: Iterable[_Stampable], provider_settings: dict[str, Any] | None
) -> None:
    """Rewrite instance-stamped resources onto their final provider ids, in place.

    ``opnsense@<primary>`` becomes ``opnsense`` so state rows survive converting a
    flat configuration to ``firewalls:``.

    Args:
        resources: Resources loaded from configuration.
        provider_settings: Environment ``provider_settings``.

    Raises:
        InvalidConfigurationError: If a resource names a firewall that is not
            declared under ``firewalls:``.
    """
    for resource in resources:
        base, instance = split_provider_id(resource.provider)
        if instance is None:
            continue
        declared = declared_instances(base, provider_settings)
        if instance not in declared:
            known = ", ".join(declared) if declared else "none declared"
            raise InvalidConfigurationError(
                f"Resource targets firewall '{instance}' of provider '{base}', which is "
                f"not declared under provider_settings.{base}.firewalls (declared: {known})"
            )
        resource.provider = instance_provider_id(base, instance, provider_settings)


def register_instance_providers(
    providers: MutableMapping[str, Any], provider_settings: dict[str, Any] | None
) -> None:
    """Register a provider for every declared instance that has none yet.

    Args:
        providers: Orchestrator provider registry, mutated in place.
        provider_settings: Environment ``provider_settings``; non-dict values are ignored.
    """
    if not isinstance(provider_settings, dict):
        return
    for base in INSTANCE_SETTINGS:
        base_provider = providers.get(base)
        spawn = getattr(base_provider, "spawn_instance", None)
        if base_provider is None or not callable(spawn):
            continue
        primary = primary_instance(base, provider_settings)
        for name in declared_instances(base, provider_settings):
            if name == primary:
                continue
            provider_id = qualified_provider_id(base, name)
            if provider_id in providers:
                continue
            providers[provider_id] = spawn(name)
            logger.debug("Registered provider instance %s", provider_id)
