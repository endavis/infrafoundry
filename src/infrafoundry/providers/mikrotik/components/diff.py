"""Pure diff of declared RouterOS objects against live rows.

Compares only the fields the YAML declares, after normalization, so a converged
device plans clean. Dynamic rows (DHCP-assigned addresses, dynamic bridge VLAN
entries) are ignored. Built-in rows are never deleted.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass, field
from typing import Any

from ..schema import DesiredObject, ResourceSpec, key_of, normalize_value

CREATE = "create"
UPDATE = "update"
DELETE = "delete"


@dataclass(frozen=True)
class Change:
    """One planned change to one RouterOS object."""

    kind: str
    type_name: str
    key: tuple[Any, ...]
    resource_name: str
    live_id: str | None = None
    before: dict[str, str] = field(default_factory=dict)
    after: dict[str, Any] = field(default_factory=dict)
    changed: tuple[str, ...] = ()


@dataclass
class TypeDiff:
    """The changes for one resource type, plus the live objects left alone."""

    type_name: str
    changes: list[Change] = field(default_factory=list)
    unmanaged: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        """True when there is nothing to change."""
        return not self.changes

    def count(self, kind: str) -> int:
        """Number of changes of a kind."""
        return sum(1 for c in self.changes if c.kind == kind)


def _is_true(row: dict[str, str], name: str) -> bool:
    return str(row.get(name, "")).strip().lower() in ("true", "yes")


def _label(key: tuple[Any, ...]) -> str:
    return "/".join(
        ",".join(str(i) for i in sorted(part)) if isinstance(part, frozenset) else str(part)
        for part in key
    )


def changed_fields(spec: ResourceSpec, desired: dict[str, Any], live: dict[str, str]) -> list[str]:
    """Return the declared fields whose live value differs, in declaration order."""
    differing: list[str] = []
    for name, raw in desired.items():
        kind = spec.fields.get(name)
        if kind is None or name in spec.key_fields:
            continue
        if normalize_value(kind, raw, name) != _live_value(kind, name, live):
            differing.append(name)
    return differing


def _live_value(kind: str, name: str, live: dict[str, str]) -> Any:
    try:
        return normalize_value(kind, live.get(name), name)
    except ValueError:
        return live.get(name)


def compute_type_diff(
    spec: ResourceSpec,
    desired: list[DesiredObject],
    live: list[dict[str, str]],
    *,
    add_only: bool,
    managed_keys: Collection[tuple[Any, ...]] | None,
) -> TypeDiff:
    """Diff the declared objects of one type against the live rows.

    Args:
        spec: The resource type.
        desired: Declared objects of this type.
        live: Live REST rows of this type.
        add_only: Suppress every delete.
        managed_keys: Keys InfraFoundry applied before (ADR-0018), or ``None`` when the
            caller gave no managed set. Only these are deleted when undeclared.

    Returns:
        The changes, the undeclared live objects kept, and warnings.
    """
    diff = TypeDiff(spec.type_name)
    rows: dict[tuple[Any, ...], dict[str, str]] = {}
    for row in live:
        if _is_true(row, "dynamic"):
            continue
        key = key_of(spec, row)
        if key is not None:
            rows.setdefault(key, row)

    declared: set[tuple[Any, ...]] = set()
    for obj in desired:
        declared.add(obj.key)
        current = rows.get(obj.key)
        if obj.absent:
            if current is not None and spec.deletable and not _is_true(current, "builtin"):
                if add_only:
                    diff.unmanaged.append(_label(obj.key) + " (absent: true, skipped: add-only)")
                else:
                    diff.changes.append(
                        Change(
                            DELETE,
                            spec.type_name,
                            obj.key,
                            obj.resource_name,
                            current.get(".id"),
                            current,
                        )
                    )
            continue
        if current is None:
            if not spec.creatable:
                diff.warnings.append(
                    f"{spec.type_name} '{_label(obj.key)}' does not exist on the device "
                    "and cannot be created"
                )
                continue
            diff.changes.append(
                Change(CREATE, spec.type_name, obj.key, obj.resource_name, after=dict(obj.fields))
            )
            continue
        differing = changed_fields(spec, obj.fields, current)
        if differing:
            diff.changes.append(
                Change(
                    UPDATE,
                    spec.type_name,
                    obj.key,
                    obj.resource_name,
                    current.get(".id"),
                    current,
                    dict(obj.fields),
                    tuple(differing),
                )
            )

    if not spec.deletable:
        return diff
    for key, row in rows.items():
        if key in declared or _is_true(row, "builtin"):
            continue
        if managed_keys is not None and not add_only and key in managed_keys:
            diff.changes.append(
                Change(DELETE, spec.type_name, key, _label(key), row.get(".id"), row)
            )
        else:
            diff.unmanaged.append(_label(key))
    return diff
