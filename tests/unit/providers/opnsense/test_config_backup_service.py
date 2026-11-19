"""Unit tests for ``ConfigBackupService`` (#1497)."""

from __future__ import annotations

from unittest.mock import MagicMock

from infrafoundry.providers.opnsense import endpoints
from infrafoundry.providers.opnsense.services.config_backup import ConfigBackupService


def test_download_config_reads_this_host_backup() -> None:
    client = MagicMock()
    client.get_text.return_value = "<opnsense/>"
    assert ConfigBackupService(client).download_config() == "<opnsense/>"
    client.get_text.assert_called_once_with("core/backup/download/this")
    client.request.assert_not_called()


def test_endpoint_is_a_registered_read_only_get_that_gates_no_type() -> None:
    ep = endpoints.CORE_BACKUP_DOWNLOAD
    assert ep.method == "GET"
    assert ep in endpoints.registered_endpoints()
    assert ep in endpoints.MIGRATE_ENDPOINTS
    for resource_type, eps in endpoints.RESOURCE_TYPE_ENDPOINTS.items():
        assert ep not in eps, resource_type
