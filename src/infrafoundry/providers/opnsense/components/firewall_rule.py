"""Firewall-rule component manager for OPNsense (ADR-0014, ADR-0015, #742).

Mirrors the layout of ``components/nat_rule.py`` minus the per-kind
dispatch — ``firewall_rules`` has a single MVC controller, so plan/apply
operate on a flat list of rules.

Identity is description-suffix-based per ADR-0015 §"Identity and
ownership"; the manager takes no part in matching — that is entirely the
diff engine's job in ``services/firewall_rule.py``.
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from infrafoundry.core.exceptions import APIError, PartialExtractionError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.types import ResourceOutcome

from ..services._nested_emit import emit_nested_list_yaml
from ..services.config_backup import ConfigBackupService
from ..services.firewall_rule import (
    Diff,
    FirewallRuleService,
    LiveFirewallRule,
    firewall_rule_configs_from_resources,
    max_live_sequence,
)
from ..services.firewall_rule_legacy import parse_legacy_rules
from ._migrate_names import env_provider_resources, reserved_names
from .base import BaseComponentManager

logger = logging.getLogger(__name__)

#: Legacy rules start this far above the highest live sequence.
_LEGACY_SEQUENCE_GAP = 100

_PARTIAL_HEADER = "# Legacy rule fields not exported — review before apply:\n"


class FirewallRuleManager(BaseComponentManager):
    """Manager for firewall-rule component operations.

    Each public method instantiates a ``FirewallRuleService`` from the
    environment and delegates. Errors propagate to the caller; the
    runner is responsible for translating exceptions into
    ``PlanResult.error`` / ``ApplyResult.error``.
    """

    #: The diff engine deletes only objects carrying InfraFoundry's marker, so no
    #: managed set is needed (ADR-0018).
    DELETE_SCOPE: ClassVar[str] = "marker"

    #: The runner deletes in a separate phase before this type's adds and updates,
    #: so a row is deleted while the objects it depends on are still live (#1269).
    SPLIT_DELETE_PHASE: ClassVar[bool] = True

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
            resources: Firewall-rule ``ResourceConfig`` entries
                (filtered upstream).
            add_only: If True, suppress deletes for managed live rules
                not in YAML. Unmanaged live rules are always ignored.
            provider_name: Provider identifier (defaults to
                ``opnsense``).

        Returns:
            ``Diff`` describing what apply would do.
        """
        service = FirewallRuleService.from_environment(env_name, provider_name, self.config_dir)
        desired = firewall_rule_configs_from_resources(resources)
        live = service.search()
        return service.compute_diff(desired, live, add_only=add_only)

    def apply(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        auto_approve: bool = True,
        add_only: bool = False,
        deletes_only: bool = False,
        provider_name: str = "opnsense",
    ) -> dict[str, Any]:
        """Apply the diff: add/update/delete rules and applyChanges.

        Args:
            env_name: Active environment name.
            resources: Firewall-rule ``ResourceConfig`` entries.
            auto_approve: Currently a no-op; the diff engine is the gate.
            add_only: If True, suppress deletes.
            deletes_only: If True, only delete: the runner's delete phase, run
                before the adds and updates (#1269).
            provider_name: Provider identifier (defaults to
                ``opnsense``).

        Returns:
            Dict with ``resources_created``, ``resources_updated``,
            ``resources_deleted`` counts and a ``resource_outcomes``
            list.
        """
        del auto_approve  # diff engine is the gate
        service = FirewallRuleService.from_environment(env_name, provider_name, self.config_dir)
        desired = firewall_rule_configs_from_resources(resources)
        live = service.search()
        diff = service.compute_diff(desired, live, add_only=add_only)

        if deletes_only:
            diff.adds = []
            diff.updates = []

        outcomes: list[ResourceOutcome] = []
        for rule in diff.adds:
            outcomes.append(
                ResourceOutcome(
                    address=f"opnsense_firewall_rule.{rule.name}",
                    action="add",
                    resource_name=rule.name,
                )
            )

        for _, want in diff.updates:
            outcomes.append(
                ResourceOutcome(
                    address=f"opnsense_firewall_rule.{want.name}",
                    action="update",
                    resource_name=want.name,
                )
            )

        for live_rule in diff.deletes:
            # Synthesize a stable name for deletes; managed_name is
            # non-None because the diff engine filters out unmanaged
            # rows entirely.
            synthetic_name = live_rule.managed_name or f"firewall-rule-{live_rule.uuid}"
            outcomes.append(
                ResourceOutcome(
                    address=f"opnsense_firewall_rule.{synthetic_name}",
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
        """Delete every managed firewall rule named in ``resources``.

        Locked entries are honored: ``lock: true`` resources are
        skipped and counted in the response under ``locked_skipped``.

        Args:
            env_name: Active environment name.
            resources: Firewall-rule ``ResourceConfig`` entries to
                destroy.
            auto_approve: Currently a no-op.
            provider_name: Provider identifier (defaults to
                ``opnsense``).

        Returns:
            Dict with ``resources_destroyed`` and ``locked_skipped``
            counts.
        """
        del auto_approve
        service = FirewallRuleService.from_environment(env_name, provider_name, self.config_dir)
        desired = firewall_rule_configs_from_resources(resources)
        live = service.search()

        live_by_name: dict[str, LiveFirewallRule] = {
            entry.managed_name: entry for entry in live if entry.managed_name is not None
        }

        deleted = 0
        locked_skipped = 0
        for rule in desired:
            if rule.lock:
                locked_skipped += 1
                continue
            existing = live_by_name.get(rule.name)
            if existing is None:
                continue
            service.delete(existing.uuid)
            deleted += 1

        if deleted:
            service.apply_changes()

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
        """Return ``{resource_name: opnsense_uuid}`` for live managed rules."""
        service = FirewallRuleService.from_environment(env_name, provider_name, self.config_dir)
        desired = firewall_rule_configs_from_resources(resources)
        live = service.search()
        live_by_name: dict[str, LiveFirewallRule] = {
            entry.managed_name: entry for entry in live if entry.managed_name is not None
        }

        result: dict[str, str] = {}
        for rule in desired:
            existing = live_by_name.get(rule.name)
            if existing is not None:
                result[rule.name] = existing.uuid
        return result

    def list(self, env_name: str, *, provider_name: str = "opnsense") -> list[LiveFirewallRule]:
        """Return the live firewall rules on the OPNsense box."""
        service = FirewallRuleService.from_environment(env_name, provider_name, self.config_dir)
        return service.search()

    def migrate(
        self,
        env_name: str,
        *,
        provider_name: str = "opnsense",
        include_legacy: bool = False,
    ) -> str:
        """Export the current managed firewall rules to InfraFoundry YAML.

        Args:
            env_name: Active environment name.
            provider_name: Provider identifier (defaults to ``opnsense``).
            include_legacy: Also export the legacy ``<filter><rule>`` rules read from the
                configuration backup (#1497). Read-only: one GET of the backup. The legacy
                rules are numbered after the highest live ``sequence`` so they keep their
                order and sort behind the rules already on the box.

        Returns:
            YAML string containing the live managed rules (and, with ``include_legacy``,
            the mapped legacy rules) in resource-centric form.

        Raises:
            PartialExtractionError: With ``include_legacy``, when a legacy rule or field
                could not be exported or the backup could not be read. The error carries
                the YAML that was produced, with the issues in a header comment.
        """
        service = FirewallRuleService.from_environment(env_name, provider_name, self.config_dir)
        if not include_legacy:
            return service.export_to_yaml()

        live = service.search_tolerant()
        entries = service.export_entries(live)
        resources = env_provider_resources(self.config_dir, env_name, provider_name)
        reserved = reserved_names(resources, exclude_types=frozenset()) | {
            str(entry["name"]) for entry in entries
        }

        issues: list[str] = []
        try:
            backup = ConfigBackupService.from_environment(
                env_name, provider_name, self.config_dir
            ).download_config()
            exported = parse_legacy_rules(
                backup,
                reserved=reserved,
                sequence_start=max_live_sequence(live) + _LEGACY_SEQUENCE_GAP,
            )
        except APIError as exc:
            logger.warning("Legacy rules not read: %s", exc.message)
            issues.append(
                "legacy rules not read: the configuration backup could not be downloaded or "
                "parsed; the API key needs the backup-download privilege"
            )
        else:
            entries.extend(exported.entries)
            issues.extend(str(issue) for issue in exported.issues)

        yaml_text = emit_nested_list_yaml("firewall.rules", entries)
        if not issues:
            return yaml_text

        header = _PARTIAL_HEADER + "".join(f"# - {issue}\n" for issue in issues)
        raise PartialExtractionError(
            f"{len(issues)} legacy rule field(s) could not be exported",
            yaml_content=header + yaml_text,
            issues=issues,
        )
