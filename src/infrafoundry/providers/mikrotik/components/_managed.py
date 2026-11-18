"""Managed-set keys for the MikroTik diff (ADR-0018).

InfraFoundry deletes an undeclared live object only when it applied that object
before. Each managed row is parsed on its own, so one row that no longer parses
cannot hide the others; it is skipped and therefore never deleted. The warning
names the type and row name, never its config.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from infrafoundry.core.provider import ResourceConfig

from ..schema import desired_from_resources

logger = logging.getLogger(__name__)


def managed_keys(
    resources: list[ResourceConfig] | None, type_name: str
) -> set[tuple[Any, ...]] | None:
    """Derive the identity keys of the managed rows of one type.

    Args:
        resources: Managed rows for the type, or ``None`` when the caller gave no
            managed set (nothing is deleted without ``absent: true``).
        type_name: The resource type, used in warnings.

    Returns:
        The set of keys, or ``None`` when ``resources`` is ``None``.
    """
    if resources is None:
        return None
    keys: set[tuple[Any, ...]] = set()
    for row in resources:
        try:
            keys.update(obj.key for obj in desired_from_resources([row]))
        except (ValueError, TypeError, KeyError):
            logger.warning(
                "mikrotik %s: managed row %r could not be parsed; it will not be deleted",
                type_name,
                row.name,
            )
    return keys


@dataclass
class ManagedIndex:
    """The managed rows of one type, resolved to keys."""

    names: dict[tuple[Any, ...], str] = field(default_factory=dict)
    """Identity key to the managed row's name (the first row wins)."""
    unparsed: set[str] = field(default_factory=set)
    """Names of managed rows whose config no longer parses (kept, never released)."""


def managed_index(resources: list[ResourceConfig] | None, type_name: str) -> ManagedIndex:
    """Map the managed rows of one type to their keys and flag the unparsable ones.

    Args:
        resources: Managed rows for the type, or ``None``.
        type_name: The resource type, used in warnings.

    Returns:
        The key-to-name map and the names that failed to parse.
    """
    index = ManagedIndex()
    for row in resources or []:
        try:
            keys = [obj.key for obj in desired_from_resources([row])]
        except (ValueError, TypeError, KeyError):
            logger.warning(
                "mikrotik %s: managed row %r could not be parsed; it will not be released",
                type_name,
                row.name,
            )
            index.unparsed.add(row.name)
            continue
        for key in keys:
            index.names.setdefault(key, row.name)
    return index
