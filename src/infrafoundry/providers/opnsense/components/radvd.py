"""Radvd component manager for OPNsense (#788).

Hybrid singleton-YAML / list-wire component manager for the ``radvd``
dotted resource type — IPv6 Router Advertisement emission per interface.
The YAML side is a **dict-shape singleton** (one ``radvd`` resource with
an inner ``interfaces:`` mapping); the wire side is a **list of records**
(one record per interface, each with its own UUID).

The pattern mirrors :class:`SystemFirmwareManager` (#806) where the
operator authors a single ``firmware`` resource but the apply path makes
per-plugin write calls. Here the operator authors a single ``radvd``
resource but the apply path makes per-interface write calls.

**Apply semantics (per #788 user decision, 2026-05-10):**

- **Full reconcile.** Interfaces in live state but absent from YAML are
  DELETED. Safe — deleting a radvd record stops RA emission for that
  interface; no data loss.
- **Per-record writes.** Each add/update/delete maps to one
  ``addEntry``/``setEntry``/``delEntry`` POST. Order: adds, updates,
  deletes (matching other direct-API managers).
- **Reconfigure deferred** to the runner's finalization-hook plumbing —
  the manager declares ``FINALIZATION_HOOK = "radvd_reconfigure"``.
- **Destroy nukes every live record** (full-destroy semantics).
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from infrafoundry.core.exceptions import InvalidConfigurationError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.types import ResourceOutcome

from ..services.radvd import RadvdService
from ._singleton import enforce_singleton
from .base import BaseComponentManager

logger = logging.getLogger(__name__)


class _RadvdDiff:
    """Plan-shape adapter for radvd's hybrid singleton/list diff.

    Exposes the standard ``adds``/``updates``/``deletes``/``locked`` /
    ``is_empty`` surface that ``OPNsenseDirectRunner._format_plan_summary``
    consumes, but with payload tuples sized for per-interface dispatch:

    - ``adds``: ``[(interface_name, desired_field_map), ...]``
    - ``updates``: ``[(interface_name, desired_field_map, live_field_map), ...]``
    - ``deletes``: ``[(interface_name, live_field_map), ...]``
    - ``locked``: always empty (radvd has no per-record lock concept).

    Args:
        adds: Per-interface adds (sorted by interface name).
        updates: Per-interface updates (sorted by interface name).
        deletes: Per-interface deletes (sorted by interface name).
    """

    def __init__(
        self,
        *,
        adds: list[tuple[str, dict[str, Any]]] | None = None,
        updates: list[tuple[str, dict[str, Any], dict[str, Any]]] | None = None,
        deletes: list[tuple[str, dict[str, Any]]] | None = None,
    ) -> None:
        """Initialize the radvd diff."""
        self.adds: list[tuple[str, dict[str, Any]]] = adds or []
        self.updates: list[tuple[str, dict[str, Any], dict[str, Any]]] = updates or []
        self.deletes: list[tuple[str, dict[str, Any]]] = deletes or []
        self.locked: list[Any] = []

    @property
    def is_empty(self) -> bool:
        """Return True when there are no add/update/delete operations to apply."""
        return not (self.adds or self.updates or self.deletes)


class RadvdManager(BaseComponentManager):
    """Manager for OPNsense radvd singleton-YAML / list-wire operations."""

    #: Runner-level finalization hook key (#788). Resolves through
    #: ``OPNsenseProvider.get_finalization_hooks()`` to a single
    #: ``radvd/service/reconfigure`` call per apply when any radvd
    #: record changed state.
    FINALIZATION_HOOK: ClassVar[str] = "radvd_reconfigure"

    def plan(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        add_only: bool = False,
        provider_name: str = "opnsense",
    ) -> _RadvdDiff:
        """Compute the per-interface add/update/delete diff.

        Args:
            env_name: Active environment name.
            resources: Should contain exactly one ``radvd`` ``ResourceConfig``.
            add_only: If True, suppress updates and deletes — only adds
                are dispatched.
            provider_name: Provider identifier (defaults to ``opnsense``).

        Returns:
            ``_RadvdDiff`` with sorted per-interface adds/updates/deletes.
        """
        enforce_singleton(resources, "radvd")
        service = RadvdService.from_environment(env_name, provider_name, self.config_dir)
        live = service.extract_interface_records()
        desired = service.build_desired_interface_records(resources[0])
        adds_set, updates_set, deletes_set = service.compute_diff(live, desired)
        if add_only:
            updates_set = set()
            deletes_set = set()
        return _RadvdDiff(
            adds=[(name, desired[name]) for name in sorted(adds_set)],
            updates=[(name, desired[name], live[name]) for name in sorted(updates_set)],
            deletes=[(name, live[name]) for name in sorted(deletes_set)],
        )

    def apply(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        auto_approve: bool = True,
        add_only: bool = False,
        provider_name: str = "opnsense",
    ) -> dict[str, Any]:
        """Apply the diff: add/update/delete radvd records per-interface.

        Does **not** call ``service.reconfigure()`` directly — the runner
        fires the ``radvd_reconfigure`` finalization hook once after every
        component has applied.

        Args:
            env_name: Active environment name.
            resources: Should contain exactly one ``radvd`` ``ResourceConfig``.
            auto_approve: No-op (the diff engine is the gate).
            add_only: If True, suppress updates and deletes.
            provider_name: Provider identifier (defaults to ``opnsense``).

        Returns:
            Dict with counts and ``resource_outcomes``. Each per-interface
            mutation produces one ``ResourceOutcome``.
        """
        del auto_approve
        enforce_singleton(resources, "radvd")
        service = RadvdService.from_environment(env_name, provider_name, self.config_dir)
        diff = self.plan(env_name, resources, add_only=add_only, provider_name=provider_name)
        live_uuids = service.list_uuids_by_interface()

        outcomes: list[ResourceOutcome] = []
        created = 0
        updated = 0
        deleted = 0

        # Adds first — new records exist on the box before any updates fire.
        for interface_name, desired_fields in diff.adds:
            payload = service.wire_payload_for_interface(interface_name, desired_fields)
            response = service.add_record(payload)
            if isinstance(response, dict) and response.get("result") == "failed":
                raise InvalidConfigurationError(
                    f"Failed to create radvd entry for interface {interface_name!r}: {response}"
                )
            outcomes.append(
                ResourceOutcome(
                    address=f"opnsense_radvd.{interface_name}",
                    action="add",
                    resource_name=interface_name,
                )
            )
            created += 1

        for interface_name, desired_fields, _live in diff.updates:
            uuid = live_uuids.get(interface_name)
            if not uuid:
                # Defensive: shouldn't happen if live state matches the diff.
                logger.warning(
                    "radvd: skipping update for interface %r — no live UUID", interface_name
                )
                continue
            payload = service.wire_payload_for_interface(interface_name, desired_fields)
            response = service.set_record(uuid, payload)
            if isinstance(response, dict) and response.get("result") == "failed":
                raise InvalidConfigurationError(
                    f"Failed to update radvd entry for interface {interface_name!r}: {response}"
                )
            outcomes.append(
                ResourceOutcome(
                    address=f"opnsense_radvd.{interface_name}",
                    action="update",
                    resource_name=interface_name,
                )
            )
            updated += 1

        for interface_name, _live in diff.deletes:
            uuid = live_uuids.get(interface_name)
            if not uuid:
                logger.warning(
                    "radvd: skipping delete for interface %r — no live UUID", interface_name
                )
                continue
            service.del_record(uuid)
            outcomes.append(
                ResourceOutcome(
                    address=f"opnsense_radvd.{interface_name}",
                    action="delete",
                    resource_name=interface_name,
                )
            )
            deleted += 1

        return {
            "success": True,
            "resources_created": created,
            "resources_updated": updated,
            "resources_deleted": deleted,
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
        """Delete every live radvd record (full destroy).

        radvd has no per-record lock, so ``locked_skipped`` is always 0.

        Args:
            env_name: Active environment name.
            resources: Singleton ``radvd`` ``ResourceConfig`` list (unused
                — destroy operates on live state).
            auto_approve: No-op.
            provider_name: Provider identifier (defaults to ``opnsense``).

        Returns:
            Dict with ``resources_destroyed`` and ``locked_skipped`` counts.
        """
        del resources, auto_approve
        service = RadvdService.from_environment(env_name, provider_name, self.config_dir)
        live_uuids = service.list_uuids_by_interface()
        outcomes: list[ResourceOutcome] = []
        for interface_name, uuid in sorted(live_uuids.items()):
            service.del_record(uuid)
            outcomes.append(
                ResourceOutcome(
                    address=f"opnsense_radvd.{interface_name}",
                    action="delete",
                    resource_name=interface_name,
                )
            )
        return {
            "success": True,
            "resources_destroyed": len(outcomes),
            "locked_skipped": 0,
            "resource_outcomes": outcomes,
        }

    def get_resource_ids(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        provider_name: str = "opnsense",
    ) -> dict[str, str]:
        """Return per-interface UUIDs keyed by ``interfaces.<name>``.

        Singleton at YAML level, but per-interface UUIDs are surfaced so
        state tracking can address each record individually.

        Args:
            env_name: Active environment name.
            resources: Singleton ``radvd`` ``ResourceConfig`` list (unused).
            provider_name: Provider identifier (defaults to ``opnsense``).

        Returns:
            Mapping like ``{"interfaces.opt1": "<uuid>", ...}``.
        """
        del resources
        service = RadvdService.from_environment(env_name, provider_name, self.config_dir)
        live_uuids = service.list_uuids_by_interface()
        return {f"interfaces.{name}": uuid for name, uuid in live_uuids.items()}

    def migrate(
        self,
        env_name: str,
        *,
        provider_name: str = "opnsense",
    ) -> str:
        """Export current radvd state to InfraFoundry YAML."""
        service = RadvdService.from_environment(env_name, provider_name, self.config_dir)
        return service.export_to_yaml()
