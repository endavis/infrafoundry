"""Provider instances: several targets of one provider in one environment (#1450).

A provider that supports instances (see :data:`INSTANCE_SPECS`: ``opnsense`` and
``kubernetes``) is configured with an instance map in ``provider_settings``
(``firewalls:`` for OPNsense, ``clusters:`` for Kubernetes). Each extra entry is a
separate provider instance whose id is ``<provider>@<name>``. The primary entry keeps
the plain provider id, so a flat configuration and state rows written before instances
existed keep working unchanged.

Everything keyed by provider id (duplicate check, state rows, dependency graph
nodes, executor batches, post-apply hooks, validation reports) therefore becomes
per-instance without a change to ``ResourceConfig`` or the state schema.

The map key, primary key, selector key and the noun used in messages come from one
:class:`InstanceSpec` per provider, so the helpers here serve every instance-capable
provider.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable, Mapping, MutableMapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from infrafoundry.core.exceptions import InvalidConfigurationError

logger = logging.getLogger(__name__)

INSTANCE_SEPARATOR = "@"


@dataclass(frozen=True)
class InstanceSpec:
    """How one provider names its instances in settings, configuration and messages."""

    #: ``provider_settings.<base>`` key holding the instance map (``firewalls``).
    map_key: str
    #: ``provider_settings.<base>`` key naming the primary instance (``primary``).
    primary_key: str
    #: Key an entry, file or manifest uses to pick an instance (``firewall``).
    selector_key: str
    #: Singular word used in messages (``firewall``).
    noun: str


#: base provider id -> how it names its instances
INSTANCE_SPECS: dict[str, InstanceSpec] = {
    "opnsense": InstanceSpec("firewalls", "primary", "firewall", "firewall"),
    "kubernetes": InstanceSpec("clusters", "primary", "cluster", "cluster"),
}

#: Every selector key (``firewall`` ...) some instance-capable provider honours.
SELECTOR_KEYS: frozenset[str] = frozenset(spec.selector_key for spec in INSTANCE_SPECS.values())

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


def instance_spec(base: str) -> InstanceSpec | None:
    """Return the :class:`InstanceSpec` for ``base``, or ``None`` without instance support."""
    return INSTANCE_SPECS.get(base)


def validate_instance_name(
    base: str, instance: str, source: str, selector_key: str = "firewall"
) -> None:
    """Check that ``base`` supports instances and ``instance`` is a valid name.

    Args:
        base: Base provider id.
        instance: Candidate instance name.
        source: Where the name came from, for the error message.
        selector_key: The selector key the name came from; ``base`` must honour it.

    Raises:
        InvalidConfigurationError: If the provider has no instance support or the
            name does not match ``INSTANCE_NAME_RE``.
    """
    spec = INSTANCE_SPECS.get(base)
    if spec is None or spec.selector_key != selector_key:
        supported = sorted(b for b, sp in INSTANCE_SPECS.items() if sp.selector_key == selector_key)
        raise InvalidConfigurationError(
            f"{source}: '{selector_key}' is only supported for provider {supported!r}, not '{base}'"
        )
    if not isinstance(instance, str) or not INSTANCE_NAME_RE.match(instance):
        raise InvalidConfigurationError(
            f"{source}: invalid {spec.noun} name {instance!r}; use lowercase letters, "
            "digits and '-' (1-32 characters, starting with a letter or digit)"
        )


def stamp_instance(
    resource: _Stampable, instance: str, source: str, selector_key: str = "firewall"
) -> None:
    """Point an unstamped resource at ``instance`` of its provider.

    A resource whose provider already carries an instance is left alone, so the
    most specific selection wins.

    Args:
        resource: Resource to stamp; its ``provider`` is rewritten in place.
        instance: Instance name.
        source: Where the selection came from, for error messages.
        selector_key: The selector key the name came from.

    Raises:
        InvalidConfigurationError: If the provider does not support instances or the
            name is invalid.
    """
    base, existing = split_provider_id(resource.provider)
    if existing is not None:
        return
    validate_instance_name(base, instance, source, selector_key)
    resource.provider = qualified_provider_id(base, instance)


def stamp_selected(
    resources: Iterable[_Stampable], selections: Mapping[str, str | None], source: str
) -> None:
    """Stamp each resource with the selection that belongs to its provider.

    A resource is stamped only when its base provider's selector key has a value in
    ``selections``; every other resource is left alone. Resources already stamped keep
    their more specific selection (see :func:`stamp_instance`).

    Args:
        resources: Resources to stamp, rewritten in place.
        selections: Selector key (``firewall`` ...) -> instance name, or ``None``.
        source: Where the selections came from, for error messages.

    Raises:
        InvalidConfigurationError: If a selected name is invalid.
    """
    for resource in resources:
        spec = INSTANCE_SPECS.get(split_provider_id(resource.provider)[0])
        if spec is None:
            continue
        instance = selections.get(spec.selector_key)
        if instance is not None:
            stamp_instance(resource, instance, source, spec.selector_key)


def entry_instance_provider(
    item: Mapping[str, Any], default_provider: str, source: str, where: str
) -> str | None:
    """Return the provider id for an entry carrying its own selector key, if any.

    Args:
        item: Resource entry mapping.
        default_provider: Provider used when the entry names none.
        source: Source filename for error messages.
        where: Resource type or entry label for error messages.

    Returns:
        ``<base>@<name>`` for the entry, or ``None`` when it has no selector key.

    Raises:
        InvalidConfigurationError: If the entry's provider does not honour the selector
            key it carries, or the name is invalid.
    """
    base = str(item.get("provider", default_provider)).partition(INSTANCE_SEPARATOR)[0]
    result: str | None = None
    for key in sorted(SELECTOR_KEYS):
        value = item.get(key)
        if value is None:
            continue
        validate_instance_name(
            base, value, f"{source}: entry '{item.get('name', '?')}' ({where})", key
        )
        result = qualified_provider_id(base, value)
    return result


def own_instance_provider(
    item: Mapping[str, Any],
    base: str,
    source: str,
    where: str,
    *,
    only_selector: str | None = None,
) -> str | None:
    """Return the instance provider id for an entry's own selector key, if it has one.

    Unlike :func:`entry_instance_provider` this reads only the selector key of ``base``
    itself. Flat provider-centric entries carry their whole configuration, so a foreign
    selector key there is an ordinary setting, not a selection.

    Args:
        item: Resource entry mapping.
        base: Base provider id of the entry.
        source: Source filename for error messages.
        where: Resource type or entry label for error messages.
        only_selector: When set, honour the entry's key only if it is this selector key
            (so a flat entry of another family keeps a same-named setting untouched).

    Returns:
        ``<base>@<name>``, or ``None`` when ``base`` has no instances or the entry sets none.

    Raises:
        InvalidConfigurationError: If the name is invalid.
    """
    base = base.partition(INSTANCE_SEPARATOR)[0]
    spec = INSTANCE_SPECS.get(base)
    if spec is not None and only_selector is not None and spec.selector_key != only_selector:
        return None
    value = item.get(spec.selector_key) if spec is not None else None
    if spec is None or value is None:
        return None
    validate_instance_name(
        base, value, f"{source}: entry '{item.get('name', '?')}' ({where})", spec.selector_key
    )
    return qualified_provider_id(base, value)


def raw_provider_settings(settings_or_env_config: Any, provider_id: str) -> dict[str, Any] | None:
    """Return the base provider's settings dict from a dict or an environment config."""
    if isinstance(settings_or_env_config, dict):
        return settings_or_env_config
    getter = getattr(settings_or_env_config, "get_provider_settings", None)
    if getter is None:
        return None
    result = getter(split_provider_id(provider_id)[0])
    return result if isinstance(result, dict) else None


def _instance_map(base: str, settings: dict[str, Any] | None) -> dict[str, Any] | None:
    spec = INSTANCE_SPECS[base]
    instances = (settings or {}).get(spec.map_key)
    return instances if isinstance(instances, dict) else None


def instance_name(base: str, settings: dict[str, Any], provider_id: str) -> str | None:
    """Return the instance name ``provider_id`` addresses, or ``None`` if unknown."""
    instance = split_provider_id(provider_id)[1]
    if instance is not None:
        return instance
    return primary_instance(base, {base: settings})


def instance_settings(
    base: str,
    settings_or_env_config: Any,
    provider_id: str,
    *,
    drop_keys: Sequence[str] = (),
) -> dict[str, Any] | None:
    """Resolve the flat settings dict for one instance.

    Args:
        base: Base provider id; it must have an :class:`InstanceSpec`.
        settings_or_env_config: The provider settings dict, or an environment config
            exposing ``get_provider_settings``.
        provider_id: ``<base>`` (the primary) or ``<base>@<name>``.
        drop_keys: Extra keys to remove from the shared defaults and the entry.

    Returns:
        With no instance map, the settings unchanged (``None`` stays ``None``, and a
        flat dict is returned as the same object). Otherwise the shared top-level
        defaults merged with the instance's entry (the entry wins), minus the map key,
        the primary key and ``drop_keys``. An undeclared or ambiguous instance yields
        an empty dict.
    """
    spec = INSTANCE_SPECS[base]
    settings = raw_provider_settings(settings_or_env_config, provider_id)
    instances = _instance_map(base, settings)
    if settings is None or instances is None:
        return settings
    name = instance_name(base, settings, provider_id)
    entry = instances.get(name) if name is not None else None
    if not isinstance(entry, dict):
        return {}
    skip = {spec.map_key, spec.primary_key, *drop_keys}
    merged = {k: v for k, v in settings.items() if k not in skip}
    merged.update({k: v for k, v in entry.items() if k not in drop_keys})
    return merged


def instance_label(base: str, settings_or_env_config: Any, provider_id: str) -> str | None:
    """Return the instance name to show in output, or ``None`` for a flat config."""
    settings = raw_provider_settings(settings_or_env_config, provider_id)
    if settings is None or _instance_map(base, settings) is None:
        return None
    return instance_name(base, settings, provider_id)


def is_primary_id(provider_id: str) -> bool:
    """Return whether ``provider_id`` is a plain id (the primary), not ``base@name``."""
    return split_provider_id(provider_id)[1] is None


def validate_instance_map(
    base: str, settings: dict[str, Any] | None, per_instance_keys: Sequence[str]
) -> list[str]:
    """Return the shape errors in ``provider_settings.<base>`` (empty when valid).

    Checks the map is a non-empty mapping, no per-instance key is also a top-level
    default, names and entries are well formed, and ``primary`` is declared.

    Args:
        base: Base provider id; it must have an :class:`InstanceSpec`.
        settings: The provider settings; ``None`` or flat settings are valid.
        per_instance_keys: Keys that identify one instance and so cannot be shared.
    """
    spec = INSTANCE_SPECS[base]
    if not isinstance(settings, dict) or spec.map_key not in settings:
        return []
    errors: list[str] = []
    instances = settings[spec.map_key]
    if not isinstance(instances, dict) or not instances:
        return [f"provider_settings.{base}.{spec.map_key} must be a non-empty mapping"]
    clash = [k for k in per_instance_keys if k in settings]
    if clash:
        errors.append(
            f"provider_settings.{base} cannot combine '{spec.map_key}' with top-level "
            f"{', '.join(clash)}; move them into a {spec.noun} entry"
        )
    for name, entry in instances.items():
        if not isinstance(name, str) or not INSTANCE_NAME_RE.match(name):
            errors.append(
                f"{spec.noun} name {name!r} is invalid; use lowercase letters, digits and '-' "
                "(1-32 characters)"
            )
        if not isinstance(entry, dict):
            errors.append(f"{spec.noun} '{name}' must be a mapping")
    primary = settings.get(spec.primary_key)
    if primary is None:
        if len(instances) > 1:
            errors.append(
                f"'{spec.primary_key}' is required when more than one {spec.noun} is declared"
            )
    elif primary not in instances:
        errors.append(f"{spec.primary_key} '{primary}' is not declared under {spec.map_key}")
    return errors


def declared_instances(base: str, provider_settings: dict[str, Any] | None) -> list[str]:
    """Return the instance names declared for ``base`` in ``provider_settings``.

    Args:
        base: Base provider id.
        provider_settings: ``EnvironmentConfig.provider_settings`` (may be ``None``).

    Returns:
        Names in declaration order; empty when the provider has no instance map.
    """
    spec = INSTANCE_SPECS.get(base)
    if spec is None or not isinstance(provider_settings, dict):
        return []
    settings = provider_settings.get(base)
    if not isinstance(settings, dict):
        return []
    instances = settings.get(spec.map_key)
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
    spec = INSTANCE_SPECS[base]
    settings = (provider_settings or {}).get(base) or {}
    named = settings.get(spec.primary_key)
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
    flat configuration to an instance map.

    Args:
        resources: Resources loaded from configuration.
        provider_settings: Environment ``provider_settings``.

    Raises:
        InvalidConfigurationError: If a resource names an instance that is not
            declared in the provider's instance map.
    """
    for resource in resources:
        base, instance = split_provider_id(resource.provider)
        if instance is None:
            continue
        declared = declared_instances(base, provider_settings)
        if instance not in declared:
            spec = INSTANCE_SPECS[base]
            known = ", ".join(declared) if declared else "none declared"
            raise InvalidConfigurationError(
                f"Resource targets {spec.noun} '{instance}' of provider '{base}', which is "
                f"not declared under provider_settings.{base}.{spec.map_key} (declared: {known})"
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
    for base in INSTANCE_SPECS:
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
