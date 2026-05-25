"""Tailscale settings component manager for OPNsense (#787).

Singleton component manager for the ``tailscale.settings`` dotted resource
type. Implements the standard ``plan`` / ``apply`` / ``destroy`` /
``get_resource_ids`` surface so that ``OPNsenseDirectRunner`` can dispatch
tailscale scalar settings alongside the other direct-API components.

Singleton semantics:

- Plan / apply enforce ``len(resources) == 1`` defensively.
- Destroy is a no-op (global plugin settings are never auto-uninstalled).
- ``get_resource_ids()`` returns ``{"settings": "global"}``.

Apply path uses :meth:`TailscaleService.apply_settings_patch` so that
posting scalar settings does NOT clobber the embedded subnets list (the
``tailscale/settings/set`` endpoint is full-replace; the service helper
handles the read-modify-write).

Reconfiguration is deferred to the runner's ``tailscale_reconfigure``
finalization hook which is shared by all three tailscale managers.
"""

from __future__ import annotations

from typing import Any, ClassVar

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.types import ResourceOutcome

from ..services.tailscale import TailscaleService
from ._singleton import SingletonDiff, diff_singleton, enforce_singleton
from .base import BaseComponentManager


class TailscaleSettingsManager(BaseComponentManager):
    """Manager for OPNsense tailscale scalar-settings singleton."""

    #: Shared tailscale finalization hook (#787). Fired once per apply
    #: when any of the three tailscale managers mutated state.
    FINALIZATION_HOOK: ClassVar[str] = "tailscale_reconfigure"

    def plan(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        add_only: bool = False,
        provider_name: str = "opnsense",
    ) -> SingletonDiff:
        """Compute the diff between live tailscale settings and the YAML singleton.

        Args:
            env_name: Active environment name.
            resources: Should contain exactly one ``tailscale.settings``
                ``ResourceConfig`` (singleton).
            add_only: No-op for singletons — singletons cannot be deleted.
            provider_name: Provider identifier (defaults to ``opnsense``).

        Returns:
            ``SingletonDiff`` exposing the standard plan-shape surface.

        Raises:
            InvalidConfigurationError: If ``len(resources) != 1``.
        """
        del add_only
        enforce_singleton(resources, "tailscale.settings")
        service = TailscaleService.from_environment(env_name, provider_name, self.config_dir)
        live = service.extract_settings_fields(service.get_settings())
        desired = service.build_desired_settings_fields(resources[0])
        diff = diff_singleton(live, desired)
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
        """Apply the singleton diff: write tailscale settings if drifted.

        Uses :meth:`TailscaleService.apply_settings_patch` (read-modify-write)
        so the scalar settings payload does not clobber the embedded subnets.

        Does NOT call ``service.reconfigure()`` — the runner fires the
        ``tailscale_reconfigure`` finalization hook once after all three
        tailscale managers have applied.

        Args:
            env_name: Active environment name.
            resources: Should contain exactly one ``tailscale.settings``
                ``ResourceConfig``.
            auto_approve: No-op.
            add_only: No-op for singletons.
            provider_name: Provider identifier.

        Returns:
            Dict with ``resources_updated`` count and ``resource_outcomes``.
        """
        del auto_approve, add_only
        enforce_singleton(resources, "tailscale.settings")
        service = TailscaleService.from_environment(env_name, provider_name, self.config_dir)
        live = service.extract_settings_fields(service.get_settings())
        desired = service.build_desired_settings_fields(resources[0])
        diff = diff_singleton(live, desired)

        if diff is None:
            return {
                "success": True,
                "resources_created": 0,
                "resources_updated": 0,
                "resources_deleted": 0,
                "resource_outcomes": [],
            }

        wire = service.build_settings_wire_payload(diff)
        service.apply_settings_patch(wire)
        return {
            "success": True,
            "resources_created": 0,
            "resources_updated": 1,
            "resources_deleted": 0,
            "resource_outcomes": [
                ResourceOutcome(
                    address="opnsense_tailscale_settings.settings",
                    action="update",
                    resource_name="settings",
                )
            ],
        }

    def destroy(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        auto_approve: bool = True,
        provider_name: str = "opnsense",
    ) -> dict[str, Any]:
        """No-op: tailscale plugin settings are never auto-uninstalled."""
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
        """Return ``{"settings": "global"}`` for the singleton.

        Args:
            env_name: Active environment name (unused).
            resources: Singleton ``tailscale.settings`` resource list (unused).
            provider_name: Provider identifier (unused).

        Returns:
            Single-entry mapping with stable id ``"global"``.
        """
        del env_name, resources, provider_name
        return {"settings": "global"}

    def migrate(
        self,
        env_name: str,
        *,
        provider_name: str = "opnsense",
    ) -> str:
        """Export current tailscale settings to InfraFoundry YAML.

        Args:
            env_name: Active environment name.
            provider_name: Provider identifier.

        Returns:
            YAML string under the ``opnsense.tailscale.settings`` namespace.
        """
        service = TailscaleService.from_environment(env_name, provider_name, self.config_dir)
        return service.export_settings_to_yaml()
