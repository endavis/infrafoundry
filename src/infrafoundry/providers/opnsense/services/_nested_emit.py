"""Helper for emitting nested-format YAML from direct-OPNsense ``migrate`` calls.

Centralises the structural wrapping that turns a flat list of resources for
a single dotted resource type (or a dict-shape singleton) into the nested
``opnsense:`` namespace document defined by ADR-0016 (#793 Phase 4).

The flat resource-centric output that each service's ``export_to_yaml``
historically emitted::

    resources:
      - provider: opnsense
        type: aliases
        name: web-servers
        config: {...}

is replaced (per ADR-0016) by an API-aligned nested layout::

    opnsense:
      firewall:
        aliases:
          - name: web-servers
            config: {...}

For singletons (e.g. ``firewall.log``)::

    opnsense:
      firewall:
        log:
          enabled: false

The helper is intentionally simple and only handles **single-type** documents
— each component manager's ``migrate()`` method emits one resource type at a
time. Multi-type emission is left to a future caller (e.g. a hypothetical
``migrate --all`` command); the same helper composes via dict-merge.

Per ADR-0016, the leaf shape (list vs dict) is declared by
``DOTTED_RESOURCE_SHAPES`` in ``infrafoundry.core.config.package_loader`` and
this helper validates the call against that table so an authoring mistake in
a service's ``export_to_yaml`` surfaces immediately rather than producing
YAML the loader will later reject.
"""

from __future__ import annotations

from typing import Any

import yaml

# ``NESTED_PROVIDER_NAMESPACE`` and the shape table live in the loader so the
# parse and emit sides agree on a single source of truth.
from infrafoundry.core.config.package_loader import (
    DOTTED_RESOURCE_SHAPES,
    NESTED_PROVIDER_NAMESPACE,
)


def emit_nested_list_yaml(dotted_type: str, entries: list[dict[str, Any]]) -> str:
    """Wrap a list of resources at *dotted_type* into nested-format YAML.

    Each entry must already carry a ``name:`` field (and typically a
    ``config:`` block); the helper does not synthesise either. The dotted
    path is split on ``.`` and each component becomes a nested mapping key
    under the top-level ``opnsense:`` namespace.

    Args:
        dotted_type: API-aligned dotted path (e.g. ``firewall.aliases``,
            ``kea.dhcp4.subnets``). Must be registered as a list-shape
            type in ``DOTTED_RESOURCE_SHAPES``.
        entries: List of resource dicts to emit under the leaf list.
            Empty list is allowed (renders as ``[]`` at the leaf).

    Returns:
        YAML string starting with ``opnsense:`` and the nested structure.

    Raises:
        ValueError: If *dotted_type* is unknown or not a list-shape type.
    """
    _check_shape(dotted_type, expected="list")
    nested = _build_nested_branch(dotted_type, entries)
    return yaml.safe_dump({NESTED_PROVIDER_NAMESPACE: nested}, sort_keys=False)


def emit_nested_singleton_yaml(dotted_type: str, config: dict[str, Any]) -> str:
    """Wrap a singleton config mapping at *dotted_type* into nested YAML.

    Args:
        dotted_type: API-aligned dotted path (e.g. ``firewall.log``,
            ``tailscale.settings``). Must be registered as a dict-shape
            type in ``DOTTED_RESOURCE_SHAPES``.
        config: Mapping of singleton fields. Becomes the leaf mapping
            verbatim.

    Returns:
        YAML string starting with ``opnsense:`` and the nested structure.

    Raises:
        ValueError: If *dotted_type* is unknown or not a dict-shape type.
    """
    _check_shape(dotted_type, expected="dict")
    nested = _build_nested_branch(dotted_type, config)
    return yaml.safe_dump({NESTED_PROVIDER_NAMESPACE: nested}, sort_keys=False)


def emit_nested_multi_yaml(branches: dict[str, Any]) -> str:
    """Wrap multiple dotted-type branches into a single nested YAML document.

    Used by component managers that legitimately emit more than one resource
    type in one call (e.g. :class:`KeaDHCPManager.migrate` exports DHCPv4
    subnets, DHCPv4 reservations, DHCPv6 subnets and DHCPv6 reservations
    together so the operator gets one document with the full Kea picture).

    Args:
        branches: Mapping of ``dotted_type`` → ``list[dict] | dict`` payload.
            Each key is validated against ``DOTTED_RESOURCE_SHAPES`` and the
            payload shape must match the declared leaf shape.

    Returns:
        YAML string with all branches merged under a single
        ``opnsense:`` top-level key.

    Raises:
        ValueError: If any dotted_type is unknown or its payload shape
            doesn't match the declared leaf shape.
    """
    nested: dict[str, Any] = {}
    for dotted_type, payload in branches.items():
        if isinstance(payload, list):
            _check_shape(dotted_type, expected="list")
        elif isinstance(payload, dict):
            _check_shape(dotted_type, expected="dict")
        else:
            raise ValueError(
                f"emit_nested_multi_yaml: payload for '{dotted_type}' must be "
                f"a list or dict, got {type(payload).__name__}"
            )
        _merge_nested_branch(nested, dotted_type, payload)
    return yaml.safe_dump({NESTED_PROVIDER_NAMESPACE: nested}, sort_keys=False)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _check_shape(dotted_type: str, *, expected: str) -> None:
    """Validate that *dotted_type* is registered with the *expected* shape.

    Args:
        dotted_type: The dotted resource type to validate.
        expected: ``"list"`` or ``"dict"`` — the shape the caller is about
            to emit.

    Raises:
        ValueError: If *dotted_type* is not in ``DOTTED_RESOURCE_SHAPES``
            or if its declared shape is not *expected*.
    """
    if dotted_type not in DOTTED_RESOURCE_SHAPES:
        raise ValueError(
            f"Unknown direct-OPNsense resource type {dotted_type!r}. "
            f"Known dotted paths: {sorted(DOTTED_RESOURCE_SHAPES)!r}"
        )
    declared = DOTTED_RESOURCE_SHAPES[dotted_type]
    if declared != expected:
        raise ValueError(
            f"Resource type {dotted_type!r} is declared as {declared!r} "
            f"shape but caller is emitting {expected!r}-shape data."
        )


def _build_nested_branch(dotted_type: str, leaf: Any) -> dict[str, Any]:
    """Build a nested dict tree from a dotted path and its leaf value.

    Example:
        ``_build_nested_branch("kea.dhcp4.subnets", [...])`` returns
        ``{"kea": {"dhcp4": {"subnets": [...]}}}``.

    Args:
        dotted_type: Dotted resource type (e.g. ``"firewall.aliases"``).
        leaf: Value to place at the leaf — a list of entry dicts for
            list-shape types, or a config mapping for dict-shape types.

    Returns:
        Nested mapping with *leaf* placed at the path indicated by
        *dotted_type*.
    """
    parts = dotted_type.split(".")
    nested: dict[str, Any] = {}
    cursor: dict[str, Any] = nested
    for key in parts[:-1]:
        next_level: dict[str, Any] = {}
        cursor[key] = next_level
        cursor = next_level
    cursor[parts[-1]] = leaf
    return nested


def _merge_nested_branch(target: dict[str, Any], dotted_type: str, leaf: Any) -> None:
    """Place *leaf* into *target* at the dotted path, creating intermediates.

    Used by :func:`emit_nested_multi_yaml` to merge multiple branches into
    a single nested document. If two branches share a parent (e.g.
    ``firewall.aliases`` and ``firewall.rules``) the parent dict is
    extended rather than overwritten. A direct collision (the leaf key
    already set) raises ``ValueError`` — emitting the same dotted type
    twice is a programming error.

    Args:
        target: Pre-existing nested mapping; mutated in place.
        dotted_type: Dotted path under which to place *leaf*.
        leaf: List or dict to set at the leaf position.

    Raises:
        ValueError: If an intermediate key in *target* is already set to
            a non-dict value or if the leaf key is already present.
    """
    parts = dotted_type.split(".")
    cursor = target
    for key in parts[:-1]:
        next_value = cursor.get(key)
        if next_value is None:
            new_level: dict[str, Any] = {}
            cursor[key] = new_level
            cursor = new_level
        elif isinstance(next_value, dict):
            cursor = next_value
        else:
            raise ValueError(
                f"Cannot merge '{dotted_type}': intermediate key {key!r} "
                f"in target already holds a non-dict ({type(next_value).__name__})."
            )
    leaf_key = parts[-1]
    if leaf_key in cursor:
        raise ValueError(
            f"Cannot merge '{dotted_type}': leaf key {leaf_key!r} already "
            "present in target. Each dotted type may only be emitted once."
        )
    cursor[leaf_key] = leaf
