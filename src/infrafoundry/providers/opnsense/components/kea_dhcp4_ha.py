"""Kea DHCPv4 high-availability settings manager for OPNsense (#1392).

Manager for the ``kea.dhcp4.ha`` singleton (the ``dhcpv4.ha`` section of the Kea DHCPv4
model). Only declared fields are compared; the live ``ha`` section is echoed back on
write, never ``general`` or ``lexpire``. Destroy is a no-op: remove HA by declaring
``enabled: false``. The ``kea_reconfigure`` finalization hook (shared with the other Kea
managers and ``kea.dhcp4.ha_peers``) reconfigures once per apply.
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.types import ResourceOutcome

from ..services.kea_dhcp4_ha import KeaHASettingsService
from ._singleton import SingletonDiff, enforce_singleton
from .base import BaseComponentManager

logger = logging.getLogger(__name__)

_TYPE = "kea.dhcp4.ha"


class KeaDHCPv4HAManager(BaseComponentManager):
    """Manager for the Kea DHCPv4 HA settings singleton."""

    FINALIZATION_HOOK: ClassVar[str] = "kea_reconfigure"

    def _drift(
        self, env_name: str, resources: list[ResourceConfig], provider_name: str
    ) -> tuple[KeaHASettingsService, dict[str, Any], dict[str, str], dict[str, str] | None]:
        enforce_singleton(resources, _TYPE)
        service = KeaHASettingsService.from_environment(env_name, provider_name, self.config_dir)
        desired = service.build_desired(resources[0])
        ha = service.live_ha(service.get_settings())
        diff = service.drift(service.extract_live(ha, desired), desired)
        return service, ha, desired, diff

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
        _, _, _, diff = self._drift(env_name, resources, provider_name)
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
        """Write the HA section when a declared field drifted.

        Reconfigure is not called here; the ``kea_reconfigure`` hook fires.
        """
        del auto_approve, add_only
        service, ha, _, diff = self._drift(env_name, resources, provider_name)
        outcomes: list[ResourceOutcome] = []
        if diff is not None:
            logger.info("%s: updating fields %s", _TYPE, sorted(diff))
            service.set_settings(service.build_set_payload(ha, diff))
            outcomes.append(
                ResourceOutcome(
                    address="opnsense_kea_ha.settings",
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
        """No-op: HA is never reset; declare ``enabled: false`` to turn it off."""
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

    def migrate(self, env_name: str, *, provider_name: str = "opnsense") -> str:
        """Export the live Kea DHCPv4 HA settings to YAML."""
        service = KeaHASettingsService.from_environment(env_name, provider_name, self.config_dir)
        return service.export_to_yaml()
