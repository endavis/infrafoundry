"""System remote-backup service for OPNsense direct-API operations (#806).

Manages the OPNsense ``<system><remotebackup>`` block (Google Drive) via
the ``gdrivebackup/settings/*`` controller. Identity is the singleton
``settings`` — there is exactly one remote-backup configuration per box.

Endpoint surface (XML-inferred per ``tmp/agents/claude/probe-806.md``;
operator should re-verify with a live probe after merge):

- ``GET gdrivebackup/settings/get`` — current GDrive settings.
- ``POST gdrivebackup/settings/set`` — write GDrive settings.

Field schema (XML-derived; YAML field names use snake_case conventions):

- ``gdrive_enabled`` — bool sentinel ("on" / "")
- ``gdrive_email`` — string (service account)
- ``gdrive_backup_count`` — int (retention count)
- ``gdrive_password`` — **secret-bearing** (must be ``secret://`` URI)
- ``gdrive_p12_key`` — **secret-bearing** (base64 PKCS12, must be
  ``secret://`` URI)
- ``gdrive_folder_id`` — string (Drive folder ID)
- ``gdrive_prefix_hostname`` — bool sentinel ("on" / "")

The two secret fields are the **second direct-API secret-bearing surface**
(after CARP password in ``virtual_ips`` from #723) and are the trigger
for the secret-required validator pattern in #806.

Secret resolution mirrors :class:`VirtualIPManager`'s flow: the operator
provides ``secret://env_secrets/<dotted/path>`` URIs in YAML, the
component manager resolves them at apply time via ``SecretResolver``
before calling :meth:`set_settings`, and the service is unaware of
secrets.

``export_to_yaml`` redacts both secret fields with placeholder
``secret://`` URIs so the migrated YAML is safe to commit.
"""

from __future__ import annotations

from typing import Any

from infrafoundry.core.provider import ResourceConfig

from ..api_client import OPNsenseClient, SystemClient
from ._nested_emit import emit_nested_singleton_yaml
from .base import BaseService

# Placeholder substituted into exported YAML for the two secret-bearing
# fields — OPNsense returns the live values on read but we never want
# to round-trip those into committed YAML.
_PASSWORD_REDACTED = "secret://env_secrets/opnsense/gdrive/password/REPLACE_ME"  # nosec B105
_P12KEY_REDACTED = "secret://env_secrets/opnsense/gdrive/p12_key/REPLACE_ME"  # nosec B105


class SystemRemoteBackupService(BaseService):
    """Service for OPNsense system-remotebackup operations via direct-API.

    Args:
        client: Configured ``OPNsenseClient`` instance.
    """

    def __init__(self, client: OPNsenseClient) -> None:
        """Initialize the remote-backup service with a SystemClient wrapper."""
        super().__init__(client)
        self.system_client = SystemClient(client)

    def get_settings(self) -> dict[str, Any]:
        """Fetch current remote-backup settings."""
        return self.system_client.get_remotebackup_settings()

    def set_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Push remote-backup settings updates to OPNsense.

        Args:
            payload: Settings payload (caller wraps in correct envelope).
                Secret fields must be plaintext at this point — the
                manager resolves ``secret://`` URIs before calling here.

        Returns:
            API response.
        """
        return self.system_client.set_remotebackup_settings(payload)

    def extract_remotebackup_fields(self, api_response: dict[str, Any]) -> dict[str, Any]:
        """Extract remote-backup fields from a gdrivebackup/settings/get response.

        Args:
            api_response: Raw response from :meth:`get_settings`.

        Returns:
            Flat ``{field: value}`` mapping.
        """
        body = _unwrap_remotebackup(api_response)
        return {
            "gdrive_enabled": _str(body.get("GDriveEnabled")),
            "gdrive_email": _str(body.get("GDriveEmail")),
            "gdrive_backup_count": _str(body.get("GDriveBackupCount")),
            "gdrive_password": _str(body.get("GDrivePassword")),
            "gdrive_p12_key": _str(body.get("GDriveP12key")),
            "gdrive_folder_id": _str(body.get("GDriveFolderID")),
            "gdrive_prefix_hostname": _str(body.get("GDrivePrefixHostname")),
        }

    def build_desired_remotebackup_fields(self, resource: ResourceConfig) -> dict[str, Any]:
        """Build the desired remote-backup field map from a YAML singleton.

        At this point any ``secret://`` URIs in the secret-bearing fields
        have already been resolved by the manager; the values land here
        as plaintext.

        Args:
            resource: ``system.remotebackup`` ``ResourceConfig``.

        Returns:
            Flat ``{field: value}`` mapping mirroring
            :meth:`extract_remotebackup_fields`.
        """
        config = resource.config
        return {
            "gdrive_enabled": _str(config.get("gdrive_enabled")),
            "gdrive_email": _str(config.get("gdrive_email")),
            "gdrive_backup_count": _str(config.get("gdrive_backup_count")),
            "gdrive_password": _str(config.get("gdrive_password")),
            "gdrive_p12_key": _str(config.get("gdrive_p12_key")),
            "gdrive_folder_id": _str(config.get("gdrive_folder_id")),
            "gdrive_prefix_hostname": _str(config.get("gdrive_prefix_hostname")),
        }

    def export_to_yaml(self) -> str:
        """Export current remote-backup settings as nested YAML.

        Secret-bearing fields are redacted with placeholder ``secret://``
        URIs so the migrated YAML is safe to commit; the operator
        re-supplies the secrets after migration.

        Returns:
            YAML string under the ``opnsense.system.remotebackup`` namespace.
        """
        live = self.extract_remotebackup_fields(self.get_settings())
        clean: dict[str, Any] = {}
        for key, value in live.items():
            if not value:
                continue
            if key == "gdrive_password":
                clean[key] = _PASSWORD_REDACTED
            elif key == "gdrive_p12_key":
                clean[key] = _P12KEY_REDACTED
            else:
                clean[key] = value
        return emit_nested_singleton_yaml("system.remotebackup", clean)


def _unwrap_remotebackup(api_response: dict[str, Any]) -> dict[str, Any]:
    """Return the inner backup-settings dict regardless of envelope.

    Tolerates ``{"gdrivebackup": {"general": {...}}}`` (modern MVC),
    ``{"general": {...}}``, and a flat layout where ``GDrive*`` fields
    sit at the top level.
    """
    gdrive = api_response.get("gdrivebackup")
    if isinstance(gdrive, dict):
        general = gdrive.get("general")
        if isinstance(general, dict):
            return general
        return gdrive
    if isinstance(api_response.get("general"), dict):
        return api_response["general"]  # type: ignore[no-any-return]
    return api_response


def _str(value: Any) -> str:
    """Return a stripped string for any scalar."""
    if value is None:
        return ""
    return str(value).strip()
