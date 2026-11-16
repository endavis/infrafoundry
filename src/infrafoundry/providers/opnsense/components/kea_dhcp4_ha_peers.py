"""Kea DHCPv4 high-availability peer manager for OPNsense (#1392).

Manages ``kea.dhcp4.ha_peers`` through
:class:`~..services.kea_dhcp4_ha.KeaHAPeerService`. Deletes use the managed-set scope
(ADR-0018). The shared ``kea_reconfigure`` finalization hook reconfigures once per apply;
``destroy`` reconfigures directly when it deleted a row, because the hook does not fire
on destroy. Nothing references a peer by UUID, so there is no split delete phase: deletes
run in the forward pass, still before the ``kea.dhcp4.ha`` settings write.
"""

from __future__ import annotations

from typing import Any, ClassVar

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.types import ResourceOutcome

from ..services.kea_dhcp4_ha import (
    Diff,
    KeaHAPeerConfig,
    KeaHAPeerService,
    LiveKeaHAPeer,
    compute_diff,
    peer_configs_from_resources,
)
from ._managed import managed_keys as derive_managed_keys
from ._migrate_names import env_provider_resources, reserved_names
from .base import BaseComponentManager

_TYPE = "kea.dhcp4.ha_peers"


class KeaDHCPv4HAPeerManager(BaseComponentManager):
    """Manager for ``kea.dhcp4.ha_peers`` operations."""

    #: Deletes are limited to the rows InfraFoundry applied before (ADR-0018).
    DELETE_SCOPE: ClassVar[str] = "managed_set"
    FINALIZATION_HOOK: ClassVar[str] = "kea_reconfigure"

    def _diff(
        self,
        service: KeaHAPeerService,
        desired: list[KeaHAPeerConfig],
        *,
        add_only: bool,
        managed_resources: list[ResourceConfig] | None,
        unresolved: set[str] | None = None,
    ) -> Diff:
        keys = derive_managed_keys(
            managed_resources,
            peer_configs_from_resources,
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
        """Compute the diff for the given peers.

        Args:
            env_name: Active environment name.
            resources: ``kea.dhcp4.ha_peers`` resources.
            add_only: If True, suppress deletes.
            managed_resources: Rows InfraFoundry applied before (ADR-0018).
            provider_name: Provider identifier.
        """
        service = KeaHAPeerService.from_environment(env_name, provider_name, self.config_dir)
        return self._diff(
            service,
            peer_configs_from_resources(resources),
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
        """Apply the diff: add, update and delete peers.

        Reconfigure is not called here; the ``kea_reconfigure`` hook fires.
        """
        del auto_approve
        service = KeaHAPeerService.from_environment(env_name, provider_name, self.config_dir)
        unresolved: set[str] = set()
        diff = self._diff(
            service,
            peer_configs_from_resources(resources),
            add_only=add_only,
            managed_resources=managed_resources,
            unresolved=unresolved,
        )
        counts = service.apply_diff(diff)
        outcomes = [
            ResourceOutcome(
                address=f"opnsense_kea_ha_peer.{c.name}",
                action="add",
                resource_name=c.name,
            )
            for c in diff.adds
        ]
        outcomes += [
            ResourceOutcome(
                address=f"opnsense_kea_ha_peer.{w.name}",
                action="update",
                resource_name=w.name,
            )
            for _, w in diff.updates
        ]
        outcomes += [
            ResourceOutcome(
                address=f"opnsense_kea_ha_peer.{d.diff_key}",
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
        """Delete the live peers named in ``resources``.

        Locked peers are skipped (counted). The finalization hook does not fire on
        destroy, so this reconfigures directly when something was deleted.
        """
        del auto_approve
        service = KeaHAPeerService.from_environment(env_name, provider_name, self.config_dir)
        desired = peer_configs_from_resources(resources)
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
        """Return ``{resource_name: uuid}`` for live peers matching ``resources``."""
        service = KeaHAPeerService.from_environment(env_name, provider_name, self.config_dir)
        live = {x.diff_key: x.uuid for x in service.search()}
        ids: dict[str, str] = {}
        for config in peer_configs_from_resources(resources):
            if config.diff_key in live:
                ids[config.name] = live[config.diff_key]
        return ids

    def list(self, env_name: str, *, provider_name: str = "opnsense") -> list[LiveKeaHAPeer]:
        """Return the live peers on the OPNsense box."""
        service = KeaHAPeerService.from_environment(env_name, provider_name, self.config_dir)
        return service.search()

    def migrate(self, env_name: str, *, provider_name: str = "opnsense") -> str:
        """Export the live peers to InfraFoundry YAML."""
        service = KeaHAPeerService.from_environment(env_name, provider_name, self.config_dir)
        resources = env_provider_resources(self.config_dir, env_name, provider_name)
        reserved = reserved_names(resources, exclude_types={_TYPE})
        return service.export_to_yaml(reserved=reserved)
