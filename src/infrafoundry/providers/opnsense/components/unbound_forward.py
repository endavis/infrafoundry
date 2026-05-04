"""Unbound forward component manager for OPNsense (ADR-0014, #724).

Mirrors the layout of ``components/static_route.py``: a thin orchestration
layer that loads ``UnboundForwardService`` from the environment and
dispatches add/update/delete operations.

Identity is the natural-key ``(type, domain, server, port)`` tuple per the
issue plan; the manager takes no part in matching — that is entirely the
diff engine's job in ``services/unbound_forward.py``. The operator-facing
``name`` is metadata only and is used for ``ResourceOutcome.address``
synthesis.
"""

from __future__ import annotations

from typing import Any

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.types import ResourceOutcome

from ..services.unbound_forward import (
    Diff,
    LiveUnboundForward,
    UnboundForwardService,
    unbound_forward_configs_from_resources,
)
from .base import BaseComponentManager


class UnboundForwardManager(BaseComponentManager):
    """Manager for Unbound forward component operations.

    Each public method instantiates an ``UnboundForwardService`` from
    the environment and delegates. Errors propagate to the caller; the
    runner is responsible for translating exceptions into
    ``PlanResult.error``/``ApplyResult.error``.
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
            resources: Forward ``ResourceConfig`` entries (filtered upstream).
            add_only: If True, suppress deletes for live forwards not in YAML.
            provider_name: Provider identifier (defaults to ``opnsense``).

        Returns:
            ``Diff`` describing what apply would do.
        """
        service = UnboundForwardService.from_environment(env_name, provider_name, self.config_dir)
        desired = unbound_forward_configs_from_resources(resources)
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
        """Apply the diff: add/update/delete forwards and reconfigure.

        Args:
            env_name: Active environment name.
            resources: Forward ``ResourceConfig`` entries.
            auto_approve: Currently a no-op; the diff engine is the gate.
            add_only: If True, suppress deletes.
            provider_name: Provider identifier (defaults to ``opnsense``).

        Returns:
            Dict with ``resources_created``, ``resources_updated``,
            ``resources_deleted`` counts and a ``resource_outcomes`` list.
        """
        del auto_approve
        service = UnboundForwardService.from_environment(env_name, provider_name, self.config_dir)
        desired = unbound_forward_configs_from_resources(resources)
        live = service.search()
        diff = service.compute_diff(desired, live, add_only=add_only)

        outcomes: list[ResourceOutcome] = []
        for forward in diff.adds:
            outcomes.append(
                ResourceOutcome(
                    address=f"opnsense_unbound_forward.{forward.name}",
                    action="add",
                    resource_name=forward.name,
                )
            )

        for _live_forward, want in diff.updates:
            outcomes.append(
                ResourceOutcome(
                    address=f"opnsense_unbound_forward.{want.name}",
                    action="update",
                    resource_name=want.name,
                )
            )

        for live_forward in diff.deletes:
            synthetic_name = _synthetic_name(live_forward)
            outcomes.append(
                ResourceOutcome(
                    address=f"opnsense_unbound_forward.{synthetic_name}",
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
        """Delete every live forward whose tuple is in ``resources``.

        Locked entries are honored: ``lock: true`` resources are skipped
        and counted in the response under ``locked_skipped``.

        Args:
            env_name: Active environment name.
            resources: Forward ``ResourceConfig`` entries to destroy.
            auto_approve: Currently a no-op.
            provider_name: Provider identifier (defaults to ``opnsense``).

        Returns:
            Dict with ``resources_destroyed`` and ``locked_skipped`` counts.
        """
        del auto_approve
        service = UnboundForwardService.from_environment(env_name, provider_name, self.config_dir)
        desired = unbound_forward_configs_from_resources(resources)
        live = service.search()

        live_by_key: dict[tuple[str, str, str, str], LiveUnboundForward] = {
            entry.diff_key: entry for entry in live
        }

        deleted = 0
        locked_skipped = 0
        any_action = False
        for forward in desired:
            if forward.lock:
                locked_skipped += 1
                continue
            existing = live_by_key.get(forward.diff_key)
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
        """Return ``{resource_name: opnsense_uuid}`` for live forwards matching YAML.

        Matches by the natural-key ``(type, domain, server, port)`` tuple
        — the operator-facing ``name`` is only used as the dict key in
        the return value.

        Args:
            env_name: Active environment name.
            resources: Forward ``ResourceConfig`` entries.
            provider_name: Provider identifier (defaults to ``opnsense``).

        Returns:
            Mapping from operator-facing resource name to OPNsense UUID.
            Resources without a matching live record are omitted.
        """
        service = UnboundForwardService.from_environment(env_name, provider_name, self.config_dir)
        desired = unbound_forward_configs_from_resources(resources)
        live = service.search()
        live_by_key: dict[tuple[str, str, str, str], LiveUnboundForward] = {
            entry.diff_key: entry for entry in live
        }

        result: dict[str, str] = {}
        for forward in desired:
            existing = live_by_key.get(forward.diff_key)
            if existing is not None:
                result[forward.name] = existing.uuid
        return result

    def list(self, env_name: str, *, provider_name: str = "opnsense") -> list[LiveUnboundForward]:
        """Return the live forwards on the OPNsense box.

        Args:
            env_name: Active environment name.
            provider_name: Provider identifier (defaults to ``opnsense``).
        """
        service = UnboundForwardService.from_environment(env_name, provider_name, self.config_dir)
        return service.search()

    def migrate(self, env_name: str, *, provider_name: str = "opnsense") -> str:
        """Export the current forwards to InfraFoundry YAML.

        Args:
            env_name: Active environment name.
            provider_name: Provider identifier (defaults to ``opnsense``).

        Returns:
            YAML string containing the live forwards in resource-centric
            form. Operator-facing ``name`` is synthesized from the
            ``(type, domain, server, port)`` natural-key tuple.
        """
        service = UnboundForwardService.from_environment(env_name, provider_name, self.config_dir)
        return service.export_to_yaml()


def _synthetic_name(forward: LiveUnboundForward) -> str:
    """Build a stable synthetic name for a live forward.

    Used when emitting ``ResourceOutcome`` for deletes — the live record
    carries no operator-facing name. Mirrors
    ``services.unbound_forward._synthesize_name`` so plan output and
    migrated YAML use the same convention.
    """
    domain_part = forward.domain.replace(".", "-") if forward.domain else "global"
    server_part = forward.server.replace(":", "-").replace(".", "-")
    return f"forward-{forward.type}-{domain_part}-{server_part}-{forward.port}".lower()
