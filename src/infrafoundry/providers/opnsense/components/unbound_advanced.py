"""Unbound advanced-settings component manager for OPNsense (#1254).

Manager for the ``unbound.advanced`` singleton: private domains, insecure
domains and private addresses. Only declared fields are compared; the whole
live ``advanced`` section is echoed back on write. Destroy is a no-op. The
``unbound_reconfigure`` finalization hook reconfigures Unbound once per apply.
The ``set`` envelope key is unverified live (see the service module).
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.types import ResourceOutcome

from ..services.unbound_advanced import UnboundAdvancedService
from ._singleton import SingletonDiff, enforce_singleton
from .base import BaseComponentManager

logger = logging.getLogger(__name__)


class UnboundAdvancedManager(BaseComponentManager):
    """Manager for the Unbound advanced settings singleton."""

    #: Shared with the other unbound managers; fires one reconfigure per apply.
    FINALIZATION_HOOK: ClassVar[str] = "unbound_reconfigure"

    def _drift(
        self, env_name: str, resources: list[ResourceConfig], provider_name: str
    ) -> tuple[UnboundAdvancedService, dict[str, Any], dict[str, list[str]] | None]:
        enforce_singleton(resources, "unbound.advanced")
        service = UnboundAdvancedService.from_environment(env_name, provider_name, self.config_dir)
        desired = service.build_desired(resources[0])
        advanced = service.live_advanced(service.get_settings())
        diff = service.drift(service.extract_live(advanced), desired)
        return service, advanced, diff

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
        """Write the advanced settings when a declared field drifted.

        Reconfigure is not called here; the ``unbound_reconfigure`` hook fires.
        """
        del auto_approve, add_only
        service, advanced, diff = self._drift(env_name, resources, provider_name)
        outcomes: list[ResourceOutcome] = []
        if diff is not None:
            logger.info("unbound.advanced: updating fields %s", sorted(diff))
            service.set_settings(service.build_set_payload(advanced, diff))
            outcomes.append(
                ResourceOutcome(
                    address="opnsense_unbound_advanced.settings",
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
