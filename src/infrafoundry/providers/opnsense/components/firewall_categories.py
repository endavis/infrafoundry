"""Firewall category component manager for OPNsense (ADR-0014, #1286).

Manages ``firewall.categories`` through
:class:`~..services.firewall_categories.FirewallCategoryService`. Deletes use the
managed-set scope (ADR-0018). The provider's ``infrafoundry`` marker category is never
part of a diff.

References to a category are uuids, so add order does not matter. Only delete order
does: the type is registered after rules, NAT and aliases, so the runner deletes it
after them without a split delete phase. A category the box reports in use (including
by models this provider does not manage) is kept with a warning and reported as
unresolved so it stays managed and the next apply retries. Categories need no
reconfigure.
"""

from __future__ import annotations

from typing import Any, ClassVar

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.types import ResourceOutcome

from ..services.firewall_categories import (
    Diff,
    FirewallCategoryConfig,
    FirewallCategoryService,
    LiveFirewallCategory,
    category_configs_from_resources,
    category_name_of,
    compute_diff,
)
from ._managed import managed_keys as derive_managed_keys
from ._migrate_names import env_provider_resources, reserved_names
from .base import BaseComponentManager

_TYPE = "firewall.categories"


class FirewallCategoryManager(BaseComponentManager):
    """Manager for ``firewall.categories`` operations."""

    #: Deletes are limited to the rows InfraFoundry applied before (ADR-0018).
    DELETE_SCOPE: ClassVar[str] = "managed_set"

    @staticmethod
    def _desired(resources: list[ResourceConfig]) -> list[FirewallCategoryConfig]:
        return category_configs_from_resources(resources)

    def _diff(
        self,
        service: FirewallCategoryService,
        desired: list[FirewallCategoryConfig],
        *,
        add_only: bool,
        managed_resources: list[ResourceConfig] | None,
        unresolved: set[str] | None = None,
    ) -> Diff:
        keys = derive_managed_keys(
            managed_resources,
            category_configs_from_resources,
            type_name=_TYPE,
            unresolved=unresolved,
        )
        return compute_diff(desired, service.search(), add_only=add_only, managed_keys=keys)

    def plan(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        add_only: bool = False,
        managed_resources: list[ResourceConfig] | None = None,
        provider_name: str = "opnsense",
    ) -> Diff:
        """Compute the diff for the given categories.

        Args:
            env_name: Active environment name.
            resources: ``firewall.categories`` resources.
            add_only: If True, suppress deletes.
            managed_resources: Rows InfraFoundry applied before (ADR-0018).
            provider_name: Provider identifier.

        Returns:
            The diff apply would execute. Whether the box accepts a delete is only
            known at apply time, so ``blocked`` is empty here.
        """
        service = FirewallCategoryService.from_environment(env_name, provider_name, self.config_dir)
        return self._diff(
            service,
            self._desired(resources),
            add_only=add_only,
            managed_resources=managed_resources,
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
        """Apply the diff: add, update and delete categories.

        Args:
            env_name: Active environment name.
            resources: ``firewall.categories`` resources.
            auto_approve: Currently a no-op.
            add_only: If True, suppress deletes.
            managed_resources: Rows InfraFoundry applied before (ADR-0018).
            provider_name: Provider identifier.

        Returns:
            Counts, ``resource_outcomes``, ``warnings`` and ``unresolved_managed``. A
            delete the box refused (category in use) is in neither the deleted count
            nor the outcomes; its row stays in ``unresolved_managed``.
        """
        del auto_approve
        service = FirewallCategoryService.from_environment(env_name, provider_name, self.config_dir)
        unresolved: set[str] = set()
        diff = self._diff(
            service,
            self._desired(resources),
            add_only=add_only,
            managed_resources=managed_resources,
            unresolved=unresolved,
        )
        counts = service.apply_diff(diff)
        blocked = {live.name for live, _ in diff.blocked}
        for row in managed_resources or []:
            if category_name_of(row.name, row.config) in blocked:
                unresolved.add(row.name)

        outcomes = [
            ResourceOutcome(
                address=f"opnsense_firewall_category.{c.name}",
                action="add",
                resource_name=c.name,
            )
            for c in diff.adds
        ]
        outcomes += [
            ResourceOutcome(
                address=f"opnsense_firewall_category.{w.name}",
                action="update",
                resource_name=w.name,
            )
            for _, w in diff.updates
        ]
        outcomes += [
            ResourceOutcome(
                address=f"opnsense_firewall_category.{d.name}",
                action="delete",
                resource_name=d.name,
            )
            for d in diff.deletes
        ]
        return {
            "success": True,
            "resources_created": counts["created"],
            "resources_updated": counts["updated"],
            "resources_deleted": counts["deleted"],
            "resource_outcomes": outcomes,
            "unresolved_managed": sorted(unresolved),
            "warnings": list(diff.warnings),
        }

    def destroy(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        auto_approve: bool = True,
        provider_name: str = "opnsense",
    ) -> dict[str, Any]:
        """Delete the live categories named in ``resources``.

        Locked categories are skipped (counted); one the box reports in use is kept
        with a warning. The ``infrafoundry`` marker is never touched.

        Args:
            env_name: Active environment name.
            resources: ``firewall.categories`` resources to destroy.
            auto_approve: Currently a no-op.
            provider_name: Provider identifier.

        Returns:
            ``resources_destroyed``, ``locked_skipped`` and ``warnings``.
        """
        del auto_approve
        service = FirewallCategoryService.from_environment(env_name, provider_name, self.config_dir)
        desired = self._desired(resources)
        wanted = {c.diff_key for c in desired if not c.lock}
        live: list[LiveFirewallCategory] = [x for x in service.search() if x.diff_key in wanted]
        diff = compute_diff([], live)
        counts = service.apply_diff(diff)
        return {
            "success": True,
            "resources_destroyed": counts["deleted"],
            "locked_skipped": sum(1 for c in desired if c.lock),
            "warnings": list(diff.warnings),
        }

    def get_resource_ids(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        provider_name: str = "opnsense",
    ) -> dict[str, str]:
        """Return ``{resource_name: uuid}`` for live categories matching ``resources``.

        The ``infrafoundry`` marker is never returned.

        Args:
            env_name: Active environment name.
            resources: ``firewall.categories`` resources.
            provider_name: Provider identifier.
        """
        service = FirewallCategoryService.from_environment(env_name, provider_name, self.config_dir)
        live = {x.name: x.uuid for x in service.search() if x.name != "infrafoundry"}
        return {
            r.name: live[category_name_of(r.name, r.config)]
            for r in resources
            if r.type == _TYPE and category_name_of(r.name, r.config) in live
        }

    def list(self, env_name: str, *, provider_name: str = "opnsense") -> list[LiveFirewallCategory]:
        """Return the live categories on the OPNsense box.

        Args:
            env_name: Active environment name.
            provider_name: Provider identifier.
        """
        service = FirewallCategoryService.from_environment(env_name, provider_name, self.config_dir)
        return service.search()

    def migrate(self, env_name: str, *, provider_name: str = "opnsense") -> str:
        """Export the live categories to InfraFoundry YAML.

        Args:
            env_name: Active environment name.
            provider_name: Provider identifier.

        Returns:
            Nested-format YAML. The marker is skipped; a handle already used by
            another resource in the environment gets a ``-2``, ``-3`` ... suffix.
        """
        service = FirewallCategoryService.from_environment(env_name, provider_name, self.config_dir)
        resources = env_provider_resources(self.config_dir, env_name, provider_name)
        reserved = reserved_names(resources, exclude_types={_TYPE})
        return service.export_to_yaml(reserved=reserved)
