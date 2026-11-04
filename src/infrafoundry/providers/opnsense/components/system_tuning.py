"""System tuning (sysctl) component manager for OPNsense (#806, #1149).

Manager for the ``system.tuning`` dotted resource type. Uses the 26.1
``core/tunables/*`` controller: each tunable named in YAML is added or
updated, matched by tunable name. Tunables not named in YAML (the box
defaults) are never touched, and destroy is a no-op. The reads were
verified live on 26.1.6_2; the writes are unverified (MVC convention).
"""

from __future__ import annotations

from typing import Any, ClassVar

from infrafoundry.core.exceptions import InvalidConfigurationError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.types import ResourceOutcome

from ..services.system_tuning import SystemTuningService
from ._singleton import enforce_singleton
from .base import BaseComponentManager


class _TuningDiff:
    """Plan-shape diff with the same surface as ``SingletonDiff``."""

    def __init__(self, adds: list[dict[str, Any]], updates: list[dict[str, Any]]) -> None:
        """Initialize with per-tunable adds and updates."""
        self.adds = adds
        self.updates = updates
        self.deletes: list[Any] = []
        self.locked: list[Any] = []

    @property
    def is_empty(self) -> bool:
        """Return True when there is nothing to add or update."""
        return not self.adds and not self.updates


class SystemTuningManager(BaseComponentManager):
    """Manager for OPNsense system tunables (per-tunable add/update)."""

    #: Fires one ``core/tunables/reconfigure`` per apply when any tunable
    #: changed (the apply path never reconfigures itself).
    FINALIZATION_HOOK: ClassVar[str] = "tunables_reconfigure"

    def _changes(
        self, env_name: str, resources: list[ResourceConfig], provider_name: str
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        enforce_singleton(resources, "system.tuning")
        service = SystemTuningService.from_environment(env_name, provider_name, self.config_dir)
        desired = service.build_desired_tunables(resources[0])
        names = [entry["tunable"] for entry in desired]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            raise InvalidConfigurationError(
                f"system.tuning lists tunable(s) more than once: {', '.join(duplicates)}"
            )
        live = service.extract_live_tunables(service.get_tunables())
        return service.compute_changes(desired, live)

    def plan(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        add_only: bool = False,
        provider_name: str = "opnsense",
    ) -> _TuningDiff:
        """Compute per-tunable adds and updates; live-only tunables are ignored."""
        del add_only
        adds, updates = self._changes(env_name, resources, provider_name)
        return _TuningDiff(adds, updates)

    def apply(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        auto_approve: bool = True,
        add_only: bool = False,
        provider_name: str = "opnsense",
    ) -> dict[str, Any]:
        """Add and update the tunables named in YAML.

        Reconfigure is not called here; the ``tunables_reconfigure``
        finalization hook fires once when anything changed.
        """
        del auto_approve, add_only
        adds, updates = self._changes(env_name, resources, provider_name)
        service = SystemTuningService.from_environment(env_name, provider_name, self.config_dir)
        outcomes: list[ResourceOutcome] = []
        for entry in adds:
            service.add_tunable(entry)
            outcomes.append(
                ResourceOutcome(
                    address=f"opnsense_system_tunable.{entry['tunable']}",
                    action="add",
                    resource_name=entry["tunable"],
                )
            )
        for entry in updates:
            service.set_tunable(entry["uuid"], entry)
            outcomes.append(
                ResourceOutcome(
                    address=f"opnsense_system_tunable.{entry['tunable']}",
                    action="update",
                    resource_name=entry["tunable"],
                )
            )
        return {
            "success": True,
            "resources_created": len(adds),
            "resources_updated": len(updates),
            "resources_deleted": 0,
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
