"""Tailscale settings component manager for OPNsense (#787).

Manager for the ``tailscale.settings`` singleton of the ``os-tailscale`` plugin. Only
declared fields are compared; the live settings object (without its nested ``subnets``
list) is echoed back on write. Destroy is a no-op. The ``tailscale_reconfigure``
finalization hook (shared with ``tailscale.auth`` and ``tailscale.subnets``)
reconfigures once per apply.

A 404 at plan means the plugin is not installed yet; the plan carries a warning and a
404 at apply still raises. A declared ``use_exit_node`` the box does not offer is a plan
warning and an apply error, because the offers depend on peers.
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from infrafoundry.core.exceptions import APIError, InvalidConfigurationError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.types import ResourceOutcome

from ..services.tailscale_settings import TailscaleSettingsService
from ._singleton import SingletonDiff, enforce_singleton
from .base import BaseComponentManager

logger = logging.getLogger(__name__)

#: Plan warning when the plugin is not installed.
PLUGIN_MISSING_WARNING = "os-tailscale is not installed; declare it under system.firmware plugins"


class TailscaleSettingsManager(BaseComponentManager):
    """Manager for the Tailscale settings singleton."""

    FINALIZATION_HOOK: ClassVar[str] = "tailscale_reconfigure"

    def _drift(
        self, env_name: str, resources: list[ResourceConfig], provider_name: str
    ) -> tuple[TailscaleSettingsService, dict[str, Any], dict[str, str], dict[str, str] | None]:
        enforce_singleton(resources, "tailscale.settings")
        service = TailscaleSettingsService.from_environment(
            env_name, provider_name, self.config_dir
        )
        desired = service.build_desired(resources[0])
        settings = service.live_settings(service.get_settings())
        diff = service.drift(service.extract_live(settings, desired), desired)
        return service, settings, desired, diff

    @staticmethod
    def _exit_node_problem(
        service: TailscaleSettingsService, settings: dict[str, Any], desired: dict[str, str]
    ) -> str | None:
        value = desired.get("use_exit_node")
        if value in (None, ""):
            return None
        if value in service.exit_node_offers(settings):
            return None
        return "tailscale.settings use_exit_node is not offered by the box"

    def plan(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        add_only: bool = False,
        provider_name: str = "opnsense",
    ) -> SingletonDiff:
        """Compute the singleton diff for the declared fields.

        A 404 means ``os-tailscale`` is not installed: the whole declared map is the
        update, with a warning.
        """
        del add_only
        try:
            service, settings, desired, diff = self._drift(env_name, resources, provider_name)
        except APIError as exc:
            if exc.status_code != 404:
                raise
            service = TailscaleSettingsService.from_environment(
                env_name, provider_name, self.config_dir
            )
            desired = service.build_desired(resources[0])
            return SingletonDiff(desired or None, warnings=[PLUGIN_MISSING_WARNING])
        problem = self._exit_node_problem(service, settings, desired)
        return SingletonDiff(diff, warnings=[problem] if problem else None)

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

        Reconfigure is not called here; the ``tailscale_reconfigure`` hook fires.

        Raises:
            InvalidConfigurationError: If ``use_exit_node`` is not offered by the box.
        """
        del auto_approve, add_only
        service, settings, desired, diff = self._drift(env_name, resources, provider_name)
        problem = self._exit_node_problem(service, settings, desired)
        if problem:
            raise InvalidConfigurationError(problem)
        outcomes: list[ResourceOutcome] = []
        if diff is not None:
            logger.info("tailscale.settings: updating fields %s", sorted(diff))
            service.set_settings(service.build_set_payload(settings, diff))
            outcomes.append(
                ResourceOutcome(
                    address="opnsense_tailscale_settings.settings",
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
        """Export the live Tailscale settings to YAML."""
        service = TailscaleSettingsService.from_environment(
            env_name, provider_name, self.config_dir
        )
        return service.export_to_yaml()
