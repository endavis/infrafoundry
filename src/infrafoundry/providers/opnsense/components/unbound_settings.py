"""Unbound general and advanced settings component manager for OPNsense (#1091).

Manager for the ``unbound.settings`` singleton. Only declared fields are compared;
each declared live section is echoed back whole on write. Destroy is a no-op. The
``unbound_reconfigure`` finalization hook reconfigures Unbound once per apply.
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.types import ResourceOutcome

from ..services.unbound_settings import Desired, UnboundSettingsService
from ._singleton import SingletonDiff, enforce_singleton
from .base import BaseComponentManager

logger = logging.getLogger(__name__)


class UnboundSettingsManager(BaseComponentManager):
    """Manager for the Unbound general and advanced settings singleton."""

    #: Shared with the other unbound managers; fires one reconfigure per apply.
    FINALIZATION_HOOK: ClassVar[str] = "unbound_reconfigure"

    def _drift(
        self, env_name: str, resources: list[ResourceConfig], provider_name: str
    ) -> tuple[UnboundSettingsService, dict[str, Any], Desired | None]:
        enforce_singleton(resources, "unbound.settings")
        service = UnboundSettingsService.from_environment(env_name, provider_name, self.config_dir)
        desired = service.build_desired(resources[0])
        live = service.live_sections(service.get_settings(), desired)
        diff = service.drift(service.extract_live(live, desired), desired)
        return service, live, diff

    def plan(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        add_only: bool = False,
        provider_name: str = "opnsense",
    ) -> SingletonDiff:
        """Compute the singleton diff for the declared fields."""
        del add_only
        _, _, diff = self._drift(env_name, resources, provider_name)
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
        """Write the settings when a declared field drifted.

        Reconfigure is not called here; the ``unbound_reconfigure`` hook fires.
        """
        del auto_approve, add_only
        service, live, diff = self._drift(env_name, resources, provider_name)
        outcomes: list[ResourceOutcome] = []
        if diff is not None:
            logger.info(
                "unbound.settings: updating fields %s",
                sorted(f"{section}.{wire}" for section, values in diff.items() for wire in values),
            )
            service.set_settings(service.build_set_payload(live, diff))
            outcomes.append(
                ResourceOutcome(
                    address="opnsense_unbound_settings.settings",
                    action="update",
                    resource_name=resources[0].name,
                )
            )
        return {
            "success": True,
            "resources_created": 0,
            "resources_updated": len(outcomes),
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
        """No-op: global settings are never reset."""
        del env_name, resources, auto_approve, provider_name
        return {"success": True, "resources_destroyed": 0, "resource_outcomes": []}

    def get_resource_ids(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        provider_name: str = "opnsense",
    ) -> dict[str, str]:
        """Return the singleton's stable id."""
        del env_name, provider_name
        return {resource.name: "global" for resource in resources}

    def migrate(
        self,
        env_name: str,
        *,
        provider_name: str = "opnsense",
    ) -> str:
        """Export the supported general and advanced settings present on the box to YAML."""
        service = UnboundSettingsService.from_environment(env_name, provider_name, self.config_dir)
        return service.export_to_yaml()
