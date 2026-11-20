"""Configuration backup download for OPNsense, read-only (#1497).

``GET core/backup/download/this`` returns the box's ``config.xml``. ``foundry config
migrate --include-legacy`` reads it to export the legacy ``<filter><rule>`` rules, which
the MVC filter API does not list, and (#1509) the legacy ``<nat><outbound><rule>`` rules
that the Source NAT API does not list.

The document holds secrets (API keys, password hashes, pre-shared keys, certificate
private keys). The text stays in memory: this service never logs it, never puts it in an
exception and never writes it to disk. The call needs the backup-download privilege on the
API key's user.
"""

from __future__ import annotations

from .. import endpoints
from .base import BaseService

#: The ``host`` path segment that selects this box's own configuration.
_THIS_HOST = "this"


class ConfigBackupService(BaseService):
    """Service for downloading the configuration backup."""

    def download_config(self) -> str:
        """Download the box's ``config.xml``.

        Returns:
            The raw XML text. It may contain secrets; treat it as sensitive.

        Raises:
            AuthenticationError: If the API key lacks the backup-download privilege.
            APIError: On any other failure, or when the box answers with JSON.
        """
        ep = endpoints.CORE_BACKUP_DOWNLOAD
        return self.client.get_text(ep.path(host=_THIS_HOST))
