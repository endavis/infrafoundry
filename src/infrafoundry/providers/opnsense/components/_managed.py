"""Shared helper that derives managed-set keys for OPNsense list managers (ADR-0018).

A manager whose ``DELETE_SCOPE`` is ``"managed_set"`` receives the rows
InfraFoundry applied before as ``managed_resources``. Its diff engine deletes a
live object only when the object's key is in the set derived here.

Each row is parsed on its own, so one row that no longer parses (a schema change,
a half-written config) cannot hide the others. A row that fails is skipped and
therefore never deleted. The warning names the type and the row name, never its
config, which can hold secrets.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from infrafoundry.core.exceptions import InfraFoundryError
from infrafoundry.core.provider import ResourceConfig

logger = logging.getLogger(__name__)


def managed_keys(
    resources: list[ResourceConfig] | None,
    parse: Callable[[list[ResourceConfig]], list[Any]],
    *,
    type_name: str,
    unresolved: set[str] | None = None,
) -> set[Any] | None:
    """Derive the diff keys of the managed rows.

    Args:
        resources: Managed rows for the type, or ``None`` when the caller gave no
            managed set (legacy full reconcile).
        parse: The type's ``*_configs_from_resources`` function. Each returned
            config must expose ``diff_key``.
        type_name: Resource type, used in warnings.
        unresolved: Optional collector. The names of rows whose key could not be
            derived are added to it, so the runner keeps them managed and retries
            them on the next run instead of releasing them.

    Returns:
        The set of keys, or ``None`` when ``resources`` is ``None``. Rows that
        fail to parse or have no key are skipped and logged by type and name.
    """
    if resources is None:
        return None
    keys: set[Any] = set()
    for row in resources:
        try:
            configs = parse([row])
        except (ValueError, TypeError, KeyError, InfraFoundryError):
            logger.warning(
                "opnsense %s: managed row %r could not be parsed; it will not be deleted",
                type_name,
                row.name,
            )
            if unresolved is not None:
                unresolved.add(row.name)
            continue
        found = False
        for config in configs:
            key = getattr(config, "diff_key", None)
            if key is not None:
                keys.add(key)
                found = True
        if not found and unresolved is not None:
            unresolved.add(row.name)
    return keys


def subnet_cidr_keys(
    resources: list[ResourceConfig] | None, unresolved: set[str] | None = None
) -> set[str] | None:
    """Derive the kea subnet keys (CIDR strings) of the managed rows.

    The subnet managers match live subnets by their ``subnet`` CIDR, which comes
    straight from the row config, so no parsing is needed.

    Args:
        resources: Managed subnet rows, or ``None`` for the legacy full reconcile.
        unresolved: Optional collector for the names of rows with no ``subnet``.

    Returns:
        The set of non-empty CIDR strings, or ``None`` when ``resources`` is ``None``.
    """
    if resources is None:
        return None
    keys: set[str] = set()
    for row in resources:
        cidr = str(row.config.get("subnet", "") or "")
        if cidr:
            keys.add(cidr)
        elif unresolved is not None:
            unresolved.add(row.name)
    return keys
