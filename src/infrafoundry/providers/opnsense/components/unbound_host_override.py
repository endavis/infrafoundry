"""Unbound host-override component manager for OPNsense (ADR-0014, #748, #776).

Mirrors the layout of ``components/unbound_host_alias.py``: a thin
orchestration layer that loads ``UnboundHostOverrideService`` from the
environment and dispatches plan/apply/destroy operations. Identity is the
natural-key tuple ``(hostname, domain, rr)`` per the ADR-0014 amendment for
this component (#776); no parent-UUID resolution is required (unlike
``unbound_host_alias``).

The read-side ``migrate`` entry point (originally added in #748) is preserved
unchanged — ``foundry config migrate --component unbound_host_override``
keeps working against the same ``UnboundHostOverrideService.export_to_yaml``.

Reconfigure semantics (#776):

This manager **does not** call ``service.reconfigure()`` directly. Instead it
declares ``FINALIZATION_HOOK = "unbound_reconfigure"`` and
``OPNsenseDirectRunner`` fires the matching hook from
``OPNsenseProvider.get_finalization_hooks()`` exactly once after the apply
loop. The same hook is shared by ``UnboundHostAliasManager`` and
``UnboundForwardManager``, so a multi-unbound apply produces a single
``unbound/service/reconfigure`` call instead of up to three.
"""

from __future__ import annotations

from typing import Any, ClassVar

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.types import ResourceOutcome

from ..services.unbound_host_override import (
    Diff,
    LiveUnboundHostOverride,
    UnboundHostOverrideService,
    unbound_host_override_configs_from_resources,
)
from .base import BaseComponentManager


class UnboundHostOverrideManager(BaseComponentManager):
    """Manager for OPNsense Unbound host-override component operations.

    Each public method instantiates an ``UnboundHostOverrideService`` from
    the environment and delegates. Errors propagate to the caller; the
    runner is responsible for translating exceptions into
    ``PlanResult.error`` / ``ApplyResult.error``.
    """

    #: Runner-level finalization hook key (#776). The host-alias and
    #: forward managers declare the same value so all three unbound
    #: components share a single ``unbound/service/reconfigure`` call
    #: per apply.
    FINALIZATION_HOOK: ClassVar[str] = "unbound_reconfigure"

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
            resources: Host-override ``ResourceConfig`` entries (filtered upstream).
            add_only: If True, suppress deletes for live overrides not in YAML.
            provider_name: Provider identifier (defaults to ``opnsense``).

        Returns:
            ``Diff`` describing what apply would do.
        """
        service = UnboundHostOverrideService.from_environment(
            env_name, provider_name, self.config_dir
        )
        desired = unbound_host_override_configs_from_resources(resources)
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
        """Apply the diff: add/update/delete host overrides.

        Does **not** call ``service.reconfigure()`` directly — the runner
        fires the ``unbound_reconfigure`` finalization hook once after
        every component has applied (#776). This coalesces the reconfigure
        across all three unbound managers (host_override / host_alias /
        forward).

        Args:
            env_name: Active environment name.
            resources: Host-override ``ResourceConfig`` entries.
            auto_approve: Currently a no-op; the diff engine is the gate.
            add_only: If True, suppress deletes.
            provider_name: Provider identifier (defaults to ``opnsense``).

        Returns:
            Dict with ``resources_created``, ``resources_updated``,
            ``resources_deleted`` counts and a ``resource_outcomes`` list.
        """
        del auto_approve  # diff engine is the gate; flag accepted for protocol shape
        service = UnboundHostOverrideService.from_environment(
            env_name, provider_name, self.config_dir
        )
        desired = unbound_host_override_configs_from_resources(resources)
        live = service.search()
        diff = service.compute_diff(desired, live, add_only=add_only)

        outcomes: list[ResourceOutcome] = []
        for override in diff.adds:
            outcomes.append(
                ResourceOutcome(
                    address=f"opnsense_unbound_host_override.{override.name}",
                    action="add",
                    resource_name=override.name,
                )
            )

        for _live_override, want in diff.updates:
            outcomes.append(
                ResourceOutcome(
                    address=f"opnsense_unbound_host_override.{want.name}",
                    action="update",
                    resource_name=want.name,
                )
            )

        for live_override in diff.deletes:
            synthetic_name = _synthetic_name(live_override)
            outcomes.append(
                ResourceOutcome(
                    address=f"opnsense_unbound_host_override.{synthetic_name}",
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
        """Delete every live override whose tuple is in ``resources``.

        Locked entries are honored: ``lock: true`` resources are skipped
        and counted in the response under ``locked_skipped``.

        Args:
            env_name: Active environment name.
            resources: Host-override ``ResourceConfig`` entries to destroy.
            auto_approve: Currently a no-op.
            provider_name: Provider identifier (defaults to ``opnsense``).

        Returns:
            Dict with ``resources_destroyed`` and ``locked_skipped`` counts.
        """
        del auto_approve
        service = UnboundHostOverrideService.from_environment(
            env_name, provider_name, self.config_dir
        )
        desired = unbound_host_override_configs_from_resources(resources)
        live = service.search()

        live_by_key: dict[tuple[str, str, str], LiveUnboundHostOverride] = {
            entry.diff_key: entry for entry in live
        }

        deleted = 0
        locked_skipped = 0
        any_action = False
        for override in desired:
            if override.lock:
                locked_skipped += 1
                continue
            existing = live_by_key.get(override.diff_key)
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
        """Return ``{resource_name: opnsense_uuid}`` for live overrides matching YAML.

        Matches by the natural-key ``(hostname, domain, rr)`` tuple — the
        operator-facing ``name`` is only used as the dict key in the
        return value.

        Args:
            env_name: Active environment name.
            resources: Host-override ``ResourceConfig`` entries.
            provider_name: Provider identifier (defaults to ``opnsense``).

        Returns:
            Mapping from operator-facing resource name to OPNsense UUID.
            Resources without a matching live record are omitted.
        """
        service = UnboundHostOverrideService.from_environment(
            env_name, provider_name, self.config_dir
        )
        desired = unbound_host_override_configs_from_resources(resources)
        live = service.search()
        live_by_key: dict[tuple[str, str, str], LiveUnboundHostOverride] = {
            entry.diff_key: entry for entry in live
        }

        result: dict[str, str] = {}
        for override in desired:
            existing = live_by_key.get(override.diff_key)
            if existing is not None:
                result[override.name] = existing.uuid
        return result

    def list(
        self, env_name: str, *, provider_name: str = "opnsense"
    ) -> list[LiveUnboundHostOverride]:
        """Return the live host overrides on the OPNsense box.

        Args:
            env_name: Active environment name.
            provider_name: Provider identifier (defaults to ``opnsense``).
        """
        service = UnboundHostOverrideService.from_environment(
            env_name, provider_name, self.config_dir
        )
        return service.search()

    def migrate(self, env_name: str, *, provider_name: str = "opnsense") -> str:
        """Export the current Unbound host overrides to InfraFoundry YAML.

        Preserves the read-side surface from #748 unchanged so
        ``foundry config migrate --component unbound_host_override`` keeps
        working.

        Args:
            env_name: Active environment name.
            provider_name: Provider identifier (defaults to ``opnsense``).

        Returns:
            YAML string containing the live host overrides in
            resource-centric form. Operator-facing ``name`` is synthesized
            from ``hostname.domain`` (with ``-<rr>`` suffix when ``rr`` is
            non-default).
        """
        service = UnboundHostOverrideService.from_environment(
            env_name, provider_name, self.config_dir
        )
        return service.export_to_yaml()


def _synthetic_name(override: LiveUnboundHostOverride) -> str:
    """Build a stable synthetic name for a live override.

    Used when emitting ``ResourceOutcome`` for deletes — the live record
    carries no operator-facing name. Mirrors
    ``services.unbound_host_override._synthesize_name`` so plan output and
    migrated YAML use the same convention.
    """
    parts: list[str] = []
    if override.hostname:
        parts.append(override.hostname)
    if override.domain:
        parts.append(override.domain.replace(".", "-"))
    if override.rr and override.rr != "A":
        parts.append(override.rr)
    if not parts:
        return override.uuid.lower()
    return "-".join(parts).lower()
