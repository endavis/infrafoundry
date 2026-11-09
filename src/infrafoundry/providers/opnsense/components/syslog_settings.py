"""Syslog-settings component manager for OPNsense (#804).

Manager for the ``syslog.settings`` singleton: the local syslog daemon's ``general``
section. Only declared fields are compared; the whole live ``general`` object is
echoed back on write. Destroy is a no-op. The ``syslog_reconfigure`` finalization
hook reconfigures once per apply. The set and reconfigure calls are unverified
against a live box.
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.types import ResourceOutcome

from ..services.syslog_settings import SyslogSettingsService
from ._singleton import SingletonDiff, enforce_singleton
from .base import BaseComponentManager

logger = logging.getLogger(__name__)


class SyslogSettingsManager(BaseComponentManager):
    """Manager for the syslog-settings singleton."""

    FINALIZATION_HOOK: ClassVar[str] = "syslog_reconfigure"

    def _drift(
        self, env_name: str, resources: list[ResourceConfig], provider_name: str
    ) -> tuple[SyslogSettingsService, dict[str, Any], dict[str, str] | None]:
        enforce_singleton(resources, "syslog.settings")
        service = SyslogSettingsService.from_environment(env_name, provider_name, self.config_dir)
        desired = service.build_desired(resources[0])
        general = service.live_general(service.get_settings())
        diff = service.drift(service.extract_live(general, desired), desired)
        return service, general, diff

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
        """Write the syslog settings when a declared field drifted.

        Reconfigure is not called here; the ``syslog_reconfigure`` hook fires.
        """
        del auto_approve, add_only
        service, general, diff = self._drift(env_name, resources, provider_name)
        outcomes: list[ResourceOutcome] = []
        if diff is not None:
            logger.info("syslog.settings: updating fields %s", sorted(diff))
            service.set_settings(service.build_set_payload(general, diff))
            outcomes.append(
                ResourceOutcome(
                    address="opnsense_syslog_settings.settings",
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
        """Export the live syslog ``general`` settings to YAML."""
        service = SyslogSettingsService.from_environment(env_name, provider_name, self.config_dir)
        return service.export_to_yaml()
