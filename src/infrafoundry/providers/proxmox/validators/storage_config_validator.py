"""Storage configuration field-level validation for Proxmox."""

from __future__ import annotations

from typing import Any

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport

# Valid storage backends
VALID_BACKENDS = frozenset({"nfs", "cifs", "dir"})

# Valid content types for Proxmox storage
VALID_CONTENT_TYPES = frozenset(
    {"images", "vztmpl", "rootdir", "iso", "backup", "snippets", "import"}
)

# Required fields per backend
BACKEND_REQUIRED_FIELDS: dict[str, list[str]] = {
    "nfs": ["server", "export"],
    "cifs": ["server", "share"],
    "dir": ["path"],
}


class StorageConfigValidator:
    """Validates storage configuration fields before Terraform generation.

    Performs field-level validation with appropriate severity levels:
    - ERROR for invalid values that would cause Terraform failures
    - WARNING for unusual but potentially valid values
    """

    def __init__(self, report: ValidationReport) -> None:
        """Initialize storage config validator.

        Args:
            report: ValidationReport to add results to.
        """
        self.report = report

    def validate(self, resources: list[ResourceConfig]) -> None:
        """Validate storage-specific configuration fields.

        Args:
            resources: List of resources to validate.
        """
        for resource in resources:
            if resource.type != "storage":
                continue
            config = resource.config or {}
            name = resource.name
            self._validate_backend(name, config)
            self._validate_backend_fields(name, config)
            self._validate_content_types(name, config)

    def _validate_backend(self, name: str, config: dict[str, Any]) -> None:
        """Error if backend is missing or not a valid value."""
        backend = config.get("backend")
        if backend is None:
            self.report.add_check(
                check_name=f"proxmox_storage_{name}_backend_missing",
                passed=False,
                message=(
                    f"Storage '{name}': 'backend' is required. "
                    f"Must be one of: {sorted(VALID_BACKENDS)}"
                ),
                level=ValidationLevel.ERROR,
            )
            return

        if backend not in VALID_BACKENDS:
            self.report.add_check(
                check_name=f"proxmox_storage_{name}_backend_invalid",
                passed=False,
                message=(
                    f"Storage '{name}': backend '{backend}' is not valid. "
                    f"Must be one of: {sorted(VALID_BACKENDS)}"
                ),
                level=ValidationLevel.ERROR,
            )

    def _validate_backend_fields(self, name: str, config: dict[str, Any]) -> None:
        """Error if required fields for the backend are missing."""
        backend = config.get("backend")
        if backend not in VALID_BACKENDS:
            return

        required_fields = BACKEND_REQUIRED_FIELDS[backend]
        for field in required_fields:
            if field not in config:
                self.report.add_check(
                    check_name=f"proxmox_storage_{name}_{field}_missing",
                    passed=False,
                    message=(f"Storage '{name}': '{field}' is required for '{backend}' backend."),
                    level=ValidationLevel.ERROR,
                )

        # CIFS without username warning
        if backend == "cifs" and "username" not in config:
            self.report.add_check(
                check_name=f"proxmox_storage_{name}_cifs_username",
                passed=True,
                message=(
                    f"Storage '{name}': CIFS storage without 'username' will use "
                    f"anonymous access. Set 'username' for authenticated shares."
                ),
                level=ValidationLevel.WARNING,
            )

    def _validate_content_types(self, name: str, config: dict[str, Any]) -> None:
        """Error if content_types contains invalid values."""
        content_types = config.get("content_types")
        if content_types is None:
            return

        if not isinstance(content_types, list):
            self.report.add_check(
                check_name=f"proxmox_storage_{name}_content_types_format",
                passed=False,
                message=(
                    f"Storage '{name}': 'content_types' must be a list. "
                    f"Valid values: {sorted(VALID_CONTENT_TYPES)}"
                ),
                level=ValidationLevel.ERROR,
            )
            return

        for ct in content_types:
            if ct not in VALID_CONTENT_TYPES:
                self.report.add_check(
                    check_name=f"proxmox_storage_{name}_content_type_{ct}",
                    passed=False,
                    message=(
                        f"Storage '{name}': content type '{ct}' is not valid. "
                        f"Valid values: {sorted(VALID_CONTENT_TYPES)}"
                    ),
                    level=ValidationLevel.ERROR,
                )
