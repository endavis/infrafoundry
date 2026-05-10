"""System tuning (sysctl) component manager for OPNsense (#806).

Singleton component manager for the ``system.tuning`` dotted resource
type — the optional 7th #806 surface. Manages OPNsense system tunables
(sysctl items) via the ``diagnostics/system/sysctl/*`` controller.

Empty on both source and target boxes today; included so future operator
sysctl tweaks have a typed home rather than living in YAML as untyped
metadata.
"""

from __future__ import annotations

from typing import Any

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.types import ResourceOutcome

from ..services.system_tuning import SystemTuningService
from ._singleton import SingletonDiff, diff_singleton, enforce_singleton
from .base import BaseComponentManager


class SystemTuningManager(BaseComponentManager):
    """Manager for OPNsense system-tuning singleton operations."""

    def plan(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        add_only: bool = False,
        provider_name: str = "opnsense",
    ) -> SingletonDiff:
        """Compute the singleton diff for the sysctl items collection."""
        del add_only
        enforce_singleton(resources, "system.tuning")
        service = SystemTuningService.from_environment(env_name, provider_name, self.config_dir)
        live = service.extract_tuning_fields(service.get_settings())
        desired = service.build_desired_tuning_fields(resources[0])
        return SingletonDiff(diff_singleton(live, desired))

    def apply(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        auto_approve: bool = True,
        add_only: bool = False,
        provider_name: str = "opnsense",
    ) -> dict[str, Any]:
        """Apply the singleton diff: write sysctl items if drifted."""
        del auto_approve, add_only
        enforce_singleton(resources, "system.tuning")
        service = SystemTuningService.from_environment(env_name, provider_name, self.config_dir)
        live = service.extract_tuning_fields(service.get_settings())
        desired = service.build_desired_tuning_fields(resources[0])
        diff = diff_singleton(live, desired)

        if diff is None:
            return {
                "success": True,
                "resources_created": 0,
                "resources_updated": 0,
                "resources_deleted": 0,
                "resource_outcomes": [],
            }

        service.set_settings({"sysctl": diff})
        return {
            "success": True,
            "resources_created": 0,
            "resources_updated": 1,
            "resources_deleted": 0,
            "resource_outcomes": [
                ResourceOutcome(
                    address="opnsense_system_tuning.settings",
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

    def get_resource_ids(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        provider_name: str = "opnsense",
    ) -> dict[str, str]:
        """Return the singleton's stable id."""
        del env_name, resources, provider_name
        return {"settings": "global"}

    def migrate(
        self,
        env_name: str,
        *,
        provider_name: str = "opnsense",
    ) -> str:
        """Export current sysctl tuning settings to InfraFoundry YAML."""
        service = SystemTuningService.from_environment(env_name, provider_name, self.config_dir)
        return service.export_to_yaml()
