"""Unit tests for Proxmox StorageConfigValidator."""

from unittest.mock import MagicMock

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.proxmox.validators.storage_config_validator import (
    StorageConfigValidator,
)


@pytest.fixture
def report():
    """Create a mock validation report."""
    return MagicMock(spec=ValidationReport)


@pytest.fixture
def validator(report):
    """Create a StorageConfigValidator instance."""
    return StorageConfigValidator(report)


def _storage(name: str = "test-storage", **config) -> ResourceConfig:
    """Helper to create a storage ResourceConfig."""
    return ResourceConfig(
        name=name,
        type="storage",
        provider="proxmox",
        config={"name": name, **config},
    )


class TestBackendValidation:
    """Tests for backend field validation."""

    def test_valid_nfs_backend(self, validator, report):
        """Valid NFS backend should not trigger an error."""
        validator.validate([_storage(backend="nfs", server="192.168.1.1", export="/export/data")])
        # Only the CIFS username warning should NOT be present; no errors
        error_calls = [c[1] for c in report.add_check.call_args_list if c[1].get("passed") is False]
        assert len(error_calls) == 0

    def test_valid_cifs_backend(self, validator, report):
        """Valid CIFS backend with username should not trigger errors."""
        validator.validate(
            [
                _storage(
                    backend="cifs",
                    server="192.168.1.1",
                    share="backups",
                    username="admin",
                )
            ]
        )
        error_calls = [c[1] for c in report.add_check.call_args_list if c[1].get("passed") is False]
        assert len(error_calls) == 0

    def test_valid_dir_backend(self, validator, report):
        """Valid dir backend should not trigger an error."""
        validator.validate([_storage(backend="dir", path="/mnt/data")])
        error_calls = [c[1] for c in report.add_check.call_args_list if c[1].get("passed") is False]
        assert len(error_calls) == 0

    def test_missing_backend(self, validator, report):
        """Missing backend should trigger an error."""
        validator.validate([_storage()])
        report.add_check.assert_called()
        call_args = report.add_check.call_args_list[0][1]
        assert call_args["passed"] is False
        assert call_args["level"] == ValidationLevel.ERROR
        assert "backend" in call_args["message"]

    def test_invalid_backend(self, validator, report):
        """Invalid backend value should trigger an error."""
        validator.validate([_storage(backend="iscsi")])
        calls = [c[1] for c in report.add_check.call_args_list if c[1].get("passed") is False]
        assert len(calls) == 1
        assert "iscsi" in calls[0]["message"]
        assert calls[0]["level"] == ValidationLevel.ERROR


class TestNFSValidation:
    """Tests for NFS backend field validation."""

    def test_missing_server(self, validator, report):
        """NFS without server should trigger an error."""
        validator.validate([_storage(backend="nfs", export="/export/data")])
        error_calls = [c[1] for c in report.add_check.call_args_list if c[1].get("passed") is False]
        assert any("server" in c["message"] for c in error_calls)

    def test_missing_export(self, validator, report):
        """NFS without export should trigger an error."""
        validator.validate([_storage(backend="nfs", server="192.168.1.1")])
        error_calls = [c[1] for c in report.add_check.call_args_list if c[1].get("passed") is False]
        assert any("export" in c["message"] for c in error_calls)

    def test_valid_nfs(self, validator, report):
        """Valid NFS config should not trigger errors."""
        validator.validate([_storage(backend="nfs", server="192.168.1.1", export="/export/data")])
        error_calls = [c[1] for c in report.add_check.call_args_list if c[1].get("passed") is False]
        assert len(error_calls) == 0


class TestCIFSValidation:
    """Tests for CIFS backend field validation."""

    def test_missing_server(self, validator, report):
        """CIFS without server should trigger an error."""
        validator.validate([_storage(backend="cifs", share="backups")])
        error_calls = [c[1] for c in report.add_check.call_args_list if c[1].get("passed") is False]
        assert any("server" in c["message"] for c in error_calls)

    def test_missing_share(self, validator, report):
        """CIFS without share should trigger an error."""
        validator.validate([_storage(backend="cifs", server="192.168.1.1")])
        error_calls = [c[1] for c in report.add_check.call_args_list if c[1].get("passed") is False]
        assert any("share" in c["message"] for c in error_calls)

    def test_cifs_without_username_warning(self, validator, report):
        """CIFS without username should trigger a warning."""
        validator.validate([_storage(backend="cifs", server="192.168.1.1", share="backups")])
        warning_calls = [
            c[1]
            for c in report.add_check.call_args_list
            if c[1].get("level") == ValidationLevel.WARNING
        ]
        assert len(warning_calls) == 1
        assert "username" in warning_calls[0]["message"]

    def test_cifs_with_username_no_warning(self, validator, report):
        """CIFS with username should not trigger the username warning."""
        validator.validate(
            [
                _storage(
                    backend="cifs",
                    server="192.168.1.1",
                    share="backups",
                    username="admin",
                )
            ]
        )
        warning_calls = [
            c[1]
            for c in report.add_check.call_args_list
            if c[1].get("level") == ValidationLevel.WARNING
        ]
        assert len(warning_calls) == 0

    def test_valid_cifs(self, validator, report):
        """Valid CIFS config should not trigger errors."""
        validator.validate(
            [
                _storage(
                    backend="cifs",
                    server="192.168.1.1",
                    share="backups",
                    username="admin",
                )
            ]
        )
        error_calls = [c[1] for c in report.add_check.call_args_list if c[1].get("passed") is False]
        assert len(error_calls) == 0


class TestDirValidation:
    """Tests for dir backend field validation."""

    def test_missing_path(self, validator, report):
        """Dir without path should trigger an error."""
        validator.validate([_storage(backend="dir")])
        error_calls = [c[1] for c in report.add_check.call_args_list if c[1].get("passed") is False]
        assert any("path" in c["message"] for c in error_calls)

    def test_valid_dir(self, validator, report):
        """Valid dir config should not trigger errors."""
        validator.validate([_storage(backend="dir", path="/mnt/data")])
        error_calls = [c[1] for c in report.add_check.call_args_list if c[1].get("passed") is False]
        assert len(error_calls) == 0


class TestContentTypesValidation:
    """Tests for content_types validation."""

    def test_valid_content_types(self, validator, report):
        """Valid content types should not trigger errors."""
        validator.validate(
            [
                _storage(
                    backend="dir",
                    path="/mnt/data",
                    content_types=["snippets", "iso", "vztmpl"],
                )
            ]
        )
        error_calls = [c[1] for c in report.add_check.call_args_list if c[1].get("passed") is False]
        assert len(error_calls) == 0

    def test_invalid_content_type(self, validator, report):
        """Invalid content type should trigger an error."""
        validator.validate(
            [_storage(backend="dir", path="/mnt/data", content_types=["invalid_type"])]
        )
        error_calls = [c[1] for c in report.add_check.call_args_list if c[1].get("passed") is False]
        assert any("invalid_type" in c["message"] for c in error_calls)

    def test_content_types_not_list(self, validator, report):
        """Non-list content_types should trigger an error."""
        validator.validate([_storage(backend="dir", path="/mnt/data", content_types="snippets")])
        error_calls = [c[1] for c in report.add_check.call_args_list if c[1].get("passed") is False]
        assert len(error_calls) == 1
        assert "list" in error_calls[0]["message"]

    def test_no_content_types(self, validator, report):
        """Missing content_types should not trigger an error."""
        validator.validate([_storage(backend="dir", path="/mnt/data")])
        error_calls = [c[1] for c in report.add_check.call_args_list if c[1].get("passed") is False]
        assert len(error_calls) == 0


class TestNonStorageResources:
    """Tests that non-storage resources are skipped."""

    def test_skips_non_storage_resources(self, validator, report):
        """Non-storage resources should be skipped entirely."""
        resource = ResourceConfig(
            name="test-vm",
            type="vm",
            provider="proxmox",
            config={"name": "test-vm"},
        )
        validator.validate([resource])
        report.add_check.assert_not_called()
