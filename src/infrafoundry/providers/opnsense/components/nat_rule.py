"""NAT rule component manager for OPNsense (ADR-0014, #713).

Mirrors the layout of ``components/vlan.py``: a thin orchestration layer
that loads ``NATRuleService`` from the environment and dispatches add/
update/delete operations across both supported kinds (outbound + 1:1).

Identity is description-prefix-based per the issue plan; the manager
takes no part in matching — that is entirely the diff engine's job in
``services/nat_rule.py``.
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from infrafoundry.core.exceptions import APIError, PartialExtractionError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.types import ResourceOutcome

from ..services._nested_emit import emit_nested_list_yaml
from ..services.config_backup import ConfigBackupService
from ..services.nat_rule import (
    SNAT_MODES_INERT,
    Diff,
    LiveNATRule,
    NATRuleConfig,
    NATRuleKind,
    NATRuleService,
    max_live_sequence,
    nat_rule_configs_from_resources,
)
from ..services.nat_rule_legacy import parse_legacy_outbound_rules
from ._migrate_names import env_provider_resources, reserved_names
from .base import BaseComponentManager

logger = logging.getLogger(__name__)

#: Legacy rules start this far above the highest live outbound sequence.
_LEGACY_SEQUENCE_GAP = 100

_PARTIAL_HEADER = "# Legacy rule fields not exported — review before apply:\n"


def _snat_mode_warnings(
    service: NATRuleService,
    desired: list[NATRuleConfig],
    sibling_resources: list[ResourceConfig] | None,
) -> list[str]:
    """Warn when declared outbound rules sit under a mode that ignores them (#1333).

    The effective mode is the declared ``firewall.source_nat.snat_mode`` when there
    is one, otherwise the live mode. An unreadable live mode (before 26.1) is silent.
    """
    outbound = [rule for rule in desired if rule.kind == "outbound" and rule.enabled]
    if not outbound:
        return []
    mode: Any = None
    if sibling_resources:
        declared = sibling_resources[0].config.get("snat_mode")
        if isinstance(declared, str):
            mode = declared
    if mode is None:
        mode = service.get_snat_mode()
    if not isinstance(mode, str) or mode not in SNAT_MODES_INERT:
        return []
    return [
        f"firewall.nat: {len(outbound)} outbound rule(s) declared but the OPNsense outbound "
        f"NAT mode is '{mode}'; manual outbound rules only take effect in 'hybrid' or "
        "'advanced' mode. Declare opnsense.firewall.source_nat.snat_mode: hybrid to manage it."
    ]


class NATRuleManager(BaseComponentManager):
    """Manager for NAT-rule component operations.

    Each public method instantiates a ``NATRuleService`` from the
    environment and delegates. Errors propagate to the caller; the runner
    is responsible for translating exceptions into ``PlanResult.error``/
    ``ApplyResult.error``.
    """

    #: The diff engine deletes only objects carrying InfraFoundry's marker, so no
    #: managed set is needed (ADR-0018).
    DELETE_SCOPE: ClassVar[str] = "marker"

    #: Resource type threaded in as ``sibling_resources``: the declared outbound NAT
    #: mode, so the plan warning uses it instead of the live mode (#1333).
    SIBLING_RESOURCE_TYPE: ClassVar[str | None] = "firewall.source_nat"

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
        sibling_resources: list[ResourceConfig] | None = None,
    ) -> Diff:
        """Compute the add/update/delete diff for the given resources.

        Args:
            env_name: Active environment name.
            resources: NAT rule ``ResourceConfig`` entries (filtered upstream).
            add_only: If True, suppress deletes for managed live rules
                not in YAML. Unmanaged live rules are always ignored.
            provider_name: Provider identifier (defaults to ``opnsense``).
            sibling_resources: ``firewall.source_nat`` resources from YAML.

        Returns:
            ``Diff`` describing what apply would do.
        """
        service = NATRuleService.from_environment(env_name, provider_name, self.config_dir)
        desired = nat_rule_configs_from_resources(resources)
        live = service.search_all()
        diff = service.compute_diff(desired, live, add_only=add_only)
        diff.warnings.extend(_snat_mode_warnings(service, desired, sibling_resources))
        return diff

    def apply(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        auto_approve: bool = True,
        add_only: bool = False,
        deletes_only: bool = False,
        provider_name: str = "opnsense",
        sibling_resources: list[ResourceConfig] | None = None,
    ) -> dict[str, Any]:
        """Apply the diff: add/update/delete rules and applyChanges.

        Args:
            env_name: Active environment name.
            resources: NAT rule ``ResourceConfig`` entries.
            auto_approve: Currently a no-op; the diff engine itself is
                the gate.
            add_only: If True, suppress deletes.
            deletes_only: If True, only delete: the runner's delete phase, run
                before the adds and updates (#1269).
            provider_name: Provider identifier (defaults to ``opnsense``).
            sibling_resources: ``firewall.source_nat`` resources from YAML.

        Returns:
            Dict with ``resources_created``, ``resources_updated``,
            ``resources_deleted`` counts and a ``resource_outcomes`` list.
        """
        del auto_approve  # diff engine is the gate; flag accepted for protocol shape
        service = NATRuleService.from_environment(env_name, provider_name, self.config_dir)
        desired = nat_rule_configs_from_resources(resources)
        live = service.search_all()
        diff = service.compute_diff(desired, live, add_only=add_only)

        if deletes_only:
            diff.adds = []
            diff.updates = []

        outcomes: list[ResourceOutcome] = []
        desired_keys = {(rule.kind, rule.name) for rule in desired}
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
            # A duplicate copy of a still-desired rule is named by uuid so the kept
            # resource's on_destroy handlers do not fire (#1339).
            is_duplicate = (live_rule.kind, live_rule.managed_name) in desired_keys
            synthetic_name = (
                f"nat-rule-{live_rule.uuid}"
                if is_duplicate or live_rule.managed_name is None
                else live_rule.managed_name
            )
            outcomes.append(
                ResourceOutcome(
                    address=f"opnsense_nat_rule.{synthetic_name}",
                    action="delete",
                    resource_name=synthetic_name,
                )
            )

        counts = service.apply_diff(diff)
        result: dict[str, Any] = {
            "success": True,
            "resources_created": counts["created"],
            "resources_updated": counts["updated"],
            "resources_deleted": counts["deleted"],
            "resource_outcomes": outcomes,
        }
        if not deletes_only:
            warnings = _snat_mode_warnings(service, desired, sibling_resources)
            if warnings:
                result["warnings"] = warnings
        return result

    def destroy(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        auto_approve: bool = True,
        provider_name: str = "opnsense",
        sibling_resources: list[ResourceConfig] | None = None,
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
        del auto_approve, sibling_resources
        service = NATRuleService.from_environment(env_name, provider_name, self.config_dir)
        desired = nat_rule_configs_from_resources(resources)
        live = service.search_all()

        # Index by per-kind name so destroy honors the same isolation as
        # the diff engine.
        copies_by_key: dict[tuple[NATRuleKind, str], list[LiveNATRule]] = {}
        for entry in live:
            if entry.managed_name is not None:
                copies_by_key.setdefault((entry.kind, entry.managed_name), []).append(entry)

        deleted = 0
        locked_skipped = 0
        kinds_touched: set[NATRuleKind] = set()
        for rule in desired:
            if rule.lock:
                locked_skipped += 1
                continue
            # Every copy goes, not just one (#1339).
            for existing in copies_by_key.get((rule.kind, rule.name), []):
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
        sibling_resources: list[ResourceConfig] | None = None,
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
        del sibling_resources
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

    def migrate(
        self,
        env_name: str,
        *,
        provider_name: str = "opnsense",
        include_legacy: bool = False,
    ) -> str:
        """Export the current managed NAT rules to InfraFoundry YAML.

        Args:
            env_name: Active environment name.
            provider_name: Provider identifier (defaults to ``opnsense``).
            include_legacy: Also export the legacy ``<nat><outbound><rule>`` rules read
                from the configuration backup (#1509). Read-only: one GET of the backup.
                They are numbered after the highest live outbound ``sequence``.

        Returns:
            YAML string containing the live managed rules (and, with ``include_legacy``,
            the mapped legacy outbound rules) in resource-centric form.

        Raises:
            PartialExtractionError: With ``include_legacy``, when a legacy rule or field
                could not be exported or the backup could not be read. The error carries
                the YAML that was produced, with the issues in a header comment.
        """
        service = NATRuleService.from_environment(env_name, provider_name, self.config_dir)
        if not include_legacy:
            return service.export_to_yaml()

        live = service.search_all_tolerant()
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
            exported = parse_legacy_outbound_rules(
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

        yaml_text = emit_nested_list_yaml("firewall.nat", entries)
        if not issues:
            return yaml_text

        header = _PARTIAL_HEADER + "".join(f"# - {issue}\n" for issue in issues)
        raise PartialExtractionError(
            f"{len(issues)} legacy rule field(s) could not be exported",
            yaml_content=header + yaml_text,
            issues=issues,
        )
