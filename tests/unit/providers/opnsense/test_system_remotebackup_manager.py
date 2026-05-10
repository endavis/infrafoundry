"""Unit tests for ``SystemRemoteBackupManager`` (#806).

Coverage:
    - Standard 8-test singleton template adapted for the secret-required
      surface.
    - test_validator_secret_required: literal plaintext for ``gdrive_password``
      is rejected by the validator with a clear error message.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from infrafoundry.core.exceptions import InvalidConfigurationError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.opnsense.components.system_remotebackup import (
    SystemRemoteBackupManager,
)
from infrafoundry.providers.opnsense.validators.system_remotebackup_validator import (
    SystemRemoteBackupValidator,
)

SERVICE_PATH = (
    "infrafoundry.providers.opnsense.components.system_remotebackup.SystemRemoteBackupService"
)
RESOLVE_PATH = (
    "infrafoundry.providers.opnsense.components.system_remotebackup."
    "SystemRemoteBackupManager._resolve_secrets"
)


def _resource(
    *,
    gdrive_email: str = "svc@example.iam.gserviceaccount.com",
    gdrive_password: str = "secret://env_secrets/opnsense/gdrive/password",
    gdrive_p12_key: str = "secret://env_secrets/opnsense/gdrive/p12_key",
) -> ResourceConfig:
    return ResourceConfig(
        name="settings",
        type="system.remotebackup",
        provider="opnsense",
        config={
            "gdrive_enabled": "on",
            "gdrive_email": gdrive_email,
            "gdrive_backup_count": "60",
            "gdrive_password": gdrive_password,
            "gdrive_p12_key": gdrive_p12_key,
            "gdrive_folder_id": "FOLDER_ID",
            "gdrive_prefix_hostname": "on",
        },
    )


def _make_service_mock(*, live_fields: dict[str, Any] | None = None) -> MagicMock:
    live = live_fields or {}
    service = MagicMock()
    service.get_settings.return_value = {"general": live}
    service.extract_remotebackup_fields.side_effect = lambda response: {
        "gdrive_enabled": response.get("general", {}).get("gdrive_enabled", ""),
        "gdrive_email": response.get("general", {}).get("gdrive_email", ""),
        "gdrive_backup_count": response.get("general", {}).get("gdrive_backup_count", ""),
        "gdrive_password": response.get("general", {}).get("gdrive_password", ""),
        "gdrive_p12_key": response.get("general", {}).get("gdrive_p12_key", ""),
        "gdrive_folder_id": response.get("general", {}).get("gdrive_folder_id", ""),
        "gdrive_prefix_hostname": response.get("general", {}).get("gdrive_prefix_hostname", ""),
    }
    service.build_desired_remotebackup_fields.side_effect = lambda resource: {
        "gdrive_enabled": resource.config.get("gdrive_enabled", ""),
        "gdrive_email": resource.config.get("gdrive_email", ""),
        "gdrive_backup_count": resource.config.get("gdrive_backup_count", ""),
        "gdrive_password": resource.config.get("gdrive_password", ""),
        "gdrive_p12_key": resource.config.get("gdrive_p12_key", ""),
        "gdrive_folder_id": resource.config.get("gdrive_folder_id", ""),
        "gdrive_prefix_hostname": resource.config.get("gdrive_prefix_hostname", ""),
    }
    service.set_settings.return_value = {"result": "saved"}
    return service


def _live(*, password: str = "PLAIN_PW", p12_key: str = "PLAIN_P12") -> dict[str, Any]:
    """Default live state — password / p12 are *plaintext* on the wire."""
    return {
        "gdrive_enabled": "on",
        "gdrive_email": "svc@example.iam.gserviceaccount.com",
        "gdrive_backup_count": "60",
        "gdrive_password": password,
        "gdrive_p12_key": p12_key,
        "gdrive_folder_id": "FOLDER_ID",
        "gdrive_prefix_hostname": "on",
    }


def _resolved_resource() -> ResourceConfig:
    """A ResourceConfig with secrets pre-resolved (mimicking _resolve_secrets)."""
    return ResourceConfig(
        name="settings",
        type="system.remotebackup",
        provider="opnsense",
        config={
            "gdrive_enabled": "on",
            "gdrive_email": "svc@example.iam.gserviceaccount.com",
            "gdrive_backup_count": "60",
            "gdrive_password": "PLAIN_PW",
            "gdrive_p12_key": "PLAIN_P12",
            "gdrive_folder_id": "FOLDER_ID",
            "gdrive_prefix_hostname": "on",
        },
    )


class TestPlan:
    def test_plan_no_change(self, tmp_path: Path) -> None:
        manager = SystemRemoteBackupManager(tmp_path)
        service = _make_service_mock(live_fields=_live())
        with patch(SERVICE_PATH) as svc_cls, patch(RESOLVE_PATH) as resolve:
            svc_cls.from_environment.return_value = service
            resolve.return_value = _resolved_resource()
            diff = manager.plan("test-env", [_resource()])
        assert diff.is_empty

    def test_plan_update(self, tmp_path: Path) -> None:
        manager = SystemRemoteBackupManager(tmp_path)
        # Live has different folder_id; secrets resolve to plaintext that
        # equals what's on the wire.
        service = _make_service_mock(live_fields=_live() | {"gdrive_folder_id": "OLD"})
        with patch(SERVICE_PATH) as svc_cls, patch(RESOLVE_PATH) as resolve:
            svc_cls.from_environment.return_value = service
            resolve.return_value = _resolved_resource()
            diff = manager.plan("test-env", [_resource()])
        assert len(diff.updates) == 1
        assert diff.updates[0]["gdrive_folder_id"] == "FOLDER_ID"

    def test_plan_raises_on_multiple_resources(self, tmp_path: Path) -> None:
        manager = SystemRemoteBackupManager(tmp_path)
        with pytest.raises(InvalidConfigurationError):
            manager.plan("test-env", [_resource(), _resource()])


class TestApply:
    def test_apply_no_change(self, tmp_path: Path) -> None:
        manager = SystemRemoteBackupManager(tmp_path)
        service = _make_service_mock(live_fields=_live())
        with patch(SERVICE_PATH) as svc_cls, patch(RESOLVE_PATH) as resolve:
            svc_cls.from_environment.return_value = service
            resolve.return_value = _resolved_resource()
            result = manager.apply("test-env", [_resource()])
        service.set_settings.assert_not_called()
        assert result["resources_updated"] == 0

    def test_apply_update(self, tmp_path: Path) -> None:
        manager = SystemRemoteBackupManager(tmp_path)
        service = _make_service_mock(live_fields=_live() | {"gdrive_folder_id": "OLD"})
        with patch(SERVICE_PATH) as svc_cls, patch(RESOLVE_PATH) as resolve:
            svc_cls.from_environment.return_value = service
            resolve.return_value = _resolved_resource()
            result = manager.apply("test-env", [_resource()])
        service.set_settings.assert_called_once()
        # The wire payload must use OPNsense's GDrive* keys (translation).
        payload = service.set_settings.call_args.args[0]
        assert "general" in payload
        assert "GDriveFolderID" in payload["general"]
        assert payload["general"]["GDriveFolderID"] == "FOLDER_ID"
        assert result["resources_updated"] == 1


class TestDestroy:
    def test_destroy_noop(self, tmp_path: Path) -> None:
        manager = SystemRemoteBackupManager(tmp_path)
        result = manager.destroy("test-env", [_resource()])
        assert result["resources_destroyed"] == 0


class TestGetResourceIds:
    def test_get_resource_ids(self, tmp_path: Path) -> None:
        manager = SystemRemoteBackupManager(tmp_path)
        result = manager.get_resource_ids("test-env", [_resource()])
        assert result == {"settings": "global"}


# ---------------------------------------------------------------------------
# Secret-required validator
# ---------------------------------------------------------------------------


class TestValidatorSecretRequired:
    def test_literal_password_rejected(self) -> None:
        report = ValidationReport()
        validator = SystemRemoteBackupValidator(report)
        # gdrive_password is plaintext, NOT a secret:// URI.
        bad = _resource(gdrive_password="literal-plaintext-not-a-secret-uri")
        validator.validate([bad])
        # Should add at least one ERROR-level check for the secret field.
        errors = [c for c in report.results if c.level == ValidationLevel.ERROR and not c.passed]
        secret_errors = [c for c in errors if "gdrive_password" in c.message]
        assert len(secret_errors) >= 1
        assert "secret://" in secret_errors[0].message

    def test_literal_p12_key_rejected(self) -> None:
        report = ValidationReport()
        validator = SystemRemoteBackupValidator(report)
        bad = _resource(gdrive_p12_key="not-a-secret-uri")
        validator.validate([bad])
        errors = [c for c in report.results if c.level == ValidationLevel.ERROR and not c.passed]
        secret_errors = [c for c in errors if "gdrive_p12_key" in c.message]
        assert len(secret_errors) >= 1

    def test_secret_uri_passes(self) -> None:
        """Properly-formed secret:// URIs should NOT raise validator errors."""
        report = ValidationReport()
        validator = SystemRemoteBackupValidator(report)
        validator.validate([_resource()])
        errors = [c for c in report.results if c.level == ValidationLevel.ERROR and not c.passed]
        # No errors expected — both fields use secret:// URIs.
        assert errors == []
