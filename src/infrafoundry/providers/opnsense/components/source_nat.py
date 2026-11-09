"""Outbound NAT mode component manager for OPNsense (#1333).

Manager for the ``firewall.source_nat`` singleton: the outbound NAT mode
(``automatic``, ``hybrid``, ``advanced`` or ``disabled``). Manual outbound rules
(``firewall.nat``) take effect only in ``hybrid`` or ``advanced`` mode. Destroy is a
no-op. The ``source_nat_apply`` finalization hook applies once per apply.
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.types import ResourceOutcome

from ..services.source_nat import SourceNatService
from ._singleton import SingletonDiff, enforce_singleton
from .base import BaseComponentManager

logger = logging.getLogger(__name__)


class SourceNatManager(BaseComponentManager):
    """Manager for the outbound NAT mode singleton."""

    FINALIZATION_HOOK: ClassVar[str] = "source_nat_apply"

    def _drift(
        self, env_name: str, resources: list[ResourceConfig], provider_name: str
    ) -> tuple[SourceNatService, dict[str, str] | None]:
        enforce_singleton(resources, "firewall.source_nat")
        service = SourceNatService.from_environment(env_name, provider_name, self.config_dir)
        desired = service.build_desired(resources[0])
        general = service.live_general(service.get_settings())
        diff = service.drift(service.extract_live(general, desired), desired)
        return service, diff

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
        _, diff = self._drift(env_name, resources, provider_name)
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
        """Write the outbound NAT mode when it drifted.

        The apply call is not made here; the ``source_nat_apply`` hook fires it.
        """
        del auto_approve, add_only
        service, diff = self._drift(env_name, resources, provider_name)
        outcomes: list[ResourceOutcome] = []
        if diff is not None:
            logger.info("firewall.source_nat: updating fields %s", sorted(diff))
            service.set_settings(diff)
            outcomes.append(
                ResourceOutcome(
                    address="opnsense_firewall_source_nat.general",
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
        """No-op: the outbound NAT mode is never reset."""
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
        """Export the live outbound NAT mode to YAML."""
        service = SourceNatService.from_environment(env_name, provider_name, self.config_dir)
        return service.export_to_yaml()
