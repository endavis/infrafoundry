"""Unbound host-alias component manager for OPNsense (ADR-0014, #724, #776).

Mirrors the layout of ``components/static_route.py``: a thin orchestration
layer that loads ``UnboundHostAliasService`` from the environment and
dispatches add/update/delete operations.

The unique aspect of this manager is that the ``host`` field in YAML
references a parent ``unbound_host_override`` by *name* (the operator's
own resource name or the live override's hostname), and the wire
representation requires the parent's UUID. The manager resolves
``host_name`` → UUID at plan/apply time by reading
``searchHostOverride`` rows; if no live override matches, the manager
raises ``ReferenceValidationError`` so the failure is visible at plan
time rather than as a server-side validation error at apply time.

Reconfigure semantics (#776):

This manager **does not** call ``service.reconfigure()`` directly from
``apply``. Instead it declares ``FINALIZATION_HOOK = "unbound_reconfigure"``
and ``OPNsenseDirectRunner`` fires the matching hook from
``OPNsenseProvider.get_finalization_hooks()`` exactly once after the apply
loop. The same hook is shared by ``UnboundHostOverrideManager`` and
``UnboundForwardManager``, so a multi-unbound apply produces a single
``unbound/service/reconfigure`` call instead of up to three. ``destroy``
still calls ``service.reconfigure()`` inline because the runner's hook
plumbing fires on apply only (per ADR-0014 §"Finalization hooks").
"""

from __future__ import annotations

from typing import Any, ClassVar

from infrafoundry.core.exceptions import ReferenceValidationError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.types import ResourceOutcome

from ..services.unbound_host_alias import (
    Diff,
    LiveUnboundHostAlias,
    UnboundHostAliasConfig,
    UnboundHostAliasService,
    unbound_host_alias_configs_from_resources,
)
from .base import BaseComponentManager


class UnboundHostAliasManager(BaseComponentManager):
    """Manager for Unbound host-alias component operations.

    Each public method instantiates an ``UnboundHostAliasService`` from
    the environment and delegates. Errors propagate to the caller; the
    runner is responsible for translating exceptions into
    ``PlanResult.error``/``ApplyResult.error``.
    """

    #: Runner-level finalization hook key (#776). The host-override and
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
            resources: Host-alias ``ResourceConfig`` entries (filtered upstream).
            add_only: If True, suppress deletes for live aliases not in YAML.
            provider_name: Provider identifier (defaults to ``opnsense``).

        Returns:
            ``Diff`` describing what apply would do.

        Raises:
            ReferenceValidationError: If any YAML alias's ``host`` field
                does not resolve to a live ``unbound_host_override``.
        """
        service = UnboundHostAliasService.from_environment(env_name, provider_name, self.config_dir)
        desired = _resolve_host_uuids(unbound_host_alias_configs_from_resources(resources), service)
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
        """Apply the diff: add/update/delete host aliases and reconfigure.

        Args:
            env_name: Active environment name.
            resources: Host-alias ``ResourceConfig`` entries.
            auto_approve: Currently a no-op; the diff engine is the gate.
            add_only: If True, suppress deletes.
            provider_name: Provider identifier (defaults to ``opnsense``).

        Returns:
            Dict with ``resources_created``, ``resources_updated``,
            ``resources_deleted`` counts and a ``resource_outcomes`` list.

        Raises:
            ReferenceValidationError: If any YAML alias's ``host`` field
                does not resolve to a live ``unbound_host_override``.
        """
        del auto_approve  # diff engine is the gate; flag accepted for protocol shape
        service = UnboundHostAliasService.from_environment(env_name, provider_name, self.config_dir)
        desired = _resolve_host_uuids(unbound_host_alias_configs_from_resources(resources), service)
        live = service.search()
        diff = service.compute_diff(desired, live, add_only=add_only)

        outcomes: list[ResourceOutcome] = []
        for alias in diff.adds:
            outcomes.append(
                ResourceOutcome(
                    address=f"opnsense_unbound_host_alias.{alias.name}",
                    action="add",
                    resource_name=alias.name,
                )
            )

        for _live_alias, want in diff.updates:
            outcomes.append(
                ResourceOutcome(
                    address=f"opnsense_unbound_host_alias.{want.name}",
                    action="update",
                    resource_name=want.name,
                )
            )

        for live_alias in diff.deletes:
            synthetic_name = _synthetic_name(live_alias)
            outcomes.append(
                ResourceOutcome(
                    address=f"opnsense_unbound_host_alias.{synthetic_name}",
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
        """Delete every live alias whose tuple is in ``resources``.

        Locked entries are honored: ``lock: true`` resources are skipped
        and counted in the response under ``locked_skipped``.

        Args:
            env_name: Active environment name.
            resources: Host-alias ``ResourceConfig`` entries to destroy.
            auto_approve: Currently a no-op.
            provider_name: Provider identifier (defaults to ``opnsense``).

        Returns:
            Dict with ``resources_destroyed`` and ``locked_skipped`` counts.

        Raises:
            ReferenceValidationError: If any YAML alias's ``host`` field
                does not resolve to a live ``unbound_host_override``.
        """
        del auto_approve
        service = UnboundHostAliasService.from_environment(env_name, provider_name, self.config_dir)
        desired = _resolve_host_uuids(unbound_host_alias_configs_from_resources(resources), service)
        live = service.search()

        live_by_key: dict[tuple[str, str], LiveUnboundHostAlias] = {
            entry.diff_key: entry for entry in live
        }

        deleted = 0
        locked_skipped = 0
        any_action = False
        for alias in desired:
            if alias.lock:
                locked_skipped += 1
                continue
            existing = live_by_key.get(alias.diff_key)
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

        Matches by the natural-key ``(host_uuid, hostname)`` tuple — the
        operator-facing ``name`` is only used as the dict key in the
        return value.

        Args:
            env_name: Active environment name.
            resources: Host-alias ``ResourceConfig`` entries.
            provider_name: Provider identifier (defaults to ``opnsense``).

        Returns:
            Mapping from operator-facing resource name to OPNsense UUID.
            Resources without a matching live record are omitted.

        Raises:
            ReferenceValidationError: If any YAML alias's ``host`` field
                does not resolve to a live ``unbound_host_override``.
        """
        service = UnboundHostAliasService.from_environment(env_name, provider_name, self.config_dir)
        desired = _resolve_host_uuids(unbound_host_alias_configs_from_resources(resources), service)
        live = service.search()
        live_by_key: dict[tuple[str, str], LiveUnboundHostAlias] = {
            entry.diff_key: entry for entry in live
        }

        result: dict[str, str] = {}
        for alias in desired:
            existing = live_by_key.get(alias.diff_key)
            if existing is not None:
                result[alias.name] = existing.uuid
        return result

    def list(self, env_name: str, *, provider_name: str = "opnsense") -> list[LiveUnboundHostAlias]:
        """Return the live host aliases on the OPNsense box.

        Args:
            env_name: Active environment name.
            provider_name: Provider identifier (defaults to ``opnsense``).
        """
        service = UnboundHostAliasService.from_environment(env_name, provider_name, self.config_dir)
        return service.search()

    def migrate(self, env_name: str, *, provider_name: str = "opnsense") -> str:
        """Export the current host aliases to InfraFoundry YAML.

        Args:
            env_name: Active environment name.
            provider_name: Provider identifier (defaults to ``opnsense``).

        Returns:
            YAML string containing the live aliases in resource-centric form.
            Operator-facing ``name`` is synthesized from the
            ``(parent_uuid, hostname)`` natural-key tuple — the operator
            can rename freely after import, since identity is the tuple.
        """
        service = UnboundHostAliasService.from_environment(env_name, provider_name, self.config_dir)
        return service.export_to_yaml()


def _resolve_host_uuids(
    configs: list[UnboundHostAliasConfig],
    service: UnboundHostAliasService,
) -> list[UnboundHostAliasConfig]:
    """Resolve each config's ``host_name`` to a parent override UUID.

    Reads ``searchHostOverride`` rows once and builds a lookup from
    several name shapes:

    - ``hostname.domain`` (the override's natural-key tuple)
    - ``hostname`` alone (when the operator references by short name)
    - the override's UUID itself (defensive — operator might paste a UUID)

    If no override matches, raises ``ReferenceValidationError`` with a
    friendly message identifying the offending alias.

    Args:
        configs: Parsed host-alias configs (with empty ``host_uuid``).
        service: Service used to fetch the host-override rows.

    Returns:
        New list of configs with ``host_uuid`` populated.

    Raises:
        ReferenceValidationError: If any ``host_name`` cannot be resolved.
    """
    if not configs:
        return []

    rows = service.search_host_overrides()
    name_to_uuid: dict[str, str] = {}
    for row in rows:
        uuid = str(row.get("uuid", ""))
        if not uuid:
            continue
        hostname = str(row.get("hostname", ""))
        domain = str(row.get("domain", ""))
        # ``hostname.domain`` form — the natural cross-ref shape.
        if hostname and domain:
            name_to_uuid[f"{hostname}.{domain}"] = uuid
        if hostname:
            # Bare hostname is convenient when there is exactly one match;
            # if multiple overrides share a hostname across domains, the
            # last one wins (best-effort — operator should use FQDN form).
            name_to_uuid.setdefault(hostname, uuid)
        # Defensive: operator might paste a UUID directly.
        name_to_uuid[uuid] = uuid

    resolved: list[UnboundHostAliasConfig] = []
    for cfg in configs:
        resolved_uuid = name_to_uuid.get(cfg.host_name)
        if resolved_uuid is None:
            raise ReferenceValidationError(
                f"unbound_host_alias '{cfg.name}' references unknown host "
                f"'{cfg.host_name}'; no live unbound_host_override matches"
            )
        resolved.append(cfg.with_host_uuid(resolved_uuid))
    return resolved


def _synthetic_name(alias: LiveUnboundHostAlias) -> str:
    """Build a stable synthetic name for a live alias.

    Used when emitting ``ResourceOutcome`` for deletes — the live record
    carries no operator-facing name. Mirrors
    ``services.unbound_host_alias._synthesize_name`` so plan output and
    migrated YAML use the same convention.
    """
    parent_short = alias.host_uuid.split("-")[0] if alias.host_uuid else "unknown"
    return f"alias-{alias.hostname}-{parent_short}".lower()
