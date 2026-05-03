"""NAT rule component manager for OPNsense (ADR-0014, #713).

Mirrors the layout of ``components/vlan.py``: a thin orchestration layer
that loads ``NATRuleService`` from the environment and dispatches add/
update/delete operations across both supported kinds (outbound + 1:1).

Identity is description-prefix-based per the issue plan; the manager
takes no part in matching — that is entirely the diff engine's job in
``services/nat_rule.py``.
"""

from __future__ import annotations

from typing import Any

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.types import ResourceOutcome

from ..services.nat_rule import (
    Diff,
    LiveNATRule,
    NATRuleKind,
    NATRuleService,
    nat_rule_configs_from_resources,
)
from .base import BaseComponentManager


class NATRuleManager(BaseComponentManager):
    """Manager for NAT-rule component operations.

    Each public method instantiates a ``NATRuleService`` from the
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
            resources: NAT rule ``ResourceConfig`` entries (filtered upstream).
            add_only: If True, suppress deletes for managed live rules
                not in YAML. Unmanaged live rules are always ignored.
            provider_name: Provider identifier (defaults to ``opnsense``).

        Returns:
            ``Diff`` describing what apply would do.
        """
        service = NATRuleService.from_environment(env_name, provider_name, self.config_dir)
        desired = nat_rule_configs_from_resources(resources)
        live = service.search_all()
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
        """Apply the diff: add/update/delete rules and applyChanges.

        Args:
            env_name: Active environment name.
            resources: NAT rule ``ResourceConfig`` entries.
            auto_approve: Currently a no-op; the diff engine itself is
                the gate.
            add_only: If True, suppress deletes.
            provider_name: Provider identifier (defaults to ``opnsense``).

        Returns:
            Dict with ``resources_created``, ``resources_updated``,
            ``resources_deleted`` counts and a ``resource_outcomes`` list.
        """
        del auto_approve  # diff engine is the gate; flag accepted for protocol shape
        service = NATRuleService.from_environment(env_name, provider_name, self.config_dir)
        desired = nat_rule_configs_from_resources(resources)
        live = service.search_all()
        diff = service.compute_diff(desired, live, add_only=add_only)

        outcomes: list[ResourceOutcome] = []
        for rule in diff.adds:
            outcomes.append(
                ResourceOutcome(
                    address=f"opnsense_nat_rule.{rule.name}",
                    action="add",
                    resource_name=rule.name,
                )
            )

        for _live_rule, want in diff.updates:
            outcomes.append(
                ResourceOutcome(
                    address=f"opnsense_nat_rule.{want.name}",
                    action="update",
                    resource_name=want.name,
                )
            )

        for live_rule in diff.deletes:
            # Synthesize a stable name for deletes; managed_name is non-None
            # because the diff engine filters out unmanaged rows entirely.
            synthetic_name = live_rule.managed_name or f"nat-rule-{live_rule.uuid}"
            outcomes.append(
                ResourceOutcome(
                    address=f"opnsense_nat_rule.{synthetic_name}",
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
        """Delete every managed NAT rule named in ``resources``.

        Locked entries are honored: ``lock: true`` resources are skipped
        and counted in the response under ``locked_skipped``.

        Args:
            env_name: Active environment name.
            resources: NAT rule ``ResourceConfig`` entries to destroy.
            auto_approve: Currently a no-op.
            provider_name: Provider identifier (defaults to ``opnsense``).

        Returns:
            Dict with ``resources_destroyed`` and ``locked_skipped`` counts.
        """
        del auto_approve
        service = NATRuleService.from_environment(env_name, provider_name, self.config_dir)
        desired = nat_rule_configs_from_resources(resources)
        live = service.search_all()

        # Index by per-kind name so destroy honors the same isolation as
        # the diff engine.
        live_by_key: dict[tuple[NATRuleKind, str], LiveNATRule] = {
            (entry.kind, entry.managed_name): entry
            for entry in live
            if entry.managed_name is not None
        }

        deleted = 0
        locked_skipped = 0
        kinds_touched: set[NATRuleKind] = set()
        for rule in desired:
            if rule.lock:
                locked_skipped += 1
                continue
            existing = live_by_key.get((rule.kind, rule.name))
            if existing is None:
                continue
            service.delete(existing.uuid, existing.kind)
            kinds_touched.add(existing.kind)
            deleted += 1

        for kind in kinds_touched:
            service.apply_changes(kind)

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
        """Return ``{resource_name: opnsense_uuid}`` for live managed rules.

        Args:
            env_name: Active environment name.
            resources: NAT rule ``ResourceConfig`` entries.
            provider_name: Provider identifier (defaults to ``opnsense``).

        Returns:
            Mapping from operator-facing resource name to OPNsense UUID.
            Resources without a matching live record are omitted. When
            two rules of different kinds share a name, the mapping uses
            the operator-facing ``name`` as the key — collisions are
            prevented at the YAML level by the resource-name validator.
        """
        service = NATRuleService.from_environment(env_name, provider_name, self.config_dir)
        desired = nat_rule_configs_from_resources(resources)
        live = service.search_all()
        live_by_key: dict[tuple[NATRuleKind, str], LiveNATRule] = {
            (entry.kind, entry.managed_name): entry
            for entry in live
            if entry.managed_name is not None
        }

        result: dict[str, str] = {}
        for rule in desired:
            existing = live_by_key.get((rule.kind, rule.name))
            if existing is not None:
                result[rule.name] = existing.uuid
        return result

    def list(self, env_name: str, *, provider_name: str = "opnsense") -> list[LiveNATRule]:
        """Return the live NAT rules on the OPNsense box (both kinds).

        Args:
            env_name: Active environment name.
            provider_name: Provider identifier (defaults to ``opnsense``).
        """
        service = NATRuleService.from_environment(env_name, provider_name, self.config_dir)
        return service.search_all()

    def migrate(self, env_name: str, *, provider_name: str = "opnsense") -> str:
        """Export the current managed NAT rules to InfraFoundry YAML.

        Args:
            env_name: Active environment name.
            provider_name: Provider identifier (defaults to ``opnsense``).

        Returns:
            YAML string containing the live managed rules in
            resource-centric form.
        """
        service = NATRuleService.from_environment(env_name, provider_name, self.config_dir)
        return service.export_to_yaml()
