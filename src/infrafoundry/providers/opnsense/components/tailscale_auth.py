"""Tailscale authentication component manager for OPNsense (#787).

Manager for the ``tailscale.auth`` singleton. ``pre_auth_key`` is a ``secret://`` URI
resolved through :func:`~._secrets.resolve_resource_secrets`; the key is never logged,
put in an exception, shown in a plan map or echoed back (see the service module for the
write policy). With a ``mint`` block (#1510) apply creates the key through the Tailscale
API when the node is not ``Running``, writes it, reconfigures and polls the status; the key,
the OAuth credentials and the token never reach a log, plan map, warning or exception.
Destroy is a no-op. The ``tailscale_reconfigure`` hook reconfigures once
per apply. A 404 at plan means the plugin is not installed yet.
"""

from __future__ import annotations

import logging
import time
from typing import Any, ClassVar

from infrafoundry.core.exceptions import APIError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.types import ResourceOutcome

from ..services.tailscale_auth import (
    MINT_PLACEHOLDER,
    MintSpec,
    TailscaleAuthService,
    key_unreadable,
    parse_mint,
    redacted,
    wants_key_update,
)
from ._secrets import resolve_resource_secrets
from ._singleton import SingletonDiff, enforce_singleton
from .base import BaseComponentManager
from .tailscale_settings import PLUGIN_MISSING_WARNING

logger = logging.getLogger(__name__)

_TYPE = "tailscale.auth"

KEY_WRITE_ONLY_WARNING = (
    "tailscale.auth pre_auth_key is not readable from the box; "
    "set update_pre_auth_key: true to write it"
)

#: How often and how long to poll ``BackendState`` after the key was written.
POLL_ATTEMPTS = 6
POLL_INTERVAL_SECONDS = 5.0

DISABLED_WARNING = (
    "tailscale.auth mint skipped: the Tailscale service is not enabled; "
    "enable it in tailscale.settings and apply again"
)
STILL_LOGGED_OUT_WARNING = (
    "tailscale.auth: the key was written but the node is not Running; see "
    "'Node stays logged out after the key is set' in docs/providers/tailscale.md "
    "(a stale profile needs SSH); the next apply mints a fresh key"
)

_sleep = time.sleep


class TailscaleAuthManager(BaseComponentManager):
    """Manager for the Tailscale authentication singleton."""

    FINALIZATION_HOOK: ClassVar[str] = "tailscale_reconfigure"

    def _prepare(
        self, env_name: str, resources: list[ResourceConfig], provider_name: str
    ) -> tuple[TailscaleAuthService, dict[str, str], bool, MintSpec | None]:
        enforce_singleton(resources, _TYPE)
        resolved = resolve_resource_secrets(self.config_dir, env_name, resources, _TYPE)
        service = TailscaleAuthService.from_environment(env_name, provider_name, self.config_dir)
        mint = parse_mint(resolved[0].config)
        return (
            service,
            service.build_desired(resolved[0]),
            wants_key_update(resolved[0]),
            mint,
        )

    @staticmethod
    def _poll_running(service: TailscaleAuthService) -> bool:
        """Poll the status until ``Running``; a failed read counts as not running."""
        for attempt in range(POLL_ATTEMPTS):
            try:
                if service.is_running():
                    return True
            except APIError:
                logger.warning("tailscale.auth: status read failed while polling")
            if attempt < POLL_ATTEMPTS - 1:
                _sleep(POLL_INTERVAL_SECONDS)
        return False

    def _recover(self, service: TailscaleAuthService) -> list[str]:
        """Reconfigure and poll; on failure reconfigure once more. Returns warnings."""
        service.reconfigure()
        if self._poll_running(service):
            return []
        service.reconfigure()
        if self._poll_running(service):
            return []
        return [STILL_LOGGED_OUT_WARNING]

    def plan(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        add_only: bool = False,
        provider_name: str = "opnsense",
    ) -> SingletonDiff:
        """Compute the singleton diff; the plan map never holds the key."""
        del add_only
        service, desired, update_key, mint = self._prepare(env_name, resources, provider_name)
        try:
            live = service.live_auth(service.get_auth())
            running = service.is_running() if mint else False
        except APIError as exc:
            if exc.status_code != 404:
                raise
            shown = redacted(desired)
            if mint:
                shown["pre_auth_key"] = MINT_PLACEHOLDER
            return SingletonDiff(shown or None, warnings=[PLUGIN_MISSING_WARNING])
        if mint:
            drift = service.changed_fields(live, desired, False)
            shown = redacted(desired) if drift else {}
            if not running:
                shown = {**redacted(desired), "pre_auth_key": MINT_PLACEHOLDER}
            return SingletonDiff(shown or None)
        warnings: list[str] = []
        if "pre_auth_key" in desired and not update_key and key_unreadable(live):
            warnings.append(KEY_WRITE_ONLY_WARNING)
        changed = service.changed_fields(live, desired, update_key)
        return SingletonDiff(redacted(desired) if changed else None, warnings=warnings or None)

    def apply(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        auto_approve: bool = True,
        add_only: bool = False,
        provider_name: str = "opnsense",
    ) -> dict[str, Any]:
        """Write the authentication settings when a declared field drifted."""
        del auto_approve, add_only
        service, desired, update_key, mint = self._prepare(env_name, resources, provider_name)
        live = service.live_auth(service.get_auth())
        if mint:
            return self._apply_mint(service, resources, desired, live, mint)
        changed = service.changed_fields(live, desired, update_key)
        outcomes: list[ResourceOutcome] = []
        if changed:
            logger.info("tailscale.auth: updating fields %s", changed)
            payload = service.build_set_payload(live, desired, "pre_auth_key" in changed)
            service.set_auth(payload)
            outcomes.append(
                ResourceOutcome(
                    address="opnsense_tailscale_auth.auth",
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

    def _apply_mint(
        self,
        service: TailscaleAuthService,
        resources: list[ResourceConfig],
        desired: dict[str, str],
        live: dict[str, Any],
        mint: MintSpec,
    ) -> dict[str, Any]:
        """Apply with a ``mint`` block: mint only when the node is not ``Running``."""
        warnings: list[str] = []
        running = service.is_running()
        send_key = False
        if not running and not service.service_enabled():
            warnings.append(DISABLED_WARNING)
        elif not running:
            # Never logged: the key lives only in these locals and the write body.
            desired = {**desired, "pre_auth_key": service.mint_key(mint)}
            send_key = True
        changed = service.changed_fields(live, desired, False)
        outcomes: list[ResourceOutcome] = []
        if send_key or changed:
            logger.info(
                "tailscale.auth: updating fields %s", ["pre_auth_key"] if send_key else changed
            )
            service.set_auth(service.build_set_payload(live, desired, send_key))
            outcomes.append(
                ResourceOutcome(
                    address="opnsense_tailscale_auth.auth",
                    action="update",
                    resource_name=resources[0].name,
                )
            )
        if send_key:
            warnings.extend(self._recover(service))
        result: dict[str, Any] = {
            "success": True,
            "resources_created": 0,
            "resources_updated": len(outcomes),
            "resources_deleted": 0,
            "resource_outcomes": outcomes,
        }
        if warnings:
            result["warnings"] = warnings
        return result

    def destroy(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        auto_approve: bool = True,
        provider_name: str = "opnsense",
    ) -> dict[str, Any]:
        """No-op: the stored key is never cleared."""
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
        """Export the live authentication settings; the key is only a placeholder."""
        service = TailscaleAuthService.from_environment(env_name, provider_name, self.config_dir)
        return service.export_to_yaml()
