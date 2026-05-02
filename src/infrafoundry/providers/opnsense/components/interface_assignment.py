"""Interface-assignment component manager for OPNsense (ADR-0014, #711).

OPNsense `26.1.6_2` exposes interface assignments as **read-only** via
``GET /api/interfaces/overview/interfacesInfo``; no REST write endpoint
exists today (the GUI's "Interfaces → Assignments" page edits
``config.xml`` via legacy PHP form posts). This manager mirrors the
``VlanManager`` shape so the dispatch-table-driven runner can iterate
both uniformly, but ``apply``/``destroy`` are loud no-op stubs that
return zero counts and an explicit informational message.

Operators wire interface assignments via the OPNsense GUI as a one-time
manual cutover step; ``infra plan`` surfaces the read-only state, and
``foundry config migrate --component interface_assignment`` (provider
method only — CLI wiring is a follow-up) extracts the live state into
YAML.

The runner forwards ``message`` from the apply result through to its
human-readable output; the runner's plan-summary helper recognizes
``Diff`` objects with ``read_only=True`` and surfaces ``message`` there
too.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from infrafoundry.core.provider import ResourceConfig

from ..services.interface_assignment import (
    InterfaceAssignmentService,
    LiveInterfaceAssignment,
    interface_assignment_configs_from_resources,
)
from .base import BaseComponentManager

logger = logging.getLogger(__name__)

_READ_ONLY_MESSAGE = (
    "interface_assignments are read-only on this OPNsense version; "
    "manual GUI configuration required (Interfaces → Assignments)"
)


# ---------------------------------------------------------------------------
# Read-only Diff shim
# ---------------------------------------------------------------------------


@dataclass
class ReadOnlyDiff:
    """Diff-shaped payload for a read-only component.

    Mirrors the structural surface of ``services.vlan.Diff`` (so the
    runner's plan-summary helper can iterate ``adds``/``updates``/
    ``deletes``/``locked`` without special-casing). The ``read_only``
    flag is the marker the runner checks; ``message`` is surfaced
    verbatim in the plan output.

    Attributes:
        adds: Always empty for read-only components.
        updates: Always empty.
        deletes: Always empty.
        locked: Always empty.
        read_only: Marker set to True so the runner formats this diff
            with the informational message rather than the count line.
        message: Human-readable note shown alongside the type name.
    """

    adds: list[Any] = field(default_factory=list)
    updates: list[Any] = field(default_factory=list)
    deletes: list[Any] = field(default_factory=list)
    locked: list[Any] = field(default_factory=list)
    read_only: bool = True
    message: str = _READ_ONLY_MESSAGE

    @property
    def is_empty(self) -> bool:
        """Read-only diffs never represent pending work."""
        return True


class InterfaceAssignmentManager(BaseComponentManager):
    """Manager for OPNsense interface-assignment operations (read-only).

    Public interface mirrors ``VlanManager`` so the runner's dispatch
    table can call any registered manager uniformly. Write methods
    (``apply``/``destroy``) return zero counts and an informational
    ``message`` field; read methods (``plan``/``get_resource_ids``/
    ``list``) hit the live API.
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
    ) -> ReadOnlyDiff:
        """Return a read-only diff with an informational message.

        We don't validate ``resources`` against live state because writes
        are no-op anyway — surfacing the read-only constraint is more
        useful to the operator than reporting a delta they cannot apply.
        The validator is the source of truth for cross-resource reference
        checks; this method is purely informational at plan time.

        Args:
            env_name: Active environment name (unused — read-only).
            resources: Interface-assignment ``ResourceConfig`` entries
                (unused for now; reserved for future write path).
            add_only: Reserved; ignored for read-only.
            provider_name: Provider identifier.

        Returns:
            ``ReadOnlyDiff`` with empty add/update/delete lists and the
            read-only informational message.
        """
        del env_name, resources, add_only, provider_name  # read-only no-op
        return ReadOnlyDiff()

    def apply(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        auto_approve: bool = True,
        add_only: bool = False,
        provider_name: str = "opnsense",
    ) -> dict[str, Any]:
        """Loud no-op apply.

        Logs an informational line and returns success with zero counts
        plus a ``message`` field the runner surfaces verbatim. Accepts
        every kwarg ``VlanManager.apply`` does so dispatch is uniform.

        Args:
            env_name: Active environment name (unused).
            resources: Interface-assignment ``ResourceConfig`` entries.
                Counted into the message; not otherwise touched.
            auto_approve: Unused.
            add_only: Unused.
            provider_name: Provider identifier (unused).

        Returns:
            Dict with ``success=True``, zero counts, an empty
            ``resource_outcomes`` list, and a ``message`` field the
            runner surfaces.
        """
        del env_name, auto_approve, add_only, provider_name  # read-only no-op
        count = len(resources)
        message = (
            f"{_READ_ONLY_MESSAGE}; {count} assignment{'s' if count != 1 else ''} described in YAML"
        )
        logger.info(message)
        return {
            "success": True,
            "resources_created": 0,
            "resources_updated": 0,
            "resources_deleted": 0,
            "resource_outcomes": [],
            "message": message,
        }

    def destroy(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        auto_approve: bool = True,
        provider_name: str = "opnsense",
    ) -> dict[str, Any]:
        """Loud no-op destroy.

        Args:
            env_name: Active environment name (unused).
            resources: Interface-assignment ``ResourceConfig`` entries
                (counted into the message only).
            auto_approve: Unused.
            provider_name: Provider identifier (unused).

        Returns:
            Dict with ``success=True``, ``resources_destroyed=0``, and
            a ``message`` field the runner surfaces.
        """
        del env_name, auto_approve, provider_name  # read-only no-op
        count = len(resources)
        message = (
            f"{_READ_ONLY_MESSAGE}; {count} assignment"
            f"{'s' if count != 1 else ''} listed in YAML; nothing destroyed"
        )
        logger.info(message)
        return {
            "success": True,
            "resources_destroyed": 0,
            "message": message,
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
        """Return ``{resource_name: identifier}`` for live entries matching ``resources``.

        For read-only resources the live ``identifier`` doubles as the
        resource ID (it's both the operator-facing name and the
        OPNsense-side primary key — there's no UUID layer for interface
        assignments). State DB updates via this map.

        Resources without a matching live record are simply omitted —
        the state DB will skip updating those rows and they'll surface
        as plan-time validation errors via the validator.

        Args:
            env_name: Active environment name.
            resources: Interface-assignment ``ResourceConfig`` entries.
            provider_name: Provider identifier (defaults to ``opnsense``).

        Returns:
            Mapping of resource name to live identifier.
        """
        configs = interface_assignment_configs_from_resources(resources)
        if not configs:
            return {}
        service = InterfaceAssignmentService.from_environment(
            env_name, provider_name, self.config_dir
        )
        live_by_id = {entry.identifier: entry for entry in service.list()}
        return {
            cfg.name: live_by_id[cfg.name].identifier for cfg in configs if cfg.name in live_by_id
        }

    def list(
        self, env_name: str, *, provider_name: str = "opnsense"
    ) -> list[LiveInterfaceAssignment]:
        """Return the live interface assignments on the OPNsense box.

        Args:
            env_name: Active environment name.
            provider_name: Provider identifier (defaults to ``opnsense``).
        """
        service = InterfaceAssignmentService.from_environment(
            env_name, provider_name, self.config_dir
        )
        return service.list()

    def migrate(self, env_name: str, *, provider_name: str = "opnsense") -> str:
        """Export the current interface assignments to InfraFoundry YAML.

        Args:
            env_name: Active environment name.
            provider_name: Provider identifier (defaults to ``opnsense``).

        Returns:
            YAML string containing the live assignments in resource-centric form.
        """
        service = InterfaceAssignmentService.from_environment(
            env_name, provider_name, self.config_dir
        )
        return service.export_to_yaml()
