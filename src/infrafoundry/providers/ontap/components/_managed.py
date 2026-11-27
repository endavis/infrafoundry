"""Managed-set keys for the ONTAP diff (ADR-0018).

InfraFoundry deletes an undeclared live LIF only when it applied that LIF before. Each
managed row is parsed on its own, so one row that no longer parses cannot hide the
others; it is skipped and therefore never deleted. The warning names the row, never its
config.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from infrafoundry.core.provider import ResourceConfig

from ..schema import desired_from_resources

logger = logging.getLogger(__name__)


@dataclass
class ManagedIndex:
    """The managed rows resolved to identity keys."""

    names: dict[tuple[str, str], str] = field(default_factory=dict)
    """Identity key to the managed row's name (the first row wins)."""
    unparsed: set[str] = field(default_factory=set)
    """Names of managed rows whose config no longer parses (kept, never released)."""


def managed_index(resources: list[ResourceConfig] | None) -> ManagedIndex:
    """Map the managed rows to their keys and flag the unparsable ones.

    Args:
        resources: Managed rows of the type, or ``None``.
    """
    index = ManagedIndex()
    for row in resources or []:
        try:
            keys = [obj.key for obj in desired_from_resources([row])]
        except (ValueError, TypeError, KeyError):
            logger.warning(
                "ontap: managed row %r could not be parsed; it will not be deleted or released",
                row.name,
            )
            index.unparsed.add(row.name)
            continue
        for key in keys:
            index.names.setdefault(key, row.name)
    return index
