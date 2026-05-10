"""System hostname component manager for OPNsense (#806).

Singleton component manager for the ``system.hostname`` dotted resource
type. Implements the standard ``plan`` / ``apply`` / ``destroy`` /
``get_resource_ids`` surface so that ``OPNsenseDirectRunner`` can dispatch
hostname/domain/timezone/language alongside the other direct-API
components.

Singleton semantics (per the #806 plan, validated against ADR-0016 §4):

- Plan / apply enforce ``len(resources) == 1`` defensively even though
  the loader's structural discrimination already guarantees this for
  dict-shape paths.
- Destroy is a no-op (return zero counts) — global system settings are
  never auto-uninstalled.
- ``get_resource_ids()`` returns ``{"settings": "global"}`` — the
  singleton resource always lives at the same logical key.
"""

from __future__ import annotations

from typing import Any

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.types import ResourceOutcome

from ..services.system_hostname import SystemHostnameService
from ._singleton import SingletonDiff, diff_singleton, enforce_singleton
from .base import BaseComponentManager


class SystemHostnameManager(BaseComponentManager):
    """Manager for OPNsense system-hostname singleton operations."""

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
    ) -> SingletonDiff:
        """Compute the diff between live OPNsense state and the YAML singleton.

        Args:
            env_name: Active environment name.
            resources: Should contain exactly one ``system.hostname``
                ``ResourceConfig`` (singleton).
            add_only: Honored for protocol shape but a no-op for singletons —
                singletons can't be deleted.
            provider_name: Provider identifier (defaults to ``opnsense``).

        Returns:
            ``SingletonDiff`` exposing ``adds``/``updates``/``deletes``/
            ``locked``/``is_empty`` so the runner's
            ``_format_plan_summary`` can read it uniformly with
            list-shape components. For singletons, ``adds``/``deletes``
            are always empty; ``updates`` carries zero or one entry (the
            desired field map).

        Raises:
            InvalidConfigurationError: If ``len(resources) != 1`` (would
                indicate a loader bug or a malformed YAML that bypassed
                the structural discriminator).
        """
        del add_only
        enforce_singleton(resources, "system.hostname")
        service = SystemHostnameService.from_environment(env_name, provider_name, self.config_dir)
        live = service.extract_hostname_fields(service.get_settings())
        desired = service.build_desired_hostname_fields(resources[0])
        diff = diff_singleton(live, desired)
        return SingletonDiff(diff)

    def apply(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        auto_approve: bool = True,
        add_only: bool = False,
        provider_name: str = "opnsense",
    ) -> dict[str, Any]:
        """Apply the singleton diff: write hostname settings if drifted.

        Args:
            env_name: Active environment name.
            resources: Should contain exactly one ``system.hostname``
                ``ResourceConfig``.
            auto_approve: No-op (the diff engine is the gate).
            add_only: No-op for singletons.
            provider_name: Provider identifier.

        Returns:
            Dict with ``resources_updated`` count and ``resource_outcomes``.
        """
        del auto_approve, add_only
        enforce_singleton(resources, "system.hostname")
        service = SystemHostnameService.from_environment(env_name, provider_name, self.config_dir)
        live = service.extract_hostname_fields(service.get_settings())
        desired = service.build_desired_hostname_fields(resources[0])
        diff = diff_singleton(live, desired)

        if diff is None:
            return {
                "success": True,
                "resources_created": 0,
                "resources_updated": 0,
                "resources_deleted": 0,
                "resource_outcomes": [],
            }

        service.set_settings({"general": diff})
        return {
            "success": True,
            "resources_created": 0,
            "resources_updated": 1,
            "resources_deleted": 0,
            "resource_outcomes": [
                ResourceOutcome(
                    address="opnsense_system_hostname.settings",
                    action="update",
                    resource_name="settings",
                )
            ],
        }

    def destroy(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        auto_approve: bool = True,
        provider_name: str = "opnsense",
    ) -> dict[str, Any]:
        """No-op: global system singletons are never auto-uninstalled."""
        del env_name, resources, auto_approve, provider_name
        return {
            "success": True,
            "resources_destroyed": 0,
            "resource_outcomes": [],
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
        """Return ``{resource_name: stable_id}`` for the singleton.

        Singletons always live at the same logical key — there is no
        OPNsense UUID to track. The stable id ``"global"`` lets state
        tracking record one entry per env.
        """
        del env_name, resources, provider_name
        return {"settings": "global"}

    def migrate(
        self,
        env_name: str,
        *,
        provider_name: str = "opnsense",
    ) -> str:
        """Export current hostname settings to InfraFoundry YAML.

        Args:
            env_name: Active environment name.
            provider_name: Provider identifier.

        Returns:
            YAML string under the ``opnsense.system.hostname`` namespace.
        """
        service = SystemHostnameService.from_environment(env_name, provider_name, self.config_dir)
        return service.export_to_yaml()
