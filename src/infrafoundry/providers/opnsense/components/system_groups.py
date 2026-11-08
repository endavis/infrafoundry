"""System-groups component manager for OPNsense (ADR-0014, #805).

Groups own their membership. ``member_refs`` name ``system.users`` resources; the
manager maps ref -> sibling resource -> wire name -> live uid (from ``auth/user``).
It follows the sibling-resource pattern of the kea reservation managers:
users are applied first, and group deletes run in their own phase before users
are deleted (``SPLIT_DELETE_PHASE``).
"""

from __future__ import annotations

from typing import Any, ClassVar

from infrafoundry.core.exceptions import ReferenceValidationError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.types import ResourceOutcome

from ..services.system_groups import (
    Diff,
    GroupConfig,
    GroupService,
    group_configs_from_resources,
)
from ..validators._xref import build_xref_index, resolve_xref
from ._managed import managed_keys as derive_managed_keys
from .base import BaseComponentManager

_TYPE = "system.groups"
_USER_TYPE = "system.users"


class GroupManager(BaseComponentManager):
    """Manager for OPNsense local groups."""

    #: Runner threads the ``system.users`` slice in as ``sibling_resources``.
    SIBLING_RESOURCE_TYPE: ClassVar[str | None] = _USER_TYPE

    #: Deletes are limited to the rows InfraFoundry applied before (ADR-0018).
    DELETE_SCOPE: ClassVar[str] = "managed_set"

    #: Groups are deleted before the users they reference.
    SPLIT_DELETE_PHASE: ClassVar[bool] = True

    @staticmethod
    def _resolve_members(
        service: GroupService,
        desired: list[GroupConfig],
        sibling_resources: list[ResourceConfig] | None,
        *,
        allow_pending: bool,
    ) -> tuple[dict[str, tuple[str, ...]], set[str]]:
        """Resolve every group's ``member_refs`` to live uids.

        Args:
            service: Group service, used to read live users.
            desired: Parsed groups.
            sibling_resources: ``system.users`` resources from YAML.
            allow_pending: Plan only. A user in YAML but not live yet marks the group
                pending (the box assigns the uid on add).

        Returns:
            ``(members, pending)``: uids per group name, and groups with an unknown member.

        Raises:
            ReferenceValidationError: A ref names no ``system.users`` resource, or
                (apply) a user that is not live.
        """
        with_refs = [g for g in desired if g.member_refs is not None]
        if not with_refs:
            return {}, set()
        index = build_xref_index(list(sibling_resources or []))
        live_uid = {u.name: u.uid for u in service.search_users()}
        members: dict[str, tuple[str, ...]] = {}
        pending: set[str] = set()
        for group in with_refs:
            uids: list[str] = []
            for ref in group.member_refs or ():
                user = resolve_xref(ref, _USER_TYPE, index, current_plugin="system")
                if user is None:
                    raise ReferenceValidationError(
                        f"system group '{group.name}' member_refs entry {ref!r} "
                        f"does not name a system.users resource"
                    )
                wire = user.config.get("name", user.name)
                uid = live_uid.get(str(wire))
                if uid is None:
                    if not allow_pending:
                        raise ReferenceValidationError(
                            f"system group '{group.name}' member {ref!r} is not a live user"
                        )
                    pending.add(group.name)
                    continue
                uids.append(uid)
            members[group.name] = tuple(uids)
        return members, pending

    def plan(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        add_only: bool = False,
        managed_resources: list[ResourceConfig] | None = None,
        managed_sibling_resources: list[ResourceConfig] | None = None,
        provider_name: str = "opnsense",
        sibling_resources: list[ResourceConfig] | None = None,
    ) -> Diff:
        """Compute the add/update/delete diff.

        Args:
            env_name: Active environment name.
            resources: ``system.groups`` entries.
            add_only: Suppress deletes.
            managed_resources: Rows applied before (ADR-0018).
            managed_sibling_resources: Accepted for runner symmetry; unused.
            provider_name: Provider identifier.
            sibling_resources: ``system.users`` entries, to resolve ``member_refs``.

        Raises:
            ReferenceValidationError: A ref names no ``system.users`` resource.
        """
        del managed_sibling_resources
        service = GroupService.from_environment(env_name, provider_name, self.config_dir)
        desired = group_configs_from_resources(resources)
        members, pending = self._resolve_members(
            service, desired, sibling_resources, allow_pending=True
        )
        return service.compute_diff(
            desired,
            members,
            service.search(),
            add_only=add_only,
            managed_keys=derive_managed_keys(
                managed_resources, group_configs_from_resources, type_name=_TYPE
            ),
            pending=pending,
        )

    def apply(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        auto_approve: bool = True,
        add_only: bool = False,
        deletes_only: bool = False,
        managed_resources: list[ResourceConfig] | None = None,
        managed_sibling_resources: list[ResourceConfig] | None = None,
        provider_name: str = "opnsense",
        sibling_resources: list[ResourceConfig] | None = None,
    ) -> dict[str, Any]:
        """Apply the diff.

        With ``deletes_only`` (the runner's delete phase) only deletes run and member
        refs are not resolved.

        Raises:
            ReferenceValidationError: A ref names no resource, or a user that is not live.
        """
        del auto_approve, managed_sibling_resources
        service = GroupService.from_environment(env_name, provider_name, self.config_dir)
        desired = group_configs_from_resources(resources)
        members: dict[str, tuple[str, ...]] = {}
        if not deletes_only:
            members, _ = self._resolve_members(
                service, desired, sibling_resources, allow_pending=False
            )
        unresolved: set[str] = set()
        diff = service.compute_diff(
            desired,
            members,
            service.search(),
            add_only=add_only,
            managed_keys=derive_managed_keys(
                managed_resources,
                group_configs_from_resources,
                type_name=_TYPE,
                unresolved=unresolved,
            ),
        )
        if deletes_only:
            diff.adds = []
            diff.updates = []
        outcomes: list[ResourceOutcome] = []
        for action, names in (
            ("add", [g.name for g in diff.adds]),
            ("update", [w.name for _, w in diff.updates]),
            ("delete", [d.name for d in diff.deletes]),
        ):
            outcomes.extend(
                ResourceOutcome(
                    address=f"opnsense_system_group.{n}", action=action, resource_name=n
                )
                for n in names
            )
        counts = service.apply_diff(diff)
        return {
            "success": True,
            "resources_created": counts["created"],
            "resources_updated": counts["updated"],
            "resources_deleted": counts["deleted"],
            "resource_outcomes": outcomes,
            "unresolved_managed": sorted(unresolved),
        }

    def destroy(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        auto_approve: bool = True,
        provider_name: str = "opnsense",
        sibling_resources: list[ResourceConfig] | None = None,
    ) -> dict[str, Any]:
        """Delete every live group named in ``resources``; locked entries are skipped."""
        del auto_approve, sibling_resources
        service = GroupService.from_environment(env_name, provider_name, self.config_dir)
        live_by_name = {g.name: g for g in service.search()}
        deleted = locked_skipped = 0
        for group in group_configs_from_resources(resources):
            if group.lock:
                locked_skipped += 1
                continue
            existing = live_by_name.get(group.name)
            if existing is None:
                continue
            service.delete(existing)
            deleted += 1
        return {"success": True, "resources_destroyed": deleted, "locked_skipped": locked_skipped}

    def get_resource_ids(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        provider_name: str = "opnsense",
        sibling_resources: list[ResourceConfig] | None = None,
    ) -> dict[str, str]:
        """Return ``{resource_name: uuid}`` for live groups matching YAML."""
        del sibling_resources
        service = GroupService.from_environment(env_name, provider_name, self.config_dir)
        live_by_name = {g.name: g for g in service.search()}
        result: dict[str, str] = {}
        for resource in resources:
            if resource.type != _TYPE:
                continue
            (config,) = group_configs_from_resources([resource])
            existing = live_by_name.get(config.name)
            if existing is not None:
                result[resource.name] = existing.uuid
        return result
