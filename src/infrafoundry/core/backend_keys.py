"""Per-provider remote Terraform state locations (#1464).

Every provider of an environment renders its own ``backend.tf`` in its own
directory, but the backend settings are one per environment. Without help, all of
them would point at one remote state. This module derives a distinct location for
each provider when two or more of them render a backend:

* One provider renders a backend: the configured location is used as written.
* Two or more render one: each gets the provider id inserted into the location,
  except the one named by ``backend.bare_key_provider``, which keeps it bare.
* A ``{provider}`` placeholder in the location field overrides the automatic rule.

The orchestrator computes the set of peers once per environment and injects it into
every provider (``assign_backend_peers``), so the result does not depend on ``-P``.
Nothing moves existing state; ``migration_warning`` tells the operator how.
"""

from __future__ import annotations

import copy
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from infrafoundry.core.config.backend_config import BackendConfig, BackendType
from infrafoundry.core.exceptions import InvalidConfigurationError

PROVIDER_PLACEHOLDER = "{provider}"

_REMOTE_SLUG_RE = re.compile(r"[^A-Za-z0-9_-]")
_POSTGRES_SLUG_RE = re.compile(r"[^a-z0-9_]")


@dataclass(frozen=True)
class BackendLocation:
    """The resolved state location of one provider.

    Attributes:
        provider_id: Provider id the location belongs to.
        field: Backend setting that holds the location (``key``, ``prefix``, ...), or
            ``None`` for a backend without one.
        config: Backend settings to render, with the location applied.
        old: Location as configured, or ``None``.
        new: Location to render, or ``None``.
        auto_moved: True when the automatic rule changed the location.
    """

    provider_id: str
    field: str | None
    config: dict[str, Any]
    old: str | None
    new: str | None
    auto_moved: bool


def _slug(provider_id: str, backend_type: BackendType) -> str:
    if backend_type == BackendType.POSTGRES:
        return _POSTGRES_SLUG_RE.sub("_", provider_id.lower())
    return _REMOTE_SLUG_RE.sub("-", provider_id)


def _location_field(backend_type: BackendType, config: dict[str, Any]) -> str | None:
    """Return the config field holding the location, ``workspaces.name`` style for remote."""
    if backend_type in {BackendType.S3, BackendType.AZURERM}:
        return "key"
    if backend_type == BackendType.GCS:
        return "prefix"
    if backend_type == BackendType.POSTGRES:
        return "schema_name"
    if backend_type == BackendType.TERRAFORM_CLOUD:
        workspaces = config.get("workspaces") or {}
        if "name" in workspaces:
            return "workspaces.name"
        if "prefix" in workspaces:
            return "workspaces.prefix"
    return None


def _get(config: dict[str, Any], field: str) -> str | None:
    if field.startswith("workspaces."):
        value = (config.get("workspaces") or {}).get(field.split(".", 1)[1])
    else:
        value = config.get(field)
    return value if isinstance(value, str) else None


def _set(config: dict[str, Any], field: str, value: str) -> None:
    if field.startswith("workspaces."):
        config["workspaces"][field.split(".", 1)[1]] = value
    else:
        config[field] = value


def _placeholder_value(backend_type: BackendType, provider_id: str) -> str:
    if backend_type in {BackendType.TERRAFORM_CLOUD, BackendType.POSTGRES}:
        return _slug(provider_id, backend_type)
    return provider_id


def _auto_value(backend_type: BackendType, field: str, value: str, provider_id: str) -> str:
    if field == "key":
        head, sep, last = value.rpartition("/")
        return f"{head}/{provider_id}/{last}" if sep else f"{provider_id}/{value}"
    if field == "prefix":
        return f"{value.rstrip('/')}/{provider_id}"
    slug = _slug(provider_id, backend_type)
    if field == "workspaces.name":
        return f"{value}-{slug}"
    if field == "workspaces.prefix":
        return f"{value}{slug}-"
    return f"{value}_{slug}"  # postgres schema_name


def resolve_backend_location(
    backend: BackendConfig, provider_id: str, peer_ids: frozenset[str]
) -> BackendLocation:
    """Resolve the backend settings one provider renders.

    Args:
        backend: The environment's backend configuration.
        provider_id: Provider id, for example ``opnsense@fw-b``.
        peer_ids: Ids of every provider of the environment that renders a backend.

    Returns:
        The location, with a copy of the backend settings carrying it.
    """
    config = copy.deepcopy(backend.get_backend_config())
    field = _location_field(backend.type, config)
    old = _get(config, field) if field else None
    if field is None or old is None:
        return BackendLocation(provider_id, field, config, old, old, False)

    if PROVIDER_PLACEHOLDER in old:
        new = old.replace(PROVIDER_PLACEHOLDER, _placeholder_value(backend.type, provider_id))
        _set(config, field, new)
        return BackendLocation(provider_id, field, config, old, new, False)

    peers = peer_ids | {provider_id}
    if len(peers) < 2 or backend.bare_key_provider == provider_id:
        return BackendLocation(provider_id, field, config, old, old, False)

    new = _auto_value(backend.type, field, old, provider_id)
    _set(config, field, new)
    return BackendLocation(provider_id, field, config, old, new, True)


def backend_provider_ids(
    providers: Mapping[str, Any], resource_provider_ids: Iterable[str]
) -> frozenset[str]:
    """Return the provider ids that have resources and render a Terraform backend."""
    return frozenset(
        pid
        for pid in resource_provider_ids
        if pid in providers and getattr(providers[pid], "renders_terraform_backend", None) is True
    )


def migration_warning(location: BackendLocation) -> str:
    """Return the warning telling an operator a provider's state location moved."""
    return (
        f"Provider '{location.provider_id}' now renders its remote state at "
        f"'{location.new}' (was '{location.old}') because several providers of this "
        f"environment render a backend. To keep the existing state, run "
        f"`terraform init -migrate-state` in generated/<env>/terraform/"
        f"{location.provider_id}/ after `plan`, or pin the provider that keeps the old "
        f"location with `backend.bare_key_provider`, or set the location with "
        f"'{PROVIDER_PLACEHOLDER}'."
    )


def assign_backend_peers(
    providers: Mapping[str, Any],
    resource_provider_ids: Iterable[str],
    backend: BackendConfig | None,
) -> list[BackendLocation]:
    """Inject the peer set into every backend-rendering provider.

    Args:
        providers: Registered providers by id.
        resource_provider_ids: Provider ids of the environment's unfiltered resources.
        backend: The environment's backend configuration, or ``None``.

    Returns:
        The locations the automatic rule moved, sorted by provider id.

    Raises:
        InvalidConfigurationError: ``bare_key_provider`` names no provider that renders
            a backend in this environment.
    """
    peers = backend_provider_ids(providers, resource_provider_ids)
    for provider in providers.values():
        if getattr(provider, "renders_terraform_backend", None) is True:
            provider.backend_peer_ids = peers

    if backend is None or backend.type == BackendType.LOCAL:
        return []
    pin = backend.bare_key_provider
    if pin is not None and peers and pin not in peers:
        raise InvalidConfigurationError(
            f"backend.bare_key_provider '{pin}' is not a provider of this environment "
            f"(expected one of: {', '.join(sorted(peers))})"
        )
    moved = [resolve_backend_location(backend, pid, peers) for pid in sorted(peers)]
    return [location for location in moved if location.auto_moved]
