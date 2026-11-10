"""Tailscale advertised-subnet component manager for OPNsense (#787).

Manages ``tailscale.subnets`` through
:class:`~..services.tailscale_subnets.TailscaleSubnetService`. Deletes use the
managed-set scope (ADR-0018). The shared ``tailscale_reconfigure`` finalization hook
reconfigures once per apply; ``destroy`` reconfigures directly when it deleted a row,
because the hook does not fire on destroy. A 404 at plan means the plugin is not
installed yet: every declared row becomes an add, with a warning. A 404 at apply raises.
"""

from __future__ import annotations

from typing import Any, ClassVar

from infrafoundry.core.exceptions import APIError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.types import ResourceOutcome

from ..services.tailscale_subnets import (
    Diff,
    LiveTailscaleSubnet,
    TailscaleSubnetConfig,
    TailscaleSubnetService,
    compute_diff,
    subnet_configs_from_resources,
)
from ._managed import managed_keys as derive_managed_keys
from ._migrate_names import env_provider_resources, reserved_names
from .base import BaseComponentManager
from .tailscale_settings import PLUGIN_MISSING_WARNING

_TYPE = "tailscale.subnets"


class TailscaleSubnetManager(BaseComponentManager):
    """Manager for ``tailscale.subnets`` operations."""

    #: Deletes are limited to the rows InfraFoundry applied before (ADR-0018).
    DELETE_SCOPE: ClassVar[str] = "managed_set"
    FINALIZATION_HOOK: ClassVar[str] = "tailscale_reconfigure"

    def _diff(
        self,
        service: TailscaleSubnetService,
        desired: list[TailscaleSubnetConfig],
        *,
        add_only: bool,
        managed_resources: list[ResourceConfig] | None,
        tolerate_missing_plugin: bool,
        unresolved: set[str] | None = None,
    ) -> Diff:
        missing = False
        try:
            live = service.search()
        except APIError as exc:
            if not (tolerate_missing_plugin and exc.status_code == 404):
                raise
            live, missing = [], True
        keys = derive_managed_keys(
            managed_resources,
            subnet_configs_from_resources,
            type_name=_TYPE,
            unresolved=unresolved,
        )
        diff = compute_diff(desired, live, add_only=add_only, managed_keys=keys)
        if missing:
            diff.warnings.append(PLUGIN_MISSING_WARNING)
        return diff

    def plan(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        add_only: bool = False,
        managed_resources: list[ResourceConfig] | None = None,
        provider_name: str = "opnsense",
    ) -> Diff:
        """Compute the diff for the given subnets.

        Args:
            env_name: Active environment name.
            resources: ``tailscale.subnets`` resources.
            add_only: If True, suppress deletes.
            managed_resources: Rows InfraFoundry applied before (ADR-0018).
            provider_name: Provider identifier.
        """
        service = TailscaleSubnetService.from_environment(env_name, provider_name, self.config_dir)
        return self._diff(
            service,
            subnet_configs_from_resources(resources),
            add_only=add_only,
            managed_resources=managed_resources,
            tolerate_missing_plugin=True,
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
        """Apply the diff: add, update and delete subnets.

        Reconfigure is not called here; the ``tailscale_reconfigure`` hook fires.
        """
        del auto_approve
        service = TailscaleSubnetService.from_environment(env_name, provider_name, self.config_dir)
        unresolved: set[str] = set()
        diff = self._diff(
            service,
            subnet_configs_from_resources(resources),
            add_only=add_only,
            managed_resources=managed_resources,
            tolerate_missing_plugin=False,
            unresolved=unresolved,
        )
        counts = service.apply_diff(diff)
        outcomes = [
            ResourceOutcome(
                address=f"opnsense_tailscale_subnet.{c.name}",
                action="add",
                resource_name=c.name,
            )
            for c in diff.adds
        ]
        outcomes += [
            ResourceOutcome(
                address=f"opnsense_tailscale_subnet.{w.name}",
                action="update",
                resource_name=w.name,
            )
            for _, w in diff.updates
        ]
        outcomes += [
            ResourceOutcome(
                address=f"opnsense_tailscale_subnet.{d.diff_key}",
                action="delete",
                resource_name=d.diff_key,
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
        """Delete the live subnets named in ``resources``.

        Locked subnets are skipped (counted). The finalization hook does not fire on
        destroy, so this reconfigures directly when something was deleted.
        """
        del auto_approve
        service = TailscaleSubnetService.from_environment(env_name, provider_name, self.config_dir)
        desired = subnet_configs_from_resources(resources)
        wanted = {c.diff_key for c in desired if not c.lock}
        live = [x for x in service.search() if x.diff_key in wanted]
        diff = compute_diff([], live)
        counts = service.apply_diff(diff)
        if counts["deleted"]:
            service.reconfigure()
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
        """Return ``{resource_name: uuid}`` for live subnets matching ``resources``."""
        service = TailscaleSubnetService.from_environment(env_name, provider_name, self.config_dir)
        live = {x.diff_key: x.uuid for x in service.search()}
        ids: dict[str, str] = {}
        for config in subnet_configs_from_resources(resources):
            if config.diff_key in live:
                ids[config.name] = live[config.diff_key]
        return ids

    def list(self, env_name: str, *, provider_name: str = "opnsense") -> list[LiveTailscaleSubnet]:
        """Return the live subnets on the OPNsense box."""
        service = TailscaleSubnetService.from_environment(env_name, provider_name, self.config_dir)
        return service.search()

    def migrate(self, env_name: str, *, provider_name: str = "opnsense") -> str:
        """Export the live subnets to InfraFoundry YAML."""
        service = TailscaleSubnetService.from_environment(env_name, provider_name, self.config_dir)
        resources = env_provider_resources(self.config_dir, env_name, provider_name)
        reserved = reserved_names(resources, exclude_types={_TYPE})
        return service.export_to_yaml(reserved=reserved)
