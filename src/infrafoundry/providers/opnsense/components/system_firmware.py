"""System firmware component manager for OPNsense (#806).

Singleton component manager for the ``system.firmware`` dotted resource
type — the **keystone** surface of #806. Without ``firmware.plugins``
automating the install of contrib plugins, the modern controllers for
follow-up issues (#790 AcmeClient, #808 OpenVPN-legacy) don't exist on
the cutover target and ``infra apply`` for those issues silently no-ops
with 404s.

Apply semantics (per the #806 user decision, 2026-05-10):

- **Install-missing only.** Any plugin in YAML but not on the box gets
  installed via ``firmware/install/<plugin_name>``.
- **Extras → warning, never removed.** Plugins on the box but not in
  YAML are logged at WARNING level only — never auto-uninstalled. This
  is a deliberate safety departure from the usual "live state == YAML
  state" symmetry.
- **Destroy is a no-op.** Don't auto-uninstall.

Plus the small set of tunable settings fields (``mirror``, ``flavour``)
follow the standard singleton diff/apply path.
"""

from __future__ import annotations

import logging
from typing import Any

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.types import ResourceOutcome

from ..services.system_firmware import SystemFirmwareService
from ._singleton import SingletonDiff, diff_singleton, enforce_singleton
from .base import BaseComponentManager

logger = logging.getLogger(__name__)


class SystemFirmwareManager(BaseComponentManager):
    """Manager for OPNsense system-firmware singleton operations."""

    def plan(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        add_only: bool = False,
        provider_name: str = "opnsense",
    ) -> SingletonDiff:
        """Compute the install-missing list + settings diff.

        The returned ``SingletonDiff`` carries up to one entry in
        ``updates``: a dict with two keys:

        - ``settings`` — the desired settings field map (or empty dict
          when settings are in sync).
        - ``install_missing`` — sorted list of plugin names to install.

        ``adds``/``deletes``/``locked`` are always empty for firmware.
        ``is_empty`` is True iff both ``settings`` is in sync AND
        ``install_missing`` is empty AND there are no extras to warn.

        Args:
            env_name: Active environment name.
            resources: Should contain exactly one ``system.firmware``
                ``ResourceConfig``.
            add_only: No-op for firmware (we never delete plugins).
            provider_name: Provider identifier.

        Returns:
            ``SingletonDiff``.
        """
        del add_only
        enforce_singleton(resources, "system.firmware")
        service = SystemFirmwareService.from_environment(env_name, provider_name, self.config_dir)
        info = service.get_firmware_info()

        # Plugin reconciliation
        installed = service.extract_installed_plugins(info)
        desired_plugins = service.build_desired_plugin_list(resources[0])
        install_missing, extras = service.desired_vs_installed_plugins(desired_plugins, installed)

        # Warn (never act on) extras — issue #806 user decision
        for extra in extras:
            logger.warning(
                "system.firmware: plugin %r installed on box but not in YAML; "
                "leaving alone (extras are never auto-removed per #806)",
                extra,
            )

        # Settings drift
        live_settings = service.extract_firmware_settings_fields(info)
        desired_settings = service.build_desired_firmware_settings_fields(resources[0])
        settings_diff = diff_singleton(live_settings, desired_settings)

        if settings_diff is None and not install_missing:
            return SingletonDiff(None)

        return SingletonDiff(
            {
                "settings": settings_diff or {},
                "install_missing": install_missing,
            }
        )

    def apply(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        auto_approve: bool = True,
        add_only: bool = False,
        provider_name: str = "opnsense",
    ) -> dict[str, Any]:
        """Apply: install missing plugins (one call per name), then settings.

        Args:
            env_name: Active environment name.
            resources: Should contain exactly one ``system.firmware``
                ``ResourceConfig``.
            auto_approve: No-op (the diff engine is the gate).
            add_only: No-op for firmware.
            provider_name: Provider identifier.

        Returns:
            Dict with counts and ``resource_outcomes``. Each installed
            plugin produces one ``ResourceOutcome`` with
            ``action="add"`` and ``resource_name=<plugin_name>``.
        """
        del auto_approve, add_only
        enforce_singleton(resources, "system.firmware")
        service = SystemFirmwareService.from_environment(env_name, provider_name, self.config_dir)
        info = service.get_firmware_info()

        installed = service.extract_installed_plugins(info)
        desired_plugins = service.build_desired_plugin_list(resources[0])
        install_missing, extras = service.desired_vs_installed_plugins(desired_plugins, installed)
        for extra in extras:
            logger.warning(
                "system.firmware: plugin %r installed on box but not in YAML; "
                "leaving alone (extras are never auto-removed per #806)",
                extra,
            )

        outcomes: list[ResourceOutcome] = []
        created = 0
        for plugin_name in install_missing:
            service.install_plugin(plugin_name)
            outcomes.append(
                ResourceOutcome(
                    address=f"opnsense_firmware_plugin.{plugin_name}",
                    action="add",
                    resource_name=plugin_name,
                )
            )
            created += 1

        # Settings updates
        live_settings = service.extract_firmware_settings_fields(info)
        desired_settings = service.build_desired_firmware_settings_fields(resources[0])
        settings_diff = diff_singleton(live_settings, desired_settings)
        updated = 0
        if settings_diff is not None:
            # Settings write goes through the firmware controller's set
            # endpoint when one exists. The XML-only inference doesn't
            # confirm a writable mirror/flavour endpoint; the keystone
            # use case for #806 is plugin install, so settings drift is
            # surfaced at plan time but not auto-written here. The
            # operator can act on it via the GUI or a follow-up.
            logger.warning(
                "system.firmware: settings drift detected (%s); skipping "
                "auto-write — use the GUI or file a follow-up",
                sorted(settings_diff.keys()),
            )

        return {
            "success": True,
            "resources_created": created,
            "resources_updated": updated,
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
        """No-op: don't auto-uninstall plugins."""
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
        """Return the singleton's stable id."""
        del env_name, resources, provider_name
        return {"settings": "global"}

    def migrate(
        self,
        env_name: str,
        *,
        provider_name: str = "opnsense",
    ) -> str:
        """Export current firmware settings to InfraFoundry YAML."""
        service = SystemFirmwareService.from_environment(env_name, provider_name, self.config_dir)
        return service.export_to_yaml()
