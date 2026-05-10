"""System remote-backup component manager for OPNsense (#806).

Singleton component manager for the ``system.remotebackup`` dotted
resource type. Manages OPNsense's GDrive remote-backup settings — the
**second** direct-API surface (after ``virtual_ips`` from #723) to carry
secret-bearing fields. The two secrets are ``gdrive_password`` and
``gdrive_p12_key``; both must be ``secret://env_secrets/<path>`` URIs in
YAML and are resolved at apply time before the desired field map is
built.

Resolution flow (mirrors :class:`VirtualIPManager._resolve_and_parse`):

1. Manager loads ``EnvironmentConfig`` for the active env.
2. Instantiates a ``SecretResolver`` with the ``env_secrets`` backend.
3. Calls ``resolver.resolve_config(resource.config)`` on the singleton's
   config dict to expand the secret URIs to plaintext.
4. Hands the resolved dict to the service layer; the service is
   unaware of secrets.

The validator (separate file) rejects literal values in either secret
field at plan time so plaintext never reaches the resolver path.
"""

from __future__ import annotations

from typing import Any

from infrafoundry.core.config import ConfigManager
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.types import ResourceOutcome
from infrafoundry.secrets.resolver import SecretResolver

from ..services.system_remotebackup import SystemRemoteBackupService
from ._singleton import SingletonDiff, diff_singleton, enforce_singleton
from .base import BaseComponentManager


class SystemRemoteBackupManager(BaseComponentManager):
    """Manager for OPNsense system-remotebackup singleton operations."""

    def plan(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        add_only: bool = False,
        provider_name: str = "opnsense",
    ) -> SingletonDiff:
        """Compute the singleton diff for the GDrive backup block.

        Plan-time secret resolution runs before the diff so the desired
        field map carries plaintext (matching the live response shape).
        """
        del add_only
        enforce_singleton(resources, "system.remotebackup")
        service = SystemRemoteBackupService.from_environment(
            env_name, provider_name, self.config_dir
        )
        resolved = self._resolve_secrets(env_name, resources[0])
        live = service.extract_remotebackup_fields(service.get_settings())
        desired = service.build_desired_remotebackup_fields(resolved)
        return SingletonDiff(diff_singleton(live, desired))

    def apply(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        auto_approve: bool = True,
        add_only: bool = False,
        provider_name: str = "opnsense",
    ) -> dict[str, Any]:
        """Apply the singleton diff: write GDrive settings if drifted."""
        del auto_approve, add_only
        enforce_singleton(resources, "system.remotebackup")
        service = SystemRemoteBackupService.from_environment(
            env_name, provider_name, self.config_dir
        )
        resolved = self._resolve_secrets(env_name, resources[0])
        live = service.extract_remotebackup_fields(service.get_settings())
        desired = service.build_desired_remotebackup_fields(resolved)
        diff = diff_singleton(live, desired)

        if diff is None:
            return {
                "success": True,
                "resources_created": 0,
                "resources_updated": 0,
                "resources_deleted": 0,
                "resource_outcomes": [],
            }

        # Translate snake_case keys back to OPNsense's GDrive* wire keys.
        wire_payload = _build_wire_payload(diff)
        service.set_settings({"general": wire_payload})
        return {
            "success": True,
            "resources_created": 0,
            "resources_updated": 1,
            "resources_deleted": 0,
            "resource_outcomes": [
                ResourceOutcome(
                    address="opnsense_system_remotebackup.settings",
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
        """No-op: global system singletons are never auto-uninstalled."""
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
        """Export current GDrive backup settings to InfraFoundry YAML."""
        service = SystemRemoteBackupService.from_environment(
            env_name, provider_name, self.config_dir
        )
        return service.export_to_yaml()

    # ------------------------------------------------------------------
    # Secret resolution
    # ------------------------------------------------------------------

    def _resolve_secrets(
        self,
        env_name: str,
        resource: ResourceConfig,
    ) -> ResourceConfig:
        """Resolve ``secret://`` URIs in the singleton's config dict.

        Mirrors :meth:`VirtualIPManager._resolve_and_parse` for the
        singleton case — one resource, one resolver pass, plaintext
        ``ResourceConfig`` returned.

        Args:
            env_name: Active environment name.
            resource: The singleton ``system.remotebackup``
                ``ResourceConfig``.

        Returns:
            A new ``ResourceConfig`` with the secret URIs in
            ``gdrive_password`` and ``gdrive_p12_key`` expanded to
            plaintext.

        Raises:
            SecretResolutionError: If any ``secret://`` URI cannot be
                resolved.
        """
        config_manager = ConfigManager(self.config_dir)
        env_config = config_manager.load_environment(env_name)
        env_secrets = env_config.secrets if env_config.secrets is not None else {}

        resolver = SecretResolver()
        resolver.configure_backend("env_secrets", {"secrets": env_secrets})
        try:
            resolved_config = resolver.resolve_config(resource.config)
        finally:
            resolver.close()

        return ResourceConfig(
            name=resource.name,
            type=resource.type,
            provider=resource.provider,
            config=resolved_config,
        )


def _build_wire_payload(snake_payload: dict[str, Any]) -> dict[str, Any]:
    """Translate snake_case YAML field names back to OPNsense's wire form.

    The XML/wire shape uses ``GDriveEnabled`` / ``GDriveEmail`` /
    ``GDriveBackupCount`` / ``GDrivePassword`` / ``GDriveP12key`` /
    ``GDriveFolderID`` / ``GDrivePrefixHostname``. The diff engine
    operates on snake_case (matching YAML) so this translation lives at
    the apply boundary, leaving the diff side untouched.

    Args:
        snake_payload: Field map keyed by snake_case YAML names.

    Returns:
        Field map keyed by the OPNsense wire names.
    """
    mapping = {
        "gdrive_enabled": "GDriveEnabled",
        "gdrive_email": "GDriveEmail",
        "gdrive_backup_count": "GDriveBackupCount",
        "gdrive_password": "GDrivePassword",  # nosec B105 -- snake->Camel field-name map, not a password literal
        "gdrive_p12_key": "GDriveP12key",
        "gdrive_folder_id": "GDriveFolderID",
        "gdrive_prefix_hostname": "GDrivePrefixHostname",
    }
    return {mapping.get(k, k): v for k, v in snake_payload.items()}
