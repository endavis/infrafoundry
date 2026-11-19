"""Managed-set handling for the OpenWrt provider (ADR-0018).

InfraFoundry deletes an undeclared device object only when it applied that object
before. Each managed row is parsed on its own, so one row that no longer parses
cannot hide the others; it is skipped and therefore never deleted. The warning
names the type and row name, never its config.

Only ``dhcp.host`` and ``firewall.redirect`` rows can be deleted. A managed
``network.interface`` or ``dhcp.pool`` that is no longer declared is only forgotten:
the section stays on the device.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field

from infrafoundry.core.managed_set import ReleasedResource
from infrafoundry.core.provider import ResourceConfig

from ..schema import SPECS, Desired, desired_from_resources

logger = logging.getLogger(__name__)


@dataclass
class ManagedIndex:
    """The managed rows resolved against the declared objects."""

    names: set[tuple[str, str]] = field(default_factory=set)
    """``(type, resource name)`` of every managed row."""
    removals: list[Desired] = field(default_factory=list)
    """Deletable managed rows no longer declared, as ``absent`` objects."""
    forgotten: list[ReleasedResource] = field(default_factory=list)
    """Non-deletable managed rows no longer declared; released without touching the device."""


def managed_index(
    managed: Mapping[str, list[ResourceConfig]] | None, declared: list[Desired]
) -> ManagedIndex:
    """Resolve the managed rows against what the YAML declares.

    Args:
        managed: Managed rows by type, or ``None`` when the caller gave no managed set.
        declared: The declared objects.

    Returns:
        The managed names, the rows to delete and the rows to forget.
    """
    index = ManagedIndex()
    declared_keys = {(d.type_name, d.key) for d in declared}
    for type_name, rows in (managed or {}).items():
        if type_name not in SPECS:
            continue
        for row in rows:
            try:
                parsed = desired_from_resources([row])
            except (ValueError, TypeError, KeyError):
                logger.warning(
                    "openwrt %s: managed row %r could not be parsed; it will not be released",
                    type_name,
                    row.name,
                )
                continue
            if not parsed:
                continue
            item = parsed[0]
            index.names.add((type_name, row.name))
            if (type_name, item.key) in declared_keys:
                continue
            if item.spec.deletable:
                index.removals.append(
                    Desired(item.spec, row.name, item.key, {}, absent=True, confirm=False)
                )
            else:
                index.forgotten.append(ReleasedResource(resource_type=type_name, name=row.name))
    return index
