"""Interface-assignment component manager for OPNsense (ADR-0014, #720).

This manager mirrors the ``VlanManager`` shape: a thin orchestration
layer that loads ``InterfaceAssignmentService`` from the environment
and dispatches add/update/delete operations through the gist-derived
PHP controller. The runner (``OPNsenseDirectRunner``) instantiates
this manager once per plan/apply/destroy and delegates.

Apply flow:

1. ``apply()`` lists live state and computes the diff first (the list
   endpoint needs no controller), then checks for lockout conflicts.
2. Only when the (filtered) diff is non-empty does it run the
   SSH-target resolution (from ``provider_settings.opnsense``: ``ssh_host``,
   ``ssh_user``, ``ssh_port``, ``ssh_key``, falling back to the ``api_url``
   host; ``OPNSENSE_SSH_HOST`` only under ``INFRAFOUNDRY_ALLOW_ENV_OVERRIDE``;
   an unresolved host raises ``RuntimeError`` with an actionable message, #1274)
   and ``installer.ensure_installed(target)``, which SCPs the controller PHP if its
   on-box checksum doesn't match the local source. Idempotent.
   The runner calls ``apply`` twice (``deletes_only`` first, #1271), so
   each pass installs only when it has writes.
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
from typing import Any, ClassVar

from infrafoundry.core.config import ConfigManager
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.types import ResourceOutcome

from ..extensions.interface_assignments import SshTarget, build_ssh_target, installer
from ..services._credentials import resolve_ssh_settings
from ..services.interface_assignment import (
    Diff,
    InterfaceAssignmentService,
    LiveInterfaceAssignment,
    find_lockout_conflicts,
    interface_assignment_configs_from_resources,
)
from ._managed import managed_keys as derive_managed_keys
from .base import BaseComponentManager

logger = logging.getLogger(__name__)


# Pre-flight credential check: SSH credentials are required for the
# one-time controller install. Missing credentials must fail the
# manager with a clear actionable message before any diff is computed.
_SSH_PREFLIGHT_MESSAGE = (
    "interface_assignments writes require SSH credentials for one-time "
    "controller install, but no SSH host resolved. Set ssh_host (and optionally "
    "ssh_user, ssh_port, ssh_key) in provider_settings.opnsense, or set api_url "
    "so the host is derived from it. OPNSENSE_SSH_HOST / OPNSENSE_API_URL apply "
    "only with INFRAFOUNDRY_ALLOW_ENV_OVERRIDE=1; OPNSENSE_SSH_USER/PORT/KEY "
    "always apply. Key auth only (ssh-agent or ~/.ssh/config); no password support. "
    "See src/infrafoundry/providers/opnsense/extensions/interface_assignments/PROVENANCE.md."
)


class InterfaceAssignmentManager(BaseComponentManager):
    """Manager for OPNsense interface-assignment operations (full CRUD).

    Public interface mirrors ``VlanManager`` so the runner's dispatch
    table can call any registered manager uniformly.
    """

    #: Deletes are limited to the rows InfraFoundry applied before (ADR-0018).
    DELETE_SCOPE: ClassVar[str] = "managed_set"

    #: The runner deletes in a separate phase before this type's adds and updates,
    #: and before the VLAN delete, since OPNsense refuses to delete an assigned
    #: VLAN (#1271).
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
        managed_resources: list[ResourceConfig] | None = None,
        provider_name: str = "opnsense",
    ) -> Diff:
        """Compute the add/update/delete diff for the given resources.

        Args:
            env_name: Active environment name.
            resources: ``interface_assignments`` ``ResourceConfig``
                entries (filtered upstream).
            add_only: If ``True``, suppress deletes for live entries
                not in YAML.
            managed_resources: Rows InfraFoundry applied before (ADR-0018). When given,
                only live assignments matching them may be deleted, and ``lan`` and
                ``wan`` never are; ``None`` deletes every live assignment missing
                from YAML.
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
        return service.compute_diff(
            desired,
            live,
            add_only=add_only,
            managed_keys=derive_managed_keys(
                managed_resources,
                interface_assignment_configs_from_resources,
                type_name="interfaces.assignments",
            ),
        )

    def apply(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        auto_approve: bool = True,
        add_only: bool = False,
        managed_resources: list[ResourceConfig] | None = None,
        provider_name: str = "opnsense",
        deletes_only: bool = False,
    ) -> dict[str, Any]:
        """Apply the diff: add/update/delete assignments via the gist controller.

        Pre-flight order:

        1. Compute the diff against live state (``service.list()`` needs
           no controller). With ``deletes_only`` the adds and updates are
           dropped.
        2. Lockout pre-flight refuses application if a planned ``add``
           would collide with an already-bound device.
        3. Only when the diff is non-empty: SSH credential pre-flight
           (raises ``RuntimeError`` with an actionable message if
           credentials are absent), then ``installer.ensure_installed()``
           SCPs the PHP controller if needed. Idempotent.
        4. Dispatch the diff via ``service.apply_diff``. First HTTP
           400 stops further ops; the caller-visible ``message``
           names what succeeded so manual continuation is possible.

        Args:
            env_name: Active environment name.
            resources: ``interface_assignments`` ``ResourceConfig`` entries.
            auto_approve: Currently a no-op; the diff engine itself
                is the gate.
            add_only: If ``True``, suppress deletes.
            managed_resources: Rows InfraFoundry applied before (ADR-0018). When given,
                only live assignments matching them may be deleted, and ``lan`` and
                ``wan`` never are; ``None`` deletes every live assignment missing
                from YAML.
            provider_name: Provider identifier (defaults to
                ``opnsense``).
            deletes_only: If ``True``, apply only the deletes. The runner's delete
                phase (``SPLIT_DELETE_PHASE``) sets it so an assignment goes before
                the VLAN it uses (#1271).

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

        service = InterfaceAssignmentService.from_environment(
            env_name, provider_name, self.config_dir
        )
        desired = interface_assignment_configs_from_resources(resources)
        live = service.list()
        unresolved_managed: set[str] = set()
        diff = service.compute_diff(
            desired,
            live,
            add_only=add_only,
            managed_keys=derive_managed_keys(
                managed_resources,
                interface_assignment_configs_from_resources,
                type_name="interfaces.assignments",
                unresolved=unresolved_managed,
            ),
        )

        if deletes_only:
            diff.adds = []
            diff.updates = []

        # Pre-flight 1: lockout check before mutating.
        conflicts = find_lockout_conflicts(diff, live)
        if conflicts:
            joined = "; ".join(conflicts)
            raise RuntimeError(f"interface_assignments lockout conflicts: {joined}")

        # Pre-flight 2: only a write needs SSH credentials and the PHP
        # controller. Listing uses the core interfaces endpoint, so an empty
        # (filtered) diff never installs and the runner's two passes do not
        # repeat the install.
        if not diff.is_empty:
            installer.ensure_installed(self._resolve_ssh_target(env_name, provider_name))

        outcomes = self._build_outcomes(diff)
        apply_result = service.apply_diff(diff)

        result: dict[str, Any] = {
            "success": apply_result.succeeded,
            "resources_created": apply_result.created,
            "resources_updated": apply_result.updated,
            "resources_deleted": apply_result.deleted,
            "resource_outcomes": outcomes,
            "unresolved_managed": sorted(unresolved_managed),
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
        installer.ensure_installed(self._resolve_ssh_target(env_name, provider_name))

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

    def _load_provider_settings(self, env_name: str, provider_name: str) -> dict[str, Any]:
        """Load the env's ``provider_settings`` entry for ``provider_name``.

        Args:
            env_name: Active environment name.
            provider_name: Provider identifier.

        Returns:
            The provider's settings dict (empty when none are configured).
        """
        config_manager = ConfigManager(self.config_dir)
        env_config = config_manager.load_environment(env_name)
        return dict(env_config.get_provider_settings(provider_name) or {})

    def _resolve_ssh_target(self, env_name: str, provider_name: str) -> SshTarget:
        """Resolve the installer's SSH target from the env's provider settings.

        Raises ``RuntimeError`` with an actionable message when no host
        resolves, so the operator gets a coherent failure mode instead of a
        deep ssh traceback at SCP time.

        Args:
            env_name: Active environment name.
            provider_name: Provider identifier.

        Returns:
            The ``SshTarget`` to pass to ``installer.ensure_installed``.

        Raises:
            RuntimeError: If no SSH host resolves, or the port / key is invalid.
        """
        ssh = resolve_ssh_settings(self._load_provider_settings(env_name, provider_name))
        if not ssh.host:
            raise RuntimeError(_SSH_PREFLIGHT_MESSAGE)
        return build_ssh_target(ssh.host, user=ssh.user, port=ssh.port, key=ssh.key)

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
