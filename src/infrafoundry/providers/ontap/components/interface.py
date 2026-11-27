"""Pure diff of declared data LIFs against live ONTAP interfaces.

Only declared fields are compared, after normalization, so a converged cluster plans
clean. Only ``scope == "svm"`` rows are considered: cluster and node management LIFs are
never touched. An undeclared LIF is deleted only when InfraFoundry applied it before
(ADR-0018) and the run is not add-only; otherwise it is reported as kept.
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Iterable
from dataclasses import dataclass, field
from typing import Any

from ..schema import COMPARED, DesiredInterface, live_view

CREATE = "create"
UPDATE = "update"
DELETE = "delete"


@dataclass(frozen=True)
class Change:
    """One planned change to one data LIF."""

    kind: str
    key: tuple[str, str]
    resource_name: str
    uuid: str | None = None
    before: dict[str, Any] = field(default_factory=dict)
    """The live view (empty for a create)."""
    after: dict[str, Any] = field(default_factory=dict)
    """The declared fields (create and update)."""
    changed: tuple[str, ...] = ()
    """The declared fields whose live value differs (update)."""


@dataclass
class InterfaceDiff:
    """The changes for the data LIFs, plus what was left alone."""

    changes: list[Change] = field(default_factory=list)
    unmanaged: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    refusals: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        """True when there is nothing to change."""
        return not self.changes

    def count(self, kind: str) -> int:
        """Number of changes of a kind."""
        return sum(1 for c in self.changes if c.kind == kind)


def label(key: tuple[str, str]) -> str:
    """Return ``svm/name`` for an identity key."""
    return f"{key[0]}/{key[1]}"


def changed_fields(declared: dict[str, Any], live: dict[str, Any]) -> list[str]:
    """Return the declared fields whose live value differs, in schema order."""
    return [name for name in COMPARED if name in declared and declared[name] != live.get(name)]


def lockout_refusals(
    changes: Iterable[Change], host: str, management_address: str | None
) -> list[str]:
    """Refuse updating or deleting the LIF the management connection runs over.

    Args:
        changes: The planned changes; creates are ignored.
        host: The ``host`` setting, for the message.
        management_address: The address ``host`` resolves to, or ``None`` when it does not.
    """
    risky = [c for c in changes if c.kind in (UPDATE, DELETE)]
    if not risky:
        return []
    if management_address is None:
        return [
            f"cannot resolve the management host '{host}', so the plan cannot prove it "
            "keeps the management connection"
        ]
    return [
        f"refusing to {c.kind} LIF '{label(c.key)}': its address is the management host "
        f"'{host}', so the change could cut the connection InfraFoundry runs over"
        for c in risky
        if c.before.get("address") == management_address
    ]


def compute_interface_diff(
    desired: list[DesiredInterface],
    live_rows: list[dict[str, Any]],
    *,
    add_only: bool,
    managed_keys: Collection[tuple[str, str]] | None,
    report_svms: Collection[str],
    host: str,
    resolve_management: Callable[[], str | None],
) -> InterfaceDiff:
    """Diff the declared LIFs against the live interfaces.

    Args:
        desired: Declared interfaces.
        live_rows: Live ``network/ip/interfaces`` records.
        add_only: Suppress every delete.
        managed_keys: Keys InfraFoundry applied before (ADR-0018), or ``None`` when the
            caller gave no managed set. Only these are deleted when undeclared.
        report_svms: SVMs whose undeclared LIFs are reported as kept.
        host: The ``host`` setting, for lock-out messages.
        resolve_management: Returns the management address; called only when an update
            or delete is planned.

    Returns:
        The changes, the undeclared LIFs kept, warnings and lock-out refusals.
    """
    diff = InterfaceDiff()
    rows: dict[tuple[str, str], dict[str, Any]] = {}
    for record in live_rows:
        view = live_view(record)
        if view["scope"] != "svm" or not view["svm"] or not view["name"]:
            continue
        rows.setdefault((view["svm"], view["name"]), view)

    declared: set[tuple[str, str]] = set()
    for obj in desired:
        declared.add(obj.key)
        current = rows.get(obj.key)
        if obj.absent:
            if current is None:
                continue
            if add_only:
                diff.unmanaged.append(f"{label(obj.key)} (absent: true, skipped: add-only)")
            else:
                diff.changes.append(
                    Change(DELETE, obj.key, obj.resource_name, current["uuid"], current)
                )
            continue
        if current is None:
            diff.changes.append(Change(CREATE, obj.key, obj.resource_name, after=dict(obj.fields)))
            continue
        if current["is_home"] is False:
            diff.warnings.append(
                f"LIF '{label(obj.key)}' is not on its home port; ONTAP keeps it where it is "
                "until it is reverted"
            )
        differing = changed_fields(obj.fields, current)
        if differing:
            diff.changes.append(
                Change(
                    UPDATE,
                    obj.key,
                    obj.resource_name,
                    current["uuid"],
                    current,
                    dict(obj.fields),
                    tuple(differing),
                )
            )

    for key, view in rows.items():
        if key in declared:
            continue
        if managed_keys is not None and not add_only and key in managed_keys:
            diff.changes.append(Change(DELETE, key, label(key), view["uuid"], view))
        elif key[0] in report_svms:
            diff.unmanaged.append(label(key))

    if any(c.kind in (UPDATE, DELETE) for c in diff.changes):
        diff.refusals.extend(lockout_refusals(diff.changes, host, resolve_management()))
    return diff
