"""HA sync settings component manager for OPNsense (#1389).

Manager for the ``hasync.settings`` singleton (System > High Availability > Settings).
``password`` is a ``secret://`` URI resolved through
:func:`~._secrets.resolve_resource_secrets`; it is never logged, put in an exception,
shown in a plan map or echoed back (see the service module for the write policy).
Destroy is a no-op. The ``hasync_reconfigure`` hook reloads the settings once per apply.
An unknown ``pfsync_interface`` or ``sync_items`` entry is a plan warning and fails the
apply before any write.
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from infrafoundry.core.exceptions import InvalidConfigurationError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.types import ResourceOutcome

from ..services.hasync_settings import (
    HasyncSettingsService,
    password_unreadable,
    redacted,
    wants_password_update,
)
from ._secrets import resolve_resource_secrets
from ._singleton import SingletonDiff, enforce_singleton
from .base import BaseComponentManager

logger = logging.getLogger(__name__)

_TYPE = "hasync.settings"

PASSWORD_WRITE_ONLY_WARNING = (  # nosec B105  # warning text, not a password
    "hasync.settings password is not readable from the box; set update_password: true to write it"
)


class HasyncSettingsManager(BaseComponentManager):
    """Manager for the HA sync settings singleton."""

    FINALIZATION_HOOK: ClassVar[str] = "hasync_reconfigure"

    #: Depends on ``interfaces.assignments``, so the runner deletes in its own phase
    #: (#1269). Destroy is a no-op here, so nothing is ever deleted.
    SPLIT_DELETE_PHASE: ClassVar[bool] = True

    def _prepare(
        self, env_name: str, resources: list[ResourceConfig], provider_name: str
    ) -> tuple[HasyncSettingsService, dict[str, str], bool]:
        enforce_singleton(resources, _TYPE)
        resolved = resolve_resource_secrets(self.config_dir, env_name, resources, _TYPE)
        service = HasyncSettingsService.from_environment(env_name, provider_name, self.config_dir)
        return service, service.build_desired(resolved[0]), wants_password_update(resolved[0])

    def plan(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        add_only: bool = False,
        provider_name: str = "opnsense",
    ) -> SingletonDiff:
        """Compute the singleton diff; the plan map never holds the password."""
        del add_only
        service, desired, update_password = self._prepare(env_name, resources, provider_name)
        live = service.live_hasync(service.get_settings())
        changed = service.changed_fields(live, desired, update_password)
        warnings = service.unknown_references(live, desired)
        if (
            "password" in desired
            and not update_password
            and not changed
            and password_unreadable(live)
        ):
            warnings.append(PASSWORD_WRITE_ONLY_WARNING)
        return SingletonDiff(redacted(desired) if changed else None, warnings=warnings or None)

    def apply(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        auto_approve: bool = True,
        add_only: bool = False,
        deletes_only: bool = False,
        provider_name: str = "opnsense",
    ) -> dict[str, Any]:
        """Write the HA sync settings when a declared field drifted.

        Reconfigure is not called here; the ``hasync_reconfigure`` hook fires.

        Args:
            env_name: Active environment name.
            resources: Should contain exactly one ``hasync.settings`` resource.
            auto_approve: No-op.
            add_only: No-op.
            deletes_only: If True, do nothing: the runner's delete phase. There is
                nothing to delete, so the box is neither read nor written.
            provider_name: Provider identifier (defaults to ``opnsense``).

        Raises:
            InvalidConfigurationError: If ``pfsync_interface`` or ``sync_items`` names
                something the box does not offer; raised before any write.
        """
        del auto_approve, add_only
        if deletes_only:
            return {
                "success": True,
                "resources_created": 0,
                "resources_updated": 0,
                "resources_deleted": 0,
                "resource_outcomes": [],
            }
        service, desired, update_password = self._prepare(env_name, resources, provider_name)
        live = service.live_hasync(service.get_settings())
        unknown = service.unknown_references(live, desired)
        if unknown:
            raise InvalidConfigurationError("; ".join(unknown))
        changed = service.changed_fields(live, desired, update_password)
        outcomes: list[ResourceOutcome] = []
        if changed:
            logger.info("hasync.settings: updating fields %s", sorted(changed))
            send = service.should_send_password(desired, changed, update_password)
            service.set_settings(service.build_set_payload(live, desired, send))
            outcomes.append(
                ResourceOutcome(
                    address="opnsense_hasync.settings",
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
        """No-op: HA sync is never switched off by a destroy."""
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
        """Export the live HA sync settings; the password is only a placeholder."""
        service = HasyncSettingsService.from_environment(env_name, provider_name, self.config_dir)
        return service.export_to_yaml()
