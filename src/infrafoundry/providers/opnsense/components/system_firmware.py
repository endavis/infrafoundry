"""System firmware component manager for OPNsense (#806).

Singleton component manager for the ``system.firmware`` dotted resource
type — the **keystone** surface of #806. Without ``firmware.plugins``
automating the install of contrib plugins, the modern controllers for
follow-up issues (#790 AcmeClient) don't exist on
the cutover target and ``infra apply`` for those issues silently no-ops
with 404s.

Apply semantics (per the #806 user decision, 2026-05-10):

- **Install-missing only.** Any plugin in YAML but not on the box gets
  installed via ``firmware/install/<plugin_name>``. The install is a
  background job, so apply waits on ``firmware/upgradestatus`` and fails
  unless the plugin is installed afterwards (#1238).
- **Extras → warning, never removed.** Plugins on the box but not in
  YAML are logged at WARNING level only — never auto-uninstalled. This
  is a deliberate safety departure from the usual "live state == YAML
  state" symmetry.
- **Destroy is a no-op.** Don't auto-uninstall.

With ``update: true`` the singleton also updates the firmware (#1452): plan
runs a firmware check and shows a pending minor update as a change; apply
starts the update, waits for the job and any reboot, and re-reads the version
before the plugin installs. Without ``update`` no firmware-update endpoint is
called. Settings written in the same run take effect from the next update.

Settings drift (only keys present in YAML: ``mirror``, ``flavour``, ...) is
written through ``core/firmware/set`` (#1149; verified live on 26.1.6_2).
Plugins are read from ``core/firmware/info`` and settings from
``core/firmware/get``.
"""

from __future__ import annotations

import logging
from typing import Any

from infrafoundry.core.exceptions import APIError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.types import ResourceOutcome

from ..services.system_firmware import PendingUpdate, SystemFirmwareService
from ._singleton import SingletonDiff, enforce_singleton
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

        The returned ``SingletonDiff`` counts the same changes ``apply``
        reports (#1238):

        - ``adds`` — one ``{"plugin": name}`` entry per missing plugin,
          sorted by name.
        - ``updates`` — ``{"settings": {...}}`` when settings drift and, with
          ``update: true`` and a pending minor update,
          ``{"firmware_update": {"from": ..., "to": ...}}`` (listed first;
          a reboot warning goes in ``warnings`` when OPNsense expects one).
          A failed check is a warning only.

        ``deletes``/``locked`` are always empty for firmware. ``is_empty``
        is True iff there is no missing plugin AND no settings drift
        (extras are only warned about).

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
        warnings: list[str] = []
        pending: PendingUpdate | None = None
        update_enabled, _ = service.desired_update(resources[0])
        if update_enabled:
            status = service.check_for_updates()
            problem = service.status_problem(status)
            if problem is not None:
                warnings.append(f"system.firmware: cannot plan a firmware update: {problem}")
            else:
                pending = service.pending_update(status)
            if pending is not None and pending.reboot:
                warnings.append(
                    "system.firmware: the firmware update will reboot the box "
                    f"({pending.from_version} -> {pending.to_version})"
                )
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
        live_settings = service.extract_firmware_settings_fields(service.get_firmware_settings())
        desired_settings = service.build_desired_firmware_settings_fields(resources[0])
        settings_diff = service.settings_drift(live_settings, desired_settings)

        diff = SingletonDiff(
            {"settings": settings_diff} if settings_diff is not None else None,
            adds=[{"plugin": name} for name in install_missing],
            warnings=warnings,
        )
        if pending is not None:
            diff.updates.insert(
                0,
                {"firmware_update": {"from": pending.from_version, "to": pending.to_version}},
            )
        return diff

    def apply(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        auto_approve: bool = True,
        add_only: bool = False,
        provider_name: str = "opnsense",
    ) -> dict[str, Any]:
        """Apply: update firmware (opt-in), install missing plugins, write settings drift.

        With ``update: true`` the run first checks for a pending minor update,
        starts it, waits for the job and any reboot, and re-reads the version.
        A check that reports an error raises. A box that is already current
        makes no update call.

        Each install is queued and then awaited; a plugin that is still not
        installed afterwards raises ``APIError`` (#1238), and neither the
        outcome nor the settings write follows it.

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

        Raises:
            APIError: If the firmware check reports an error, the update does
                not reach the expected version in ``update_timeout``, or an
                install is rejected, times out, or finishes without the
                plugin being installed.
        """
        del auto_approve, add_only
        enforce_singleton(resources, "system.firmware")
        service = SystemFirmwareService.from_environment(env_name, provider_name, self.config_dir)
        outcomes: list[ResourceOutcome] = []
        updated = 0
        update_enabled, update_timeout = service.desired_update(resources[0])
        if update_enabled:
            status = service.check_for_updates()
            problem = service.status_problem(status)
            if problem is not None:
                raise APIError(
                    f"system.firmware: cannot update the firmware: {problem}",
                    provider="opnsense",
                )
            pending = service.pending_update(status)
            if pending is not None:
                logger.info(
                    "system.firmware: updating firmware %s -> %s",
                    pending.from_version,
                    pending.to_version,
                )
                service.start_update()
                service.wait_for_update(pending.to_version, timeout=update_timeout)
                outcomes.append(
                    ResourceOutcome(
                        address="opnsense_system_firmware.update",
                        action="update",
                        resource_name=resources[0].name,
                    )
                )
                updated += 1
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

        # Settings updates (keys only in logs, never values)
        live_settings = service.extract_firmware_settings_fields(service.get_firmware_settings())
        desired_settings = service.build_desired_firmware_settings_fields(resources[0])
        settings_diff = service.settings_drift(live_settings, desired_settings)
        if settings_diff is not None:
            logger.info(
                "system.firmware: updating settings %s",
                sorted(settings_diff.keys()),
            )
            service.set_firmware_settings({"firmware": settings_diff})
            updated += 1
            outcomes.append(
                ResourceOutcome(
                    address="opnsense_system_firmware.settings",
                    action="update",
                    resource_name=resources[0].name,
                )
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
        del env_name, provider_name
        return {resource.name: "global" for resource in resources}

    def migrate(
        self,
        env_name: str,
        *,
        provider_name: str = "opnsense",
    ) -> str:
        """Export current firmware settings to InfraFoundry YAML."""
        service = SystemFirmwareService.from_environment(env_name, provider_name, self.config_dir)
        return service.export_to_yaml()
