"""Monit settings component manager for OPNsense (ADR-0014, #791).

Manager for the ``monit.settings`` singleton. Only declared fields are compared; the
flattened live ``general`` section is echoed back on write, except a live secret field the
operator did not declare. ``password``, ``httpd_password`` and ``mmonit_url`` are
``secret://`` URIs resolved through :func:`~._secrets.resolve_resource_secrets`; they are
never logged, put in an exception or shown in a plan map. Destroy is a no-op. The
``monit_reconfigure`` finalization hook reconfigures once per apply. Monit is core
OPNsense, so there is no missing-plugin tolerance.
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.types import ResourceOutcome

from ..services.monit_settings import MonitSettingsService, redacted
from ._secrets import resolve_resource_secrets
from ._singleton import SingletonDiff, enforce_singleton
from .base import BaseComponentManager

logger = logging.getLogger(__name__)

_TYPE = "monit.settings"


class MonitSettingsManager(BaseComponentManager):
    """Manager for the monit settings singleton."""

    FINALIZATION_HOOK: ClassVar[str] = "monit_reconfigure"

    def _drift(
        self, env_name: str, resources: list[ResourceConfig], provider_name: str
    ) -> tuple[MonitSettingsService, dict[str, Any], dict[str, str], list[str]]:
        enforce_singleton(resources, _TYPE)
        resolved = resolve_resource_secrets(self.config_dir, env_name, resources, _TYPE)
        service = MonitSettingsService.from_environment(env_name, provider_name, self.config_dir)
        desired = service.build_desired(resolved[0])
        general = service.live_general(service.get_model())
        changed = service.drift(service.extract_live(general, desired), desired)
        return service, general, desired, changed

    def plan(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        add_only: bool = False,
        provider_name: str = "opnsense",
    ) -> SingletonDiff:
        """Compute the singleton diff for the declared fields; secrets are redacted."""
        del add_only
        _, _, desired, changed = self._drift(env_name, resources, provider_name)
        return SingletonDiff(redacted(desired) if changed else None)

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

        Reconfigure is not called here; the ``monit_reconfigure`` hook fires.
        """
        del auto_approve, add_only
        service, general, desired, changed = self._drift(env_name, resources, provider_name)
        outcomes: list[ResourceOutcome] = []
        if changed:
            logger.info("monit.settings: updating fields %s", sorted(changed))
            service.set_settings(service.build_set_payload(general, desired))
            outcomes.append(
                ResourceOutcome(
                    address="opnsense_monit_settings.settings",
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

    def migrate(self, env_name: str, *, provider_name: str = "opnsense") -> str:
        """Export the live settings; a non-empty secret is only a placeholder."""
        service = MonitSettingsService.from_environment(env_name, provider_name, self.config_dir)
        return service.export_to_yaml()
