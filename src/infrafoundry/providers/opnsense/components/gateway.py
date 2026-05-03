"""Gateway component manager for OPNsense (ADR-0014, #721).

Mirrors the layout of ``components/vlan.py`` and ``components/nat_rule.py``:
a thin orchestration layer that loads ``GatewayService`` from the environment
and dispatches add/update/delete operations.

Identity is the natural-key ``name`` per the issue plan; the manager takes
no part in matching — that is entirely the diff engine's job in
``services/gateway.py``.
"""

from __future__ import annotations

from typing import Any

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.types import ResourceOutcome

from ..services.gateway import (
    Diff,
    GatewayService,
    LiveGateway,
    gateway_configs_from_resources,
)
from .base import BaseComponentManager


class GatewayManager(BaseComponentManager):
    """Manager for gateway component operations.

    Each public method instantiates a ``GatewayService`` from the
    environment and delegates. Errors propagate to the caller; the runner
    is responsible for translating exceptions into ``PlanResult.error``/
    ``ApplyResult.error``.
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
            resources: Gateway ``ResourceConfig`` entries (filtered upstream).
            add_only: If True, suppress deletes for managed live gateways
                not in YAML. Dynamic gateways are always ignored.
            provider_name: Provider identifier (defaults to ``opnsense``).

        Returns:
            ``Diff`` describing what apply would do.
        """
        service = GatewayService.from_environment(env_name, provider_name, self.config_dir)
        desired = gateway_configs_from_resources(resources)
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
        """Apply the diff: add/update/delete gateways and reconfigure.

        Args:
            env_name: Active environment name.
            resources: Gateway ``ResourceConfig`` entries.
            auto_approve: Currently a no-op; the diff engine itself is
                the gate.
            add_only: If True, suppress deletes.
            provider_name: Provider identifier (defaults to ``opnsense``).

        Returns:
            Dict with ``resources_created``, ``resources_updated``,
            ``resources_deleted`` counts and a ``resource_outcomes`` list.
        """
        del auto_approve  # diff engine is the gate; flag accepted for protocol shape
        service = GatewayService.from_environment(env_name, provider_name, self.config_dir)
        desired = gateway_configs_from_resources(resources)
        live = service.search()
        diff = service.compute_diff(desired, live, add_only=add_only)

        outcomes: list[ResourceOutcome] = []
        for gateway in diff.adds:
            outcomes.append(
                ResourceOutcome(
                    address=f"opnsense_gateway.{gateway.name}",
                    action="add",
                    resource_name=gateway.name,
                )
            )

        for _live_gw, want in diff.updates:
            outcomes.append(
                ResourceOutcome(
                    address=f"opnsense_gateway.{want.name}",
                    action="update",
                    resource_name=want.name,
                )
            )

        for live_gw in diff.deletes:
            # Synthesize a stable name for deletes; the diff engine filters
            # dynamic gateways so ``name`` is always operator-meaningful here.
            synthetic_name = live_gw.name or f"gateway-{live_gw.uuid}"
            outcomes.append(
                ResourceOutcome(
                    address=f"opnsense_gateway.{synthetic_name}",
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
        """Delete every managed gateway named in ``resources``.

        Locked entries are honored: ``lock: true`` resources are skipped
        and counted in the response under ``locked_skipped``.

        Args:
            env_name: Active environment name.
            resources: Gateway ``ResourceConfig`` entries to destroy.
            auto_approve: Currently a no-op.
            provider_name: Provider identifier (defaults to ``opnsense``).

        Returns:
            Dict with ``resources_destroyed`` and ``locked_skipped`` counts.
        """
        del auto_approve
        service = GatewayService.from_environment(env_name, provider_name, self.config_dir)
        desired = gateway_configs_from_resources(resources)
        live = service.search()

        # Index live by name; only managed gateways are eligible for destroy.
        live_by_name: dict[str, LiveGateway] = {
            entry.name: entry for entry in live if entry.is_managed
        }

        deleted = 0
        locked_skipped = 0
        any_action = False
        for gateway in desired:
            if gateway.lock:
                locked_skipped += 1
                continue
            existing = live_by_name.get(gateway.name)
            if existing is None:
                continue
            service.delete(existing.uuid)
            deleted += 1
            any_action = True

        if any_action:
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
        """Return ``{resource_name: opnsense_uuid}`` for live managed gateways.

        Args:
            env_name: Active environment name.
            resources: Gateway ``ResourceConfig`` entries.
            provider_name: Provider identifier (defaults to ``opnsense``).

        Returns:
            Mapping from operator-facing resource name to OPNsense UUID.
            Resources without a matching live record are omitted.
        """
        service = GatewayService.from_environment(env_name, provider_name, self.config_dir)
        desired = gateway_configs_from_resources(resources)
        live = service.search()
        live_by_name: dict[str, LiveGateway] = {
            entry.name: entry for entry in live if entry.is_managed
        }

        result: dict[str, str] = {}
        for gateway in desired:
            existing = live_by_name.get(gateway.name)
            if existing is not None:
                result[gateway.name] = existing.uuid
        return result

    def list(self, env_name: str, *, provider_name: str = "opnsense") -> list[LiveGateway]:
        """Return the live gateways on the OPNsense box (managed + dynamic).

        Args:
            env_name: Active environment name.
            provider_name: Provider identifier (defaults to ``opnsense``).
        """
        service = GatewayService.from_environment(env_name, provider_name, self.config_dir)
        return service.search()

    def migrate(self, env_name: str, *, provider_name: str = "opnsense") -> str:
        """Export the current managed gateways to InfraFoundry YAML.

        Args:
            env_name: Active environment name.
            provider_name: Provider identifier (defaults to ``opnsense``).

        Returns:
            YAML string containing the live managed gateways in
            resource-centric form.
        """
        service = GatewayService.from_environment(env_name, provider_name, self.config_dir)
        return service.export_to_yaml()
