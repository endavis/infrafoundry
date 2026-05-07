"""Alias component manager for OPNsense (ADR-0014, #747, #775).

Mirrors the layout of ``components/unbound_host_alias.py``: a thin
orchestration layer that loads ``AliasService`` from the environment and
dispatches plan/apply/destroy operations. Identity is the natural-key
alias ``name`` (OPNsense-enforced unique); no parent-UUID resolution is
required (unlike ``unbound_host_alias``), which keeps the plan/apply
surface even simpler than its peer.

The read-side ``migrate`` entry point (originally added in #747) is
preserved unchanged — ``foundry config migrate --component aliases``
keeps working against the same ``AliasService.export_to_yaml``.
"""

from __future__ import annotations

from typing import Any

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.types import ResourceOutcome

from ..services.alias import (
    AliasConfig,
    AliasService,
    Diff,
    LiveAlias,
    alias_configs_from_resources,
)
from .base import BaseComponentManager


class AliasManager(BaseComponentManager):
    """Manager for OPNsense alias component operations.

    Each public method instantiates an ``AliasService`` from the
    environment and delegates. Errors propagate to the caller; the
    runner is responsible for translating exceptions into
    ``PlanResult.error`` / ``ApplyResult.error``.
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
            resources: Alias ``ResourceConfig`` entries (filtered upstream).
            add_only: If True, suppress deletes for live aliases not in YAML.
            provider_name: Provider identifier (defaults to ``opnsense``).

        Returns:
            ``Diff`` describing what apply would do.
        """
        service = AliasService.from_environment(env_name, provider_name, self.config_dir)
        desired = alias_configs_from_resources(resources)
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
        """Apply the diff: add/update/delete aliases and reconfigure.

        Args:
            env_name: Active environment name.
            resources: Alias ``ResourceConfig`` entries.
            auto_approve: Currently a no-op; the diff engine is the gate.
            add_only: If True, suppress deletes.
            provider_name: Provider identifier (defaults to ``opnsense``).

        Returns:
            Dict with ``resources_created``, ``resources_updated``,
            ``resources_deleted`` counts and a ``resource_outcomes`` list.
        """
        del auto_approve  # diff engine is the gate; flag accepted for protocol shape
        service = AliasService.from_environment(env_name, provider_name, self.config_dir)
        desired = alias_configs_from_resources(resources)
        live = service.search()
        diff = service.compute_diff(desired, live, add_only=add_only)

        outcomes: list[ResourceOutcome] = []
        for alias in diff.adds:
            outcomes.append(
                ResourceOutcome(
                    address=f"opnsense_firewall_alias.{alias.name}",
                    action="add",
                    resource_name=alias.name,
                )
            )

        for _live_alias, want in diff.updates:
            outcomes.append(
                ResourceOutcome(
                    address=f"opnsense_firewall_alias.{want.name}",
                    action="update",
                    resource_name=want.name,
                )
            )

        for live_alias in diff.deletes:
            outcomes.append(
                ResourceOutcome(
                    address=f"opnsense_firewall_alias.{live_alias.name}",
                    action="delete",
                    resource_name=live_alias.name,
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
        """Delete every live alias whose name is in ``resources``.

        Locked entries are honored: ``lock: true`` resources are skipped
        and counted in the response under ``locked_skipped``.

        Args:
            env_name: Active environment name.
            resources: Alias ``ResourceConfig`` entries to destroy.
            auto_approve: Currently a no-op.
            provider_name: Provider identifier (defaults to ``opnsense``).

        Returns:
            Dict with ``resources_destroyed`` and ``locked_skipped`` counts.
        """
        del auto_approve
        service = AliasService.from_environment(env_name, provider_name, self.config_dir)
        desired = alias_configs_from_resources(resources)
        live = service.search()

        live_by_name: dict[str, LiveAlias] = {entry.name: entry for entry in live}

        deleted = 0
        locked_skipped = 0
        any_action = False
        for alias in desired:
            if alias.lock:
                locked_skipped += 1
                continue
            existing = live_by_name.get(alias.name)
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
        """Return ``{resource_name: opnsense_uuid}`` for live aliases matching YAML.

        Matches by the wire-name identity. The dict key is the
        operator-facing top-level ``ResourceConfig.name`` (so callers
        can address resources by their YAML name); the value is the
        OPNsense UUID for the matching live alias.

        Args:
            env_name: Active environment name.
            resources: Alias ``ResourceConfig`` entries.
            provider_name: Provider identifier (defaults to ``opnsense``).

        Returns:
            Mapping from operator-facing resource name to OPNsense UUID.
            Resources without a matching live record are omitted.
        """
        service = AliasService.from_environment(env_name, provider_name, self.config_dir)
        desired = _desired_with_resource_names(resources)
        live = service.search()
        live_by_name: dict[str, LiveAlias] = {entry.name: entry for entry in live}

        result: dict[str, str] = {}
        for resource_name, alias in desired:
            existing = live_by_name.get(alias.name)
            if existing is not None:
                result[resource_name] = existing.uuid
        return result

    def list(self, env_name: str, *, provider_name: str = "opnsense") -> list[LiveAlias]:
        """Return the live aliases on the OPNsense box.

        Args:
            env_name: Active environment name.
            provider_name: Provider identifier (defaults to ``opnsense``).
        """
        service = AliasService.from_environment(env_name, provider_name, self.config_dir)
        return service.search()

    def migrate(self, env_name: str, *, provider_name: str = "opnsense") -> str:
        """Export the current aliases to InfraFoundry YAML.

        Preserves the read-side surface from #747 unchanged so
        ``foundry config migrate --component aliases`` keeps working.

        Args:
            env_name: Active environment name.
            provider_name: Provider identifier (defaults to ``opnsense``).

        Returns:
            YAML string containing the live aliases in resource-centric
            form. Operator-facing ``name`` is the alias name verbatim.
        """
        service = AliasService.from_environment(env_name, provider_name, self.config_dir)
        return service.export_to_yaml()


def _desired_with_resource_names(
    resources: list[ResourceConfig],
) -> list[tuple[str, AliasConfig]]:
    """Pair each ``AliasConfig`` with its operator-facing top-level name.

    ``alias_configs_from_resources`` builds ``AliasConfig`` instances
    keyed on the wire identity ``config.name``. ``get_resource_ids``
    needs to return a ``{resource_name: uuid}`` dict where the keys are
    the operator-facing top-level YAML names — which can diverge from
    ``config.name`` once an operator renames after migrate. This helper
    walks ``resources`` in lockstep with the parser to keep both names
    available for the caller.
    """
    paired: list[tuple[str, AliasConfig]] = []
    parsed = alias_configs_from_resources(resources)
    parsed_iter = iter(parsed)
    for resource in resources:
        if resource.type != "aliases":
            continue
        cfg = next(parsed_iter, None)
        if cfg is None:
            break
        paired.append((resource.name, cfg))
    return paired
