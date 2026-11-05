"""The set of objects InfraFoundry manages for a provider (ADR-0018).

Direct-API runners delete only what InfraFoundry itself applied. The state
database is the record of that: :meth:`StateManager.get_managed_resources`
returns the newest ``ACTIVE`` row of each managed ``(resource_type, name)``,
and :func:`build_managed_resources` turns those rows into the
``ResourceConfig`` mapping the orchestrator and executor hand to a runner as
``managed_resources=``.

The helpers here are pure: no database access, no logging of row configs.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypedDict

from infrafoundry.core.provider import ResourceConfig

ManagedResources = Mapping[str, list[ResourceConfig]]
"""Managed rows grouped by resource type (for example ``"unbound.forwards"``)."""


class ReleasedResource(TypedDict):
    """A managed resource the runner removed from the box (or found already gone)."""

    resource_type: str
    name: str


def build_managed_resources(rows: Any, provider: str) -> dict[str, list[ResourceConfig]]:
    """Rebuild ``ResourceConfig`` objects from managed state rows.

    Rows whose ``config`` is not a dict are skipped, because a manager cannot
    derive a key from them.

    Args:
        rows: The list returned by ``StateManager.get_managed_resources``. Anything
            other than a list (for example a ``MagicMock`` state manager's
            return value) yields an empty mapping.
        provider: Provider name stamped on each rebuilt ``ResourceConfig``.

    Returns:
        Managed resources grouped by resource type.
    """
    managed: dict[str, list[ResourceConfig]] = {}
    if not isinstance(rows, list):
        return managed
    for row in rows:
        config = getattr(row, "config", None)
        resource_type = getattr(row, "resource_type", None)
        name = getattr(row, "name", None)
        if not isinstance(config, dict):
            continue
        if not isinstance(resource_type, str) or not isinstance(name, str):
            continue
        managed.setdefault(resource_type, []).append(
            ResourceConfig(name=name, type=resource_type, provider=provider, config=dict(config))
        )
    return managed
