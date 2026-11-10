"""Tailscale authentication component manager for OPNsense (#787).

Manager for the ``tailscale.auth`` singleton. ``pre_auth_key`` is a ``secret://`` URI
resolved through :func:`~._secrets.resolve_resource_secrets`; the key is never logged,
put in an exception, shown in a plan map or echoed back (see the service module for the
write policy). Destroy is a no-op. The ``tailscale_reconfigure`` hook reconfigures once
per apply. A 404 at plan means the plugin is not installed yet.
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from infrafoundry.core.exceptions import APIError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.types import ResourceOutcome

from ..services.tailscale_auth import (
    TailscaleAuthService,
    key_unreadable,
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


class TailscaleAuthManager(BaseComponentManager):
    """Manager for the Tailscale authentication singleton."""

    FINALIZATION_HOOK: ClassVar[str] = "tailscale_reconfigure"

    def _prepare(
        self, env_name: str, resources: list[ResourceConfig], provider_name: str
    ) -> tuple[TailscaleAuthService, dict[str, str], bool]:
        enforce_singleton(resources, _TYPE)
        resolved = resolve_resource_secrets(self.config_dir, env_name, resources, _TYPE)
        service = TailscaleAuthService.from_environment(env_name, provider_name, self.config_dir)
        return service, service.build_desired(resolved[0]), wants_key_update(resolved[0])

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
        service, desired, update_key = self._prepare(env_name, resources, provider_name)
        try:
            live = service.live_auth(service.get_auth())
        except APIError as exc:
            if exc.status_code != 404:
                raise
            return SingletonDiff(redacted(desired) or None, warnings=[PLUGIN_MISSING_WARNING])
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
        service, desired, update_key = self._prepare(env_name, resources, provider_name)
        live = service.live_auth(service.get_auth())
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
