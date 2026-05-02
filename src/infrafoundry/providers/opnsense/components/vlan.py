"""VLAN component manager for OPNsense (ADR-0014).

Mirrors the layout of ``components/kea_dhcp.py``: a thin orchestration layer
that loads ``VlanService`` from the environment and dispatches add/update/
delete operations. The runner (``OPNsenseDirectRunner``) instantiates this
manager once per plan/apply/destroy and delegates.
"""

from __future__ import annotations

from typing import Any

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.types import ResourceOutcome

from ..services.vlan import (
    Diff,
    LiveVlan,
    VlanService,
    vlan_configs_from_resources,
)
from .base import BaseComponentManager


class VlanManager(BaseComponentManager):
    """Manager for VLAN component operations.

    Each public method instantiates a ``VlanService`` from the environment
    and delegates. Errors propagate to the caller; the runner is responsible
    for translating exceptions into ``PlanResult.error``/``ApplyResult.error``.
    """

    # ------------------------------------------------------------------
    # Plan / apply / destroy
    # ------------------------------------------------------------------

    def plan(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        add_only: bool = False,
        provider_name: str = "opnsense",
    ) -> Diff:
        """Compute the add/update/delete diff for the given resources.

        Args:
            env_name: Active environment name.
            resources: VLAN ``ResourceConfig`` entries (filtered upstream).
            add_only: If True, suppress deletes for live VLANs not in YAML.
            provider_name: Provider identifier (defaults to ``opnsense``).

        Returns:
            ``Diff`` describing what apply would do.
        """
        service = VlanService.from_environment(env_name, provider_name, self.config_dir)
        desired = vlan_configs_from_resources(resources)
        live = service.search()
        return service.compute_diff(desired, live, add_only=add_only)

    def apply(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        auto_approve: bool = True,
        add_only: bool = False,
        provider_name: str = "opnsense",
    ) -> dict[str, Any]:
        """Apply the diff: add/update/delete VLANs and reconfigure.

        Args:
            env_name: Active environment name.
            resources: VLAN ``ResourceConfig`` entries.
            auto_approve: Currently a no-op; the diff engine itself is the gate.
            add_only: If True, suppress deletes.
            provider_name: Provider identifier (defaults to ``opnsense``).

        Returns:
            Dict with ``resources_created``, ``resources_updated``,
            ``resources_deleted`` counts and a ``resource_outcomes`` list of
            ``ResourceOutcome`` objects so destroy-time lifecycle events fire
            correctly.
        """
        del auto_approve  # diff engine is the gate; flag accepted for protocol shape
        service = VlanService.from_environment(env_name, provider_name, self.config_dir)
        desired = vlan_configs_from_resources(resources)
        live = service.search()
        diff = service.compute_diff(desired, live, add_only=add_only)

        outcomes: list[ResourceOutcome] = []
        for vlan in diff.adds:
            outcomes.append(
                ResourceOutcome(
                    address=f"opnsense_vlan.{vlan.name}",
                    action="add",
                    resource_name=vlan.name,
                )
            )

        # Map live UUIDs back to a desired-resource name so updates report
        # the operator-facing identifier.
        desired_by_key = {v.diff_key: v for v in desired}
        for live_vlan, want in diff.updates:
            outcomes.append(
                ResourceOutcome(
                    address=f"opnsense_vlan.{want.name}",
                    action="update",
                    resource_name=want.name,
                )
            )
            # Read but ignore — kept for future field-level diff reporting.
            _ = desired_by_key.get(live_vlan.diff_key)

        for live_vlan in diff.deletes:
            # Synthesize a stable name for deletes since the live record
            # came from OPNsense, not the operator's YAML.
            synthetic_name = f"vlan-{live_vlan.device}-{live_vlan.tag}"
            outcomes.append(
                ResourceOutcome(
                    address=f"opnsense_vlan.{synthetic_name}",
                    action="delete",
                    resource_name=synthetic_name,
                )
            )

        counts = service.apply_diff(diff)
        return {
            "success": True,
            "resources_created": counts["created"],
            "resources_updated": counts["updated"],
            "resources_deleted": counts["deleted"],
            "resource_outcomes": outcomes,
        }

    def destroy(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        auto_approve: bool = True,
        provider_name: str = "opnsense",
    ) -> dict[str, Any]:
        """Delete every VLAN named in ``resources`` from the live OPNsense box.

        Locked entries are honored: ``lock: true`` resources are skipped
        and counted in the response under ``locked_skipped``.

        Args:
            env_name: Active environment name.
            resources: VLAN ``ResourceConfig`` entries to destroy.
            auto_approve: Currently a no-op.
            provider_name: Provider identifier (defaults to ``opnsense``).

        Returns:
            Dict with ``resources_destroyed`` count.
        """
        del auto_approve
        service = VlanService.from_environment(env_name, provider_name, self.config_dir)
        desired = vlan_configs_from_resources(resources)
        live = service.search()
        live_by_key: dict[tuple[str, int], LiveVlan] = {v.diff_key: v for v in live}

        deleted = 0
        locked_skipped = 0
        for vlan in desired:
            if vlan.lock:
                locked_skipped += 1
                continue
            existing = live_by_key.get(vlan.diff_key)
            if existing is None:
                continue
            service.delete(existing.uuid)
            deleted += 1

        if deleted:
            service.reconfigure()

        return {
            "success": True,
            "resources_destroyed": deleted,
            "locked_skipped": locked_skipped,
        }

    # ------------------------------------------------------------------
    # State / migration helpers
    # ------------------------------------------------------------------

    def get_resource_ids(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        provider_name: str = "opnsense",
    ) -> dict[str, str]:
        """Return ``{resource_name: opnsense_uuid}`` for live resources matching ``resources``.

        Args:
            env_name: Active environment name.
            resources: VLAN ``ResourceConfig`` entries.
            provider_name: Provider identifier (defaults to ``opnsense``).

        Returns:
            Mapping from operator-facing resource name to OPNsense UUID.
            Resources without a matching live record are omitted.
        """
        service = VlanService.from_environment(env_name, provider_name, self.config_dir)
        desired = vlan_configs_from_resources(resources)
        live = service.search()
        live_by_key: dict[tuple[str, int], LiveVlan] = {v.diff_key: v for v in live}

        result: dict[str, str] = {}
        for vlan in desired:
            existing = live_by_key.get(vlan.diff_key)
            if existing is not None:
                result[vlan.name] = existing.uuid
        return result

    def list(self, env_name: str, *, provider_name: str = "opnsense") -> list[LiveVlan]:
        """Return the live VLANs on the OPNsense box for ``env_name``.

        Args:
            env_name: Active environment name.
            provider_name: Provider identifier (defaults to ``opnsense``).
        """
        service = VlanService.from_environment(env_name, provider_name, self.config_dir)
        return service.search()

    def migrate(self, env_name: str, *, provider_name: str = "opnsense") -> str:
        """Export the current VLAN configuration to InfraFoundry YAML.

        Args:
            env_name: Active environment name.
            provider_name: Provider identifier (defaults to ``opnsense``).

        Returns:
            YAML string containing the live VLANs in resource-centric form.
        """
        service = VlanService.from_environment(env_name, provider_name, self.config_dir)
        return service.export_to_yaml()
