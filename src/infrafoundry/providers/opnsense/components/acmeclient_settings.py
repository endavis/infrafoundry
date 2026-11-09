"""ACME-client settings component manager for OPNsense (#790).

Manager for the ``acmeclient.settings`` singleton of the ``os-acme-client`` plugin.
Only declared fields are compared; the whole live settings object is echoed back on
write. Destroy is a no-op. The ``acmeclient_reconfigure`` finalization hook (shared
with the four list managers) reconfigures once per apply.

The renewal cron job is plugin-managed: after a write with ``enabled`` and
``autoRenewal`` both on, the manager calls ``settings/fetchCronIntegration`` so the
plugin creates or repairs its own job. A 404 at plan means the plugin is not installed
yet; the plan carries a warning (``system.firmware`` may install it in the same apply)
and a 404 at apply still raises.
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from infrafoundry.core.exceptions import APIError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.types import ResourceOutcome

from ..services.acmeclient_settings import AcmeClientSettingsService
from ._singleton import SingletonDiff, enforce_singleton
from .base import BaseComponentManager

logger = logging.getLogger(__name__)

#: Plan warning shared with the list managers when the plugin is not installed.
PLUGIN_MISSING_WARNING = "os-acme-client is not installed; declare it under system.firmware plugins"


class AcmeClientSettingsManager(BaseComponentManager):
    """Manager for the ACME-client settings singleton."""

    FINALIZATION_HOOK: ClassVar[str] = "acmeclient_reconfigure"

    def _drift(
        self, env_name: str, resources: list[ResourceConfig], provider_name: str
    ) -> tuple[AcmeClientSettingsService, dict[str, Any], dict[str, str] | None]:
        enforce_singleton(resources, "acmeclient.settings")
        service = AcmeClientSettingsService.from_environment(
            env_name, provider_name, self.config_dir
        )
        desired = service.build_desired(resources[0])
        settings = service.live_settings(service.get_settings())
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
        """Compute the singleton diff for the declared fields.

        A 404 from the plugin controller means ``os-acme-client`` is not installed:
        the whole declared map is the update, with a warning.
        """
        del add_only
        try:
            _, _, diff = self._drift(env_name, resources, provider_name)
        except APIError as exc:
            if exc.status_code != 404:
                raise
            service = AcmeClientSettingsService.from_environment(
                env_name, provider_name, self.config_dir
            )
            desired = service.build_desired(resources[0])
            return SingletonDiff(desired or None, warnings=[PLUGIN_MISSING_WARNING])
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
        """Write the settings when a declared field drifted, then fix the cron job.

        Reconfigure is not called here; the ``acmeclient_reconfigure`` hook fires.
        """
        del auto_approve, add_only
        service, settings, diff = self._drift(env_name, resources, provider_name)
        outcomes: list[ResourceOutcome] = []
        if diff is not None:
            logger.info("acmeclient.settings: updating fields %s", sorted(diff))
            payload = service.build_set_payload(settings, diff)
            service.set_settings(payload)
            if service.renewal_effective(payload):
                logger.info("acmeclient.settings: renewal is on; fetching cron integration")
                service.fetch_cron_integration()
            outcomes.append(
                ResourceOutcome(
                    address="opnsense_acmeclient_settings.settings",
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
        """Export the live ACME-client settings to YAML."""
        service = AcmeClientSettingsService.from_environment(
            env_name, provider_name, self.config_dir
        )
        return service.export_to_yaml()
