"""System remote-backup validator for OPNsense (#806).

Pure-check, never-mutate validator for the ``system.remotebackup``
singleton resource type. The keystone behavior here is the
**secret-required** check: the two GDrive credentials
(``gdrive_password`` and ``gdrive_p12_key``) MUST be ``secret://`` URIs;
literal plaintext is rejected at plan time so credentials never reach
the resolver path as plain strings.

The validator does NOT mutate ``resource.config`` — strict invariant for
all OPNsense validators. Resolution of the ``secret://`` URI happens at
apply time inside :class:`SystemRemoteBackupManager`.
"""

from __future__ import annotations

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport

from ._secrets import is_secret_reference

# Fields that MUST be ``secret://`` URIs. Order matters only for stable
# iteration in the report output.
_SECRET_REQUIRED_FIELDS: tuple[str, ...] = ("gdrive_password", "gdrive_p12_key")


class SystemRemoteBackupValidator:
    """Validates ``system.remotebackup`` singleton resources."""

    def __init__(self, report: ValidationReport) -> None:
        """Initialize validator.

        Args:
            report: ValidationReport to add results to.
        """
        self.report = report

    def validate(self, resources: list[ResourceConfig]) -> None:
        """Validate ``system.remotebackup`` resources."""
        for resource in resources:
            self._validate_one(resource)

    def _validate_one(self, resource: ResourceConfig) -> None:
        check = f"system_remotebackup_{resource.name}"
        config = resource.config

        # Secret-required fields: must be a ``secret://`` URI when set.
        for field in _SECRET_REQUIRED_FIELDS:
            value = config.get(field)
            if value is None or value == "":
                # Empty / None is allowed — the operator may not have
                # configured GDrive backup yet. Apply-time logic decides
                # whether the missing value is a problem.
                continue
            if not is_secret_reference(value):
                self.report.add_check(
                    check_name=f"{check}_{field}",
                    passed=False,
                    message=(
                        f"system.remotebackup '{resource.name}' {field} must be a "
                        f"``secret://<backend>/<path>`` URI; literal plaintext is "
                        f"rejected to prevent credentials leaking into committed YAML"
                    ),
                    level=ValidationLevel.ERROR,
                )

        # Plain string fields.
        for field in (
            "gdrive_enabled",
            "gdrive_email",
            "gdrive_folder_id",
            "gdrive_prefix_hostname",
        ):
            value = config.get(field)
            if value is not None and not isinstance(value, str):
                self.report.add_check(
                    check_name=f"{check}_{field}",
                    passed=False,
                    message=(
                        f"system.remotebackup '{resource.name}' {field} must be a "
                        f"string, got {type(value).__name__}"
                    ),
                    level=ValidationLevel.ERROR,
                )

        # gdrive_backup_count — int or numeric string.
        backup_count = config.get("gdrive_backup_count")
        if backup_count is not None and not _is_int_like(backup_count):
            self.report.add_check(
                check_name=f"{check}_gdrive_backup_count",
                passed=False,
                message=(
                    f"system.remotebackup '{resource.name}' gdrive_backup_count must "
                    f"be an integer or numeric string, got {backup_count!r}"
                ),
                level=ValidationLevel.ERROR,
            )


def _is_int_like(value: object) -> bool:
    """Accept int OR numeric string."""
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    if isinstance(value, str):
        try:
            int(value)
        except ValueError:
            return False
        return True
    return False
