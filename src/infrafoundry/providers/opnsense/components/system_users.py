"""System-users component manager for OPNsense (ADR-0014, #805).

Thin orchestration over :class:`UserService`: resolves ``secret://`` URIs, checks
the password hash format, then plans, applies or destroys. Identity is the wire
``name``. The uid-0 account is never deleted.
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.types import ResourceOutcome

from ..services.system_users import (
    Diff,
    UserConfig,
    UserService,
    check_password_hashes,
    user_configs_from_resources,
)
from ._managed import managed_keys as derive_managed_keys
from ._secrets import resolve_resource_secrets
from .base import BaseComponentManager

logger = logging.getLogger(__name__)

_TYPE = "system.users"


class UserManager(BaseComponentManager):
    """Manager for OPNsense local users."""

    #: Deletes are limited to the rows InfraFoundry applied before (ADR-0018).
    DELETE_SCOPE: ClassVar[str] = "managed_set"

    def _desired(self, env_name: str, resources: list[ResourceConfig]) -> list[UserConfig]:
        """Resolve secrets, parse and validate the password hashes."""
        resolved = resolve_resource_secrets(self.config_dir, env_name, resources, _TYPE)
        configs = user_configs_from_resources(resolved)
        check_password_hashes(configs)
        return configs

    def plan(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        add_only: bool = False,
        managed_resources: list[ResourceConfig] | None = None,
        provider_name: str = "opnsense",
    ) -> Diff:
        """Compute the add/update/delete diff.

        Args:
            env_name: Active environment name.
            resources: ``system.users`` entries.
            add_only: Suppress deletes.
            managed_resources: Rows applied before (ADR-0018); ``None`` deletes every
                live user missing from YAML, except uid 0.
            provider_name: Provider identifier.
        """
        service = UserService.from_environment(env_name, provider_name, self.config_dir)
        return service.compute_diff(
            self._desired(env_name, resources),
            service.search(),
            add_only=add_only,
            managed_keys=derive_managed_keys(
                managed_resources, user_configs_from_resources, type_name=_TYPE
            ),
        )

    def apply(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        auto_approve: bool = True,
        add_only: bool = False,
        managed_resources: list[ResourceConfig] | None = None,
        provider_name: str = "opnsense",
    ) -> dict[str, Any]:
        """Apply the diff.

        Returns:
            Counts, ``resource_outcomes`` and ``unresolved_managed``.
        """
        del auto_approve
        service = UserService.from_environment(env_name, provider_name, self.config_dir)
        desired = self._desired(env_name, resources)
        unresolved: set[str] = set()
        diff = service.compute_diff(
            desired,
            service.search(),
            add_only=add_only,
            managed_keys=derive_managed_keys(
                managed_resources,
                user_configs_from_resources,
                type_name=_TYPE,
                unresolved=unresolved,
            ),
        )
        outcomes: list[ResourceOutcome] = []
        for action, names in (
            ("add", [u.name for u in diff.adds]),
            ("update", [w.name for _, w in diff.updates]),
            ("delete", [d.name for d in diff.deletes]),
        ):
            outcomes.extend(
                ResourceOutcome(address=f"opnsense_system_user.{n}", action=action, resource_name=n)
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
    ) -> dict[str, Any]:
        """Delete every live user named in ``resources``.

        Locked entries are skipped (``locked_skipped``); the uid-0 account is never
        deleted (``protected_skipped``).
        """
        del auto_approve
        service = UserService.from_environment(env_name, provider_name, self.config_dir)
        live_by_name = {u.name: u for u in service.search()}
        deleted = locked_skipped = protected_skipped = 0
        for user in user_configs_from_resources(resources):
            if user.lock:
                locked_skipped += 1
                continue
            existing = live_by_name.get(user.name)
            if existing is None:
                continue
            if existing.is_root:
                logger.warning("opnsense system.users: not destroying the uid 0 account")
                protected_skipped += 1
                continue
            service.delete(existing)
            deleted += 1
        return {
            "success": True,
            "resources_destroyed": deleted,
            "locked_skipped": locked_skipped,
            "protected_skipped": protected_skipped,
        }

    def get_resource_ids(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        provider_name: str = "opnsense",
    ) -> dict[str, str]:
        """Return ``{resource_name: uuid}`` for live users matching YAML."""
        service = UserService.from_environment(env_name, provider_name, self.config_dir)
        live_by_name = {u.name: u for u in service.search()}
        result: dict[str, str] = {}
        for resource in resources:
            if resource.type != _TYPE:
                continue
            (config,) = user_configs_from_resources([resource])
            existing = live_by_name.get(config.name)
            if existing is not None:
                result[resource.name] = existing.uuid
        return result
