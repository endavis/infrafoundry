"""System-groups service for OPNsense direct-API operations (ADR-0014, #805).

Manages local groups via the ``auth/group`` controller. Identity is the wire
``name``. Group membership is owned here: ``member`` is a comma-joined list of
user uids, compared as a sorted set. YAML ``member_refs`` name ``system.users``
resources; the manager resolves them to live uids. When ``member_refs`` is
absent the group's membership is neither written nor compared.

There is no reconfigure step for groups.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from infrafoundry.core.provider import ResourceConfig

from .. import endpoints
from .base import BaseService, raise_on_failed_write
from .system_users import LiveUser, row_to_live, search_rows

logger = logging.getLogger(__name__)

_STRING_FIELDS: tuple[str, ...] = ("scope", "description")
_VALID_SCOPES: frozenset[str] = frozenset({"system", "user"})
#: Every config key a ``system.groups`` resource accepts (single source for plan and validator).
ALLOWED_KEYS: frozenset[str] = frozenset({"name", "lock", "priv", "member_refs", *_STRING_FIELDS})
#: Keys the box assigns itself; the validator rejects them with an explanation.
BOX_ASSIGNED_KEYS: frozenset[str] = frozenset({"gid"})


@dataclass(frozen=True)
class GroupConfig:
    """Desired-state local group.

    Attributes:
        name: Wire group name (diff key).
        fields: Sorted ``(wire_key, value)`` pairs the operator set.
        member_refs: Referenced ``system.users`` names, or ``None`` when membership is unmanaged.
        lock: Per-resource safety annotation (ADR-0014 section 6).
    """

    name: str
    fields: tuple[tuple[str, str], ...] = ()
    member_refs: tuple[str, ...] | None = None
    lock: bool = False

    @property
    def diff_key(self) -> str:
        """Identity of this group: the wire ``name``."""
        return self.name

    def to_payload(self, member_uids: Sequence[str] | None = None) -> dict[str, Any]:
        """Serialize to the ``add``/``set`` envelope.

        Args:
            member_uids: Resolved member uids. ``member`` is written only when given
                and the group declares ``member_refs``.
        """
        body: dict[str, Any] = {"name": self.name, **dict(self.fields)}
        if self.member_refs is not None and member_uids is not None:
            body["member"] = ",".join(sorted(set(member_uids), key=_uid_sort))
        return {"group": body}


@dataclass(frozen=True)
class LiveGroup:
    """A group as currently configured on the box."""

    uuid: str
    name: str
    gid: str
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def diff_key(self) -> str:
        """Identity of this group: the wire ``name``."""
        return self.name


@dataclass
class Diff:
    """Result of comparing desired groups to live groups.

    ``members`` maps a group name to its resolved member uids; apply writes them.
    """

    adds: list[GroupConfig] = field(default_factory=list)
    updates: list[tuple[LiveGroup, GroupConfig]] = field(default_factory=list)
    deletes: list[LiveGroup] = field(default_factory=list)
    unmanaged: list[LiveGroup] = field(default_factory=list)
    locked: list[tuple[GroupConfig, LiveGroup | None]] = field(default_factory=list)
    members: dict[str, tuple[str, ...]] = field(default_factory=dict)

    @property
    def is_empty(self) -> bool:
        """Return True if there is nothing to add, update or delete."""
        return not (self.adds or self.updates or self.deletes)


def _uid_sort(uid: str) -> tuple[int, str]:
    """Sort numeric uids numerically, anything else after them."""
    return (0, f"{int(uid):012d}") if uid.isdigit() else (1, uid)


def _member_set(value: Any) -> frozenset[str]:
    """Split a live comma-separated ``member`` value into a set of uids."""
    if value is None:
        return frozenset()
    return frozenset(m.strip() for m in str(value).split(",") if m.strip())


def _needs_update(
    have: LiveGroup, want: GroupConfig, members: Sequence[str] | None, pending: bool
) -> bool:
    """Return True if a field the operator set, or the membership, differs."""
    for key, value in want.fields:
        live_value = have.raw.get(key)
        if key == "priv":
            if _member_set(value) != _member_set(live_value):
                return True
        elif value != ("" if live_value is None else str(live_value)):
            return True
    if want.member_refs is None:
        return False
    if pending:
        return True
    return members is not None and frozenset(members) != _member_set(have.raw.get("member"))


def compute_diff(
    desired: list[GroupConfig],
    resolved_members: Mapping[str, Sequence[str]],
    current: list[LiveGroup],
    *,
    add_only: bool = False,
    managed_keys: set[str] | None = None,
    pending: set[str] | None = None,
) -> Diff:
    """Compare desired groups to live groups, keyed by ``name``.

    Args:
        desired: Groups the operator wants.
        resolved_members: ``{group name: member uids}`` for groups with ``member_refs``.
        current: Groups on the box.
        add_only: Suppress deletes.
        managed_keys: When given, only these live groups may be deleted (ADR-0018).
        pending: Group names with a member that is not live yet (plan only); a live
            group in it is an update because its membership will change.

    Returns:
        The diff.
    """
    pending = pending or set()
    desired_by_key = {g.diff_key: g for g in desired}
    current_by_key = {g.diff_key: g for g in current}
    locked_keys = {g.diff_key for g in desired if g.lock}
    diff = Diff()

    for key, want in desired_by_key.items():
        have = current_by_key.get(key)
        members = resolved_members.get(key)
        if members is not None:
            diff.members[key] = tuple(members)
        if want.lock:
            diff.locked.append((want, have))
        elif have is None:
            diff.adds.append(want)
        elif _needs_update(have, want, members, key in pending):
            diff.updates.append((have, want))

    if add_only:
        return diff
    for key, have in current_by_key.items():
        if key in locked_keys or key in desired_by_key:
            continue
        if managed_keys is not None and key not in managed_keys:
            diff.unmanaged.append(have)
        else:
            diff.deletes.append(have)
    return diff


def group_configs_from_resources(resources: list[ResourceConfig]) -> list[GroupConfig]:
    """Convert ``system.groups`` resources to :class:`GroupConfig`.

    Args:
        resources: Provider resources; other types are skipped.

    Raises:
        ValueError: On a non-dict config, an unknown key or a mistyped value.
    """
    configs: list[GroupConfig] = []
    for resource in resources:
        if resource.type != "system.groups":
            continue
        config = resource.config
        if not isinstance(config, dict):
            raise ValueError(f"system group '{resource.name}' has non-dict config")
        configs.append(_build_config(resource.name, config))
    return configs


def _build_config(resource_name: str, config: dict[str, Any]) -> GroupConfig:
    """Build one :class:`GroupConfig`."""
    unknown = sorted(set(config) - ALLOWED_KEYS)
    if unknown:
        raise ValueError(f"system group '{resource_name}' has unknown keys: {unknown}")
    name = config.get("name", resource_name)
    if not isinstance(name, str) or not name:
        raise ValueError(f"system group '{resource_name}' requires a non-empty string 'name'")
    lock = config.get("lock", False)
    if not isinstance(lock, bool):
        raise ValueError(f"system group '{resource_name}' lock must be a boolean")
    values: dict[str, str] = {}
    if "priv" in config:
        priv = config["priv"]
        if not isinstance(priv, list) or not all(isinstance(p, str) for p in priv):
            raise ValueError(f"system group '{resource_name}' priv must be a list of strings")
        values["priv"] = ",".join(sorted(set(priv)))
    for key in _STRING_FIELDS:
        if key not in config:
            continue
        value = config[key]
        if value is None:
            value = ""
        if not isinstance(value, str):
            raise ValueError(f"system group '{resource_name}' {key} must be a string")
        values[key] = value
    scope = values.get("scope")
    if scope is not None and scope not in _VALID_SCOPES:
        raise ValueError(
            f"system group '{resource_name}' scope must be one of {sorted(_VALID_SCOPES)}"
        )
    refs: tuple[str, ...] | None = None
    if "member_refs" in config:
        raw_refs = config["member_refs"]
        if not isinstance(raw_refs, list) or not all(isinstance(r, str) and r for r in raw_refs):
            raise ValueError(
                f"system group '{resource_name}' member_refs must be a list of non-empty strings"
            )
        refs = tuple(raw_refs)
    return GroupConfig(name=name, fields=tuple(sorted(values.items())), member_refs=refs, lock=lock)


def row_to_live_group(row: dict[str, Any]) -> LiveGroup:
    """Normalize a ``search`` row into a :class:`LiveGroup`."""
    return LiveGroup(
        uuid=str(row.get("uuid", "")),
        name=str(row.get("name", "")),
        gid=str(row.get("gid", "") or ""),
        raw=row,
    )


class GroupService(BaseService):
    """Service for OPNsense local-group operations via the ``auth/group`` controller."""

    def search(self) -> list[LiveGroup]:
        """Fetch the live groups."""
        ep = endpoints.AUTH_GROUP.search
        return [
            row_to_live_group(r) for r in search_rows(self.client.request(ep.method, ep.path()))
        ]

    def search_users(self) -> list[LiveUser]:
        """Fetch the live users, to resolve ``member_refs`` to uids."""
        ep = endpoints.AUTH_USER.search
        return [row_to_live(r) for r in search_rows(self.client.request(ep.method, ep.path()))]

    def add(self, group: GroupConfig, member_uids: Sequence[str] | None = None) -> dict[str, Any]:
        """Create a group; raises when OPNsense rejects it."""
        ep = endpoints.AUTH_GROUP.add
        response = self.client.request(ep.method, ep.path(), data=group.to_payload(member_uids))
        return raise_on_failed_write(response, f"add group {group.name}")  # type: ignore[no-any-return]

    def update(
        self, uuid: str, group: GroupConfig, member_uids: Sequence[str] | None = None
    ) -> dict[str, Any]:
        """Update a group by UUID; raises when OPNsense rejects it."""
        ep = endpoints.AUTH_GROUP.update
        response = self.client.request(
            ep.method, ep.path(uuid=uuid), data=group.to_payload(member_uids)
        )
        return raise_on_failed_write(response, f"update group {group.name}")  # type: ignore[no-any-return]

    def delete(self, live: LiveGroup) -> dict[str, Any]:
        """Delete a group by UUID; raises when OPNsense rejects it."""
        ep = endpoints.AUTH_GROUP.delete
        response = self.client.request(ep.method, ep.path(uuid=live.uuid))
        return raise_on_failed_write(response, f"delete group {live.name}")  # type: ignore[no-any-return]

    def compute_diff(
        self,
        desired: list[GroupConfig],
        resolved_members: Mapping[str, Sequence[str]],
        live: list[LiveGroup],
        *,
        add_only: bool = False,
        managed_keys: set[str] | None = None,
        pending: set[str] | None = None,
    ) -> Diff:
        """Service-method form of :func:`compute_diff`."""
        return compute_diff(
            desired,
            resolved_members,
            live,
            add_only=add_only,
            managed_keys=managed_keys,
            pending=pending,
        )

    def apply_diff(self, diff: Diff) -> dict[str, int]:
        """Dispatch the diff. There is no reconfigure step for groups.

        Returns:
            ``{"created": N, "updated": M, "deleted": K}``.
        """
        created = updated = deleted = 0
        for group in diff.adds:
            self.add(group, diff.members.get(group.name))
            created += 1
        for live, want in diff.updates:
            self.update(live.uuid, want, diff.members.get(want.name))
            updated += 1
        for live in diff.deletes:
            self.delete(live)
            deleted += 1
        return {"created": created, "updated": updated, "deleted": deleted}
