"""Extractor registry for ``config migrate`` per-component dispatch.

Provides a small registry keyed by ``(provider_name, resource_type)`` that
maps each migratable component to an :class:`Extractor` — anything with an
``extract(env_name, **kwargs) -> str`` method that returns InfraFoundry YAML.

Providers populate the registry during their own ``__init__`` (see
``OPNsenseProvider._register_extractors``); the CLI ``config migrate``
command looks up extractors at runtime and validates ``--provider`` /
``--component`` against the registered set rather than a hardcoded
``click.Choice``. New components become reachable on the CLI as soon as
they register an extractor; no edit to the CLI choice list is required.

The shape mirrors :mod:`infrafoundry.core.runners.runner_registry`: a
class-based registry plus a module-level singleton with thin convenience
functions. Re-registration silently overwrites — required so test
fixtures that re-instantiate providers don't error.
"""

from __future__ import annotations

from typing import Any, Protocol


class Extractor(Protocol):
    """Protocol implemented by every config-migrate extractor.

    The ``extract`` method must return the InfraFoundry YAML payload as a
    string. ``**kwargs`` is passed through to the underlying component
    manager — the registry is intentionally agnostic to per-component
    options (e.g., ``interfaces`` for ``isc_to_kea``).
    """

    def extract(self, env_name: str, **kwargs: Any) -> str:
        """Return the migrated InfraFoundry YAML for ``env_name``."""
        ...


class ExtractorRegistry:
    """Registry mapping ``(provider_name, resource_type)`` to extractors.

    Providers register one extractor per migratable component during
    ``__init__``. The CLI looks up extractors at dispatch time and treats
    unregistered combinations as user errors rather than silent no-ops.
    """

    def __init__(self) -> None:
        """Initialize an empty registry."""
        self._extractors: dict[tuple[str, str], Extractor] = {}

    def register(self, provider_name: str, resource_type: str, extractor: Extractor) -> None:
        """Register an extractor for ``(provider_name, resource_type)``.

        Re-registration silently overwrites the prior entry. This matches
        ``RunnerRegistry.register`` semantics and is required so test
        fixtures that re-instantiate providers don't accumulate
        registrations and don't error on the second pass.

        Args:
            provider_name: Provider name (e.g., ``"opnsense"``).
            resource_type: Resource type / component name
                (e.g., ``"interfaces.vlans"``, ``"kea_dhcp"``).
            extractor: An object satisfying the :class:`Extractor`
                Protocol.
        """
        self._extractors[(provider_name, resource_type)] = extractor

    def get(self, provider_name: str, resource_type: str) -> Extractor:
        """Return the extractor for ``(provider_name, resource_type)``.

        Args:
            provider_name: Provider name.
            resource_type: Resource type / component name.

        Returns:
            The registered :class:`Extractor`.

        Raises:
            KeyError: When no extractor is registered for the requested
                combination. The error message lists the registered
                providers (when ``provider_name`` is unknown) or the
                registered resource types for that provider (when only
                ``resource_type`` is unknown), so callers can surface a
                helpful message to the operator without re-querying the
                registry.
        """
        key = (provider_name, resource_type)
        if key in self._extractors:
            return self._extractors[key]

        if not self.has_provider(provider_name):
            providers = ", ".join(self.list_providers()) or "<none>"
            raise KeyError(
                f"No extractors registered for provider {provider_name!r}. "
                f"Registered providers: {providers}."
            )

        resource_types = ", ".join(self.list_resource_types(provider_name)) or "<none>"
        raise KeyError(
            f"No extractor registered for resource type {resource_type!r} "
            f"under provider {provider_name!r}. "
            f"Registered resource types: {resource_types}."
        )

    def has(self, provider_name: str, resource_type: str) -> bool:
        """Return True iff ``(provider_name, resource_type)`` is registered.

        Args:
            provider_name: Provider name.
            resource_type: Resource type / component name.
        """
        return (provider_name, resource_type) in self._extractors

    def has_provider(self, provider_name: str) -> bool:
        """Return True iff at least one extractor is registered for the provider.

        Args:
            provider_name: Provider name.
        """
        return any(p == provider_name for p, _ in self._extractors)

    def list_resource_types(self, provider_name: str) -> list[str]:
        """Return the registered resource types for a provider, sorted.

        An empty list is returned for unknown providers (intentional —
        callers can use this to detect "no migrate components" without
        catching exceptions).

        Args:
            provider_name: Provider name.
        """
        return sorted(rt for p, rt in self._extractors if p == provider_name)

    def list_providers(self) -> list[str]:
        """Return the registered provider names, sorted."""
        return sorted({p for p, _ in self._extractors})


# Module-level singleton mirrors ``infrafoundry.core.runners.runner_registry``.
_extractor_registry = ExtractorRegistry()


def register_extractor(provider_name: str, resource_type: str, extractor: Extractor) -> None:
    """Register an extractor on the module-level registry.

    Args:
        provider_name: Provider name.
        resource_type: Resource type / component name.
        extractor: The :class:`Extractor` to register.
    """
    _extractor_registry.register(provider_name, resource_type, extractor)


def get_extractor(provider_name: str, resource_type: str) -> Extractor:
    """Return an extractor from the module-level registry.

    Args:
        provider_name: Provider name.
        resource_type: Resource type / component name.

    Raises:
        KeyError: When no extractor is registered for the combination.
    """
    return _extractor_registry.get(provider_name, resource_type)


def has_extractor(provider_name: str, resource_type: str) -> bool:
    """Return True iff the registry has the requested extractor.

    Args:
        provider_name: Provider name.
        resource_type: Resource type / component name.
    """
    return _extractor_registry.has(provider_name, resource_type)


def list_extractor_resource_types(provider_name: str) -> list[str]:
    """Return registered resource types for a provider, sorted.

    Args:
        provider_name: Provider name.
    """
    return _extractor_registry.list_resource_types(provider_name)


def list_extractor_providers() -> list[str]:
    """Return registered provider names, sorted."""
    return _extractor_registry.list_providers()
