"""Interface-assignment component manager for OPNsense (ADR-0014, #720).

This manager mirrors the ``VlanManager`` shape: a thin orchestration
layer that loads ``InterfaceAssignmentService`` from the environment
and dispatches add/update/delete operations through the gist-derived
PHP controller. The runner (``OPNsenseDirectRunner``) instantiates
this manager once per plan/apply/destroy and delegates.

Apply flow:

1. ``apply()`` runs an SSH-credential pre-flight; missing credentials
   raise ``RuntimeError`` with an actionable message **before** any
   diff or REST call (no deep paramiko traceback).
2. ``installer.ensure_installed()`` SCPs the controller PHP if its
   on-box checksum doesn't match the local source. Idempotent —
   subsequent calls fast-path via the checksum probe.
3. The service ``compute_diff`` + ``apply_diff`` does the actual
   CRUD against the controller's REST endpoints. Each REST call
   triggers ``interface reconfigure all`` server-side via configd;
   there is no end-of-batch reconfigure step (differs from VLAN's
   pattern).

Destroy flow honors ``lock: true`` per-resource — locked entries are
skipped and reported under ``locked_skipped``.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.types import ResourceOutcome

from ..extensions.interface_assignments import installer
from ..services.interface_assignment import (
    Diff,
    InterfaceAssignmentService,
    LiveInterfaceAssignment,
    find_lockout_conflicts,
    interface_assignment_configs_from_resources,
)
from .base import BaseComponentManager

logger = logging.getLogger(__name__)


# Pre-flight credential check: SSH credentials are required for the
# one-time controller install. Missing credentials must fail the
# manager with a clear actionable message before any diff is computed.
_SSH_PREFLIGHT_MESSAGE = (
    "interface_assignments writes require SSH credentials for one-time "
    "controller install; set OPNSENSE_SSH_HOST/KEY/USER (or rely on "
    "OPNSENSE_API_URL + ssh-agent + ~/.ssh/config). "
    "See src/infrafoundry/providers/opnsense/extensions/interface_assignments/PROVENANCE.md."
)


class InterfaceAssignmentManager(BaseComponentManager):
    """Manager for OPNsense interface-assignment operations (full CRUD).

    Public interface mirrors ``VlanManager`` so the runner's dispatch
    table can call any registered manager uniformly.
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
            resources: ``interface_assignments`` ``ResourceConfig``
                entries (filtered upstream).
            add_only: If ``True``, suppress deletes for live entries
                not in YAML.
            provider_name: Provider identifier (defaults to
                ``opnsense``).

        Returns:
            ``Diff`` describing what apply would do.
        """
        service = InterfaceAssignmentService.from_environment(
            env_name, provider_name, self.config_dir
        )
        desired = interface_assignment_configs_from_resources(resources)
        live = service.list()
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
        """Apply the diff: add/update/delete assignments via the gist controller.

        Pre-flight order:

        1. SSH credential pre-flight (raises ``RuntimeError`` with
           an actionable message if credentials are absent).
        2. ``installer.ensure_installed()`` SCPs the PHP controller
           if needed. Idempotent.
        3. Compute the diff against live state.
        4. Lockout pre-flight refuses application if a planned ``add``
           would collide with an already-bound device.
        5. Dispatch the diff via ``service.apply_diff``. First HTTP
           400 stops further ops; the caller-visible ``message``
           names what succeeded so manual continuation is possible.

        Args:
            env_name: Active environment name.
            resources: ``interface_assignments`` ``ResourceConfig`` entries.
            auto_approve: Currently a no-op; the diff engine itself
                is the gate.
            add_only: If ``True``, suppress deletes.
            provider_name: Provider identifier (defaults to
                ``opnsense``).

        Returns:
            Dict with ``success``, ``resources_created``,
            ``resources_updated``, ``resources_deleted``,
            ``resource_outcomes``, and an optional ``message`` field.

        Raises:
            RuntimeError: If SSH credentials needed for the controller
                install are missing, or the installer / lockout
                pre-flight fail.
        """
        del auto_approve  # diff engine is the gate; flag accepted for protocol shape

        # Pre-flight 1: SSH credentials must be resolvable before we do
        # anything else. Skipping this means a deep paramiko traceback
        # surfaces from inside install_controller() at apply time.
        self._preflight_ssh_credentials()

        # Pre-flight 2: ensure the PHP controller is installed. Idempotent
        # — fast-paths via checksum on every subsequent apply.
        installer.ensure_installed()

        service = InterfaceAssignmentService.from_environment(
            env_name, provider_name, self.config_dir
        )
        desired = interface_assignment_configs_from_resources(resources)
        live = service.list()
        diff = service.compute_diff(desired, live, add_only=add_only)

        # Pre-flight 3: lockout check before mutating.
        conflicts = find_lockout_conflicts(diff, live)
        if conflicts:
            joined = "; ".join(conflicts)
            raise RuntimeError(f"interface_assignments lockout conflicts: {joined}")

        outcomes = self._build_outcomes(diff)
        apply_result = service.apply_diff(diff)

        result: dict[str, Any] = {
            "success": apply_result.succeeded,
            "resources_created": apply_result.created,
            "resources_updated": apply_result.updated,
            "resources_deleted": apply_result.deleted,
            "resource_outcomes": outcomes,
        }
        if apply_result.failure_message is not None:
            # Surface partial-success counts in the operator-facing
            # message so manual continuation is possible.
            result["message"] = (
                f"{apply_result.failure_message}; partial success — "
                f"created={apply_result.created} updated={apply_result.updated} "
                f"deleted={apply_result.deleted}"
            )
        return result

    def destroy(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        auto_approve: bool = True,
        provider_name: str = "opnsense",
    ) -> dict[str, Any]:
        """Delete every assignment named in ``resources`` from the live OPNsense box.

        Locked entries are honored: ``lock: true`` resources are
        skipped and counted in the response under ``locked_skipped``.

        Args:
            env_name: Active environment name.
            resources: ``interface_assignments`` ``ResourceConfig``
                entries to destroy.
            auto_approve: Currently a no-op.
            provider_name: Provider identifier (defaults to
                ``opnsense``).

        Returns:
            Dict with ``resources_destroyed`` and ``locked_skipped``
            counts.

        Raises:
            RuntimeError: If SSH credentials needed for the controller
                install are missing, or installer setup fails.
        """
        del auto_approve

        # Pre-flight (matches apply()): the controller must be present
        # before we can dispatch delItem. Idempotent fast-path on
        # repeat destroys.
        self._preflight_ssh_credentials()
        installer.ensure_installed()

        service = InterfaceAssignmentService.from_environment(
            env_name, provider_name, self.config_dir
        )
        desired = interface_assignment_configs_from_resources(resources)
        live = service.list()
        live_by_key: dict[str, LiveInterfaceAssignment] = {v.diff_key: v for v in live}

        deleted = 0
        locked_skipped = 0
        for cfg in desired:
            if cfg.lock:
                locked_skipped += 1
                continue
            existing = live_by_key.get(cfg.diff_key)
            if existing is None:
                continue
            service.delete(existing.identifier)
            deleted += 1

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
        """Return ``{resource_name: identifier}`` for live entries matching ``resources``.

        For interface assignments the live ``identifier`` doubles as
        the resource ID — there's no UUID layer, the logical name is
        the primary key on the box.

        Args:
            env_name: Active environment name.
            resources: ``interface_assignments`` ``ResourceConfig``
                entries.
            provider_name: Provider identifier (defaults to
                ``opnsense``).

        Returns:
            Mapping of resource name to live identifier. Resources
            without a matching live record are omitted.
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

    def migrate(self, env_name: str, *, provider_name: str = "opnsense") -> str:
        """Export the current interface assignments to InfraFoundry YAML.

        Args:
            env_name: Active environment name.
            provider_name: Provider identifier (defaults to ``opnsense``).

        Returns:
            YAML string containing the live assignments in
            resource-centric form.
        """
        service = InterfaceAssignmentService.from_environment(
            env_name, provider_name, self.config_dir
        )
        return service.export_to_yaml()

    # ------------------------------------------------------------------
    # Internal helpers (defined before ``list`` so list[...] annotations
    # below resolve to the builtin)
    # ------------------------------------------------------------------

    @staticmethod
    def _preflight_ssh_credentials() -> None:
        """Verify SSH credentials are resolvable before invoking the installer.

        Raises ``RuntimeError`` with an actionable message when neither
        ``OPNSENSE_SSH_HOST`` nor ``OPNSENSE_API_URL`` is set, so the
        operator gets a coherent failure mode instead of a deep
        paramiko traceback at SCP time.
        """
        if os.environ.get("OPNSENSE_SSH_HOST") or os.environ.get("OPNSENSE_API_URL"):
            return
        raise RuntimeError(_SSH_PREFLIGHT_MESSAGE)

    @staticmethod
    def _build_outcomes(diff: Diff) -> list[ResourceOutcome]:
        """Build ``ResourceOutcome`` entries for every operation in ``diff``.

        Mirrors ``VlanManager._build_outcomes``: address shape is
        ``opnsense_interface_assignment.{name}``; the deleted-by-IaC
        path uses the live record's identifier (which doubles as
        ``name`` for this component).
        """
        outcomes: list[ResourceOutcome] = []

        for cfg in diff.adds:
            outcomes.append(
                ResourceOutcome(
                    address=f"opnsense_interface_assignment.{cfg.name}",
                    action="add",
                    resource_name=cfg.name,
                )
            )

        for _live, want in diff.updates:
            outcomes.append(
                ResourceOutcome(
                    address=f"opnsense_interface_assignment.{want.name}",
                    action="update",
                    resource_name=want.name,
                )
            )

        for live in diff.deletes:
            outcomes.append(
                ResourceOutcome(
                    address=f"opnsense_interface_assignment.{live.identifier}",
                    action="delete",
                    resource_name=live.identifier,
                )
            )

        return outcomes

    # ------------------------------------------------------------------
    # Read paths (defined last so ``list`` does not shadow the builtin
    # in earlier annotations)
    # ------------------------------------------------------------------

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
