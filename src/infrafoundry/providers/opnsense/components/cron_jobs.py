"""Cron-jobs component manager for OPNsense (#789).

List-shape direct-API component manager for the ``cron.jobs`` dotted
resource type — OPNsense scheduled tasks via the ``cron/settings/`` MVC
controller. Each job is a distinct UUID-keyed record on the box.

**Apply semantics (per #789 user decision):**

- **Full reconcile.** Managed jobs absent from YAML are DELETED. Unmanaged
  jobs (no identity suffix) are never touched.
- **Per-record writes.** Adds, updates, and deletes each make one API call.
  Order: adds first, then updates, then deletes.
- **Reconfigure deferred** to the runner's finalization-hook plumbing —
  the manager declares ``FINALIZATION_HOOK = "cron_reconfigure"`` and the
  apply path never calls ``service.reconfigure()`` directly.
- **Destroy reconfigures directly** — unlike apply, the ``cron_reconfigure``
  hook is not fired by the runner for destroy paths, so destroy calls
  ``service.reconfigure()`` directly after any deletion.
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.types import ResourceOutcome

from ..services.cron_jobs import (
    CronJobsService,
    Diff,
    LiveCronJob,
    cron_job_configs_from_resources,
    plugin_conflicts,
)
from .base import BaseComponentManager

logger = logging.getLogger(__name__)


class CronJobsManager(BaseComponentManager):
    """Manager for OPNsense cron-job direct-API operations (#789).

    Each public method instantiates a ``CronJobsService`` from the
    environment and delegates. Errors propagate to the caller; the
    runner is responsible for translating exceptions into plan/apply
    error results.
    """

    #: Runner-level finalization hook key (#789). Resolves through
    #: ``OPNsenseProvider.get_finalization_hooks()`` to a single
    #: ``cron/service/reconfigure`` call per apply when any cron job
    #: changed state.
    FINALIZATION_HOOK: ClassVar[str] = "cron_reconfigure"

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

        Emits a WARNING log for each unmanaged live job that shares a
        ``command`` with a desired YAML job (``plugin_conflicts``).
        These conflicts do not block the plan.

        Args:
            env_name: Active environment name.
            resources: Cron-job ``ResourceConfig`` entries (filtered
                upstream to ``cron.jobs`` type).
            add_only: If True, suppress deletes for managed live jobs
                not in YAML. Unmanaged live jobs are always ignored.
            provider_name: Provider identifier (defaults to
                ``opnsense``).

        Returns:
            ``Diff`` describing what apply would do.
        """
        service = CronJobsService.from_environment(env_name, provider_name, self.config_dir)
        desired = cron_job_configs_from_resources(resources)
        live = service.search()

        for want, conflicting in plugin_conflicts(desired, live):
            logger.warning(
                "cron_jobs: YAML job %r shares command %r with unmanaged live job %r (%s) — "
                "the live job will NOT be modified, but both will run the same command",
                want.name,
                want.command,
                conflicting.uuid,
                conflicting.raw.get("description", ""),
            )

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
        """Apply the diff: add/update/delete cron jobs.

        Does **not** call ``service.reconfigure()`` directly — the runner
        fires the ``cron_reconfigure`` finalization hook once after every
        component has applied.

        Args:
            env_name: Active environment name.
            resources: Cron-job ``ResourceConfig`` entries.
            auto_approve: Currently a no-op; the diff engine is the gate.
            add_only: If True, suppress deletes.
            provider_name: Provider identifier (defaults to
                ``opnsense``).

        Returns:
            Dict with ``resources_created``, ``resources_updated``,
            ``resources_deleted`` counts and a ``resource_outcomes`` list.
        """
        del auto_approve  # diff engine is the gate
        service = CronJobsService.from_environment(env_name, provider_name, self.config_dir)
        desired = cron_job_configs_from_resources(resources)
        live = service.search()
        diff = service.compute_diff(desired, live, add_only=add_only)

        outcomes: list[ResourceOutcome] = []

        for job in diff.adds:
            outcomes.append(
                ResourceOutcome(
                    address=f"opnsense_cron_job.{job.name}",
                    action="add",
                    resource_name=job.name,
                )
            )

        for _, want in diff.updates:
            outcomes.append(
                ResourceOutcome(
                    address=f"opnsense_cron_job.{want.name}",
                    action="update",
                    resource_name=want.name,
                )
            )

        for live_job in diff.deletes:
            synthetic_name = live_job.managed_name or f"cron-job-{live_job.uuid}"
            outcomes.append(
                ResourceOutcome(
                    address=f"opnsense_cron_job.{synthetic_name}",
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
        """Delete every managed cron job named in ``resources``.

        Locked entries (``lock: true``) are skipped and counted under
        ``locked_skipped``. The destroy path calls ``service.reconfigure()``
        directly because the finalization hook only fires for apply paths.

        Args:
            env_name: Active environment name.
            resources: Cron-job ``ResourceConfig`` entries to destroy.
            auto_approve: Currently a no-op.
            provider_name: Provider identifier (defaults to
                ``opnsense``).

        Returns:
            Dict with ``resources_destroyed`` and ``locked_skipped`` counts.
        """
        del auto_approve
        service = CronJobsService.from_environment(env_name, provider_name, self.config_dir)
        desired = cron_job_configs_from_resources(resources)
        live = service.search()

        live_by_name: dict[str, LiveCronJob] = {
            entry.managed_name: entry for entry in live if entry.managed_name is not None
        }

        deleted = 0
        locked_skipped = 0
        for job in desired:
            if job.lock:
                locked_skipped += 1
                continue
            existing = live_by_name.get(job.name)
            if existing is None:
                continue
            service.delete(existing.uuid)
            deleted += 1

        if deleted:
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
        """Return ``{resource_name: opnsense_uuid}`` for live managed cron jobs.

        Used by the AcmeClient cross-reference mechanism (and future
        state tracking) to look up cron-job UUIDs by operator name.

        Args:
            env_name: Active environment name.
            resources: Cron-job ``ResourceConfig`` entries (used to scope
                output to desired resource names only).
            provider_name: Provider identifier (defaults to
                ``opnsense``).

        Returns:
            Mapping ``{operator_name: uuid}`` for live managed jobs.
        """
        service = CronJobsService.from_environment(env_name, provider_name, self.config_dir)
        desired = cron_job_configs_from_resources(resources)
        live = service.search()
        live_by_name: dict[str, LiveCronJob] = {
            entry.managed_name: entry for entry in live if entry.managed_name is not None
        }

        result: dict[str, str] = {}
        for job in desired:
            existing = live_by_name.get(job.name)
            if existing is not None:
                result[job.name] = existing.uuid
        return result

    def list(self, env_name: str, *, provider_name: str = "opnsense") -> list[LiveCronJob]:
        """Return the live cron jobs on the OPNsense box.

        Args:
            env_name: Active environment name.
            provider_name: Provider identifier (defaults to
                ``opnsense``).

        Returns:
            All live ``LiveCronJob`` entries (managed and unmanaged).
        """
        service = CronJobsService.from_environment(env_name, provider_name, self.config_dir)
        return service.search()

    def migrate(
        self,
        env_name: str,
        *,
        provider_name: str = "opnsense",
    ) -> str:
        """Export current managed cron jobs to InfraFoundry YAML.

        Args:
            env_name: Active environment name.
            provider_name: Provider identifier (defaults to
                ``opnsense``).

        Returns:
            YAML string with the nested ``opnsense:`` namespace and a
            ``cron.jobs`` list leaf.
        """
        service = CronJobsService.from_environment(env_name, provider_name, self.config_dir)
        return service.export_to_yaml()
