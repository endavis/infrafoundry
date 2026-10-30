"""Pin OPNsense literals that were restructured to drop bandit suppressions (#1209)."""

from infrafoundry.providers.opnsense import OPNsenseProvider
from infrafoundry.providers.opnsense.components.system_remotebackup import _build_wire_payload
from infrafoundry.providers.opnsense.validator import _API_SECRET_ENV


def test_tfvars_mapping_matches_the_original_literal() -> None:
    assert OPNsenseProvider._OPNSENSE_TFVARS_MAPPING == {
        "api_url": "opnsense_api_url",
        "api_key": "opnsense_api_key",
        "api_secret": "opnsense_api_secret",
    }


def test_api_secret_env_name_is_unchanged() -> None:
    assert _API_SECRET_ENV == "OPNSENSE_API_SECRET"


def test_remote_backup_wire_field_names_are_unchanged() -> None:
    snake = {
        "gdrive_enabled": 1,
        "gdrive_email": 2,
        "gdrive_backup_count": 3,
        "gdrive_password": 4,
        "gdrive_p12_key": 5,
        "gdrive_folder_id": 6,
        "gdrive_prefix_hostname": 7,
        "other": 8,
    }
    assert _build_wire_payload(snake) == {
        "GDriveEnabled": 1,
        "GDriveEmail": 2,
        "GDriveBackupCount": 3,
        "GDrivePassword": 4,
        "GDriveP12key": 5,
        "GDriveFolderID": 6,
        "GDrivePrefixHostname": 7,
        "other": 8,
    }
