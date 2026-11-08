"""Interface-settings component manager for OPNsense (#1092).

Manager for the ``interfaces.settings`` singleton: hardware offloading, VLAN
hardware filtering, IPv6 and the DHCPv6 client. Only declared fields are compared;
the whole live ``settings`` object is echoed back on write. Destroy is a no-op.
The ``hostdiscovery_reconfigure`` finalization hook reconfigures once per
apply. The set and reconfigure calls are unverified against a live box.
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.types import ResourceOutcome

from ..services.hostdiscovery import HostDiscoveryService
from ._singleton import SingletonDiff, enforce_singleton
from .base import BaseComponentManager

logger = logging.getLogger(__name__)


class HostDiscoveryManager(BaseComponentManager):
    """Manager for the host-discovery singleton."""

    FINALIZATION_HOOK: ClassVar[str] = "hostdiscovery_reconfigure"

    #: Depends on ``interfaces.assignments``, so the runner deletes in its own phase
    #: (#1269). Destroy is a no-op here, so nothing is ever deleted.
    SPLIT_DELETE_PHASE: ClassVar[bool] = True

    def _drift(
        self, env_name: str, resources: list[ResourceConfig], provider_name: str
    ) -> tuple[HostDiscoveryService, dict[str, Any], dict[str, Any] | None]:
        enforce_singleton(resources, "hostdiscovery")
        service = HostDiscoveryService.from_environment(env_name, provider_name, self.config_dir)
        desired = service.build_desired(resources[0])
        settings = service.live_general(service.get_settings())
        diff = service.drift(service.extract_live(settings, desired), desired)
        return service, settings, diff

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
        deletes_only: bool = False,
        provider_name: str = "opnsense",
    ) -> dict[str, Any]:
        """Write the host-discovery settings when a declared field drifted.

        Reconfigure is not called here; the ``hostdiscovery_reconfigure``
        hook fires.

        Args:
            env_name: Active environment name.
            resources: Should contain exactly one ``hostdiscovery`` resource.
            auto_approve: No-op.
            add_only: No-op (the singleton is never deleted).
            deletes_only: If True, do nothing: the runner's delete phase. There
                is nothing to delete, so the box is neither read nor written.
            provider_name: Provider identifier (defaults to ``opnsense``).

        Returns:
            Dict with counts and ``resource_outcomes``.
        """
        del auto_approve, add_only
        if deletes_only:
            return {
                "success": True,
                "resources_created": 0,
                "resources_updated": 0,
                "resources_deleted": 0,
                "resource_outcomes": [],
            }
        service, settings, diff = self._drift(env_name, resources, provider_name)
        outcomes: list[ResourceOutcome] = []
        if diff is not None:
            logger.info("hostdiscovery: updating fields %s", sorted(diff))
            service.set_settings(service.build_set_payload(settings, diff))
            outcomes.append(
                ResourceOutcome(
                    address="opnsense_hostdiscovery.hostdiscovery",
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
        """Export the live host-discovery settings to YAML."""
        service = HostDiscoveryService.from_environment(env_name, provider_name, self.config_dir)
        return service.export_to_yaml()
