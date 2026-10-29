"""Template configuration field-level validation for Proxmox."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport

# Extensions Proxmox VE accepts for ``import`` content (PVE::Storage ``$IMPORT_EXT_RE_1``),
# which is what ``download_image`` downloads into (#1188).
IMPORT_EXTENSIONS = (".ova", ".ovf", ".qcow2", ".raw", ".vmdk")


class TemplateConfigValidator:
    """Validates template configuration fields before Terraform generation.

    Performs field-level validation:
    - ERROR for ``download_image.filename`` values Proxmox rejects for import content
    """

    def __init__(self, report: ValidationReport) -> None:
        """Initialize template config validator.

        Args:
            report: ValidationReport to add results to.
        """
        self.report = report

    def validate(self, templates: list[ResourceConfig]) -> None:
        """Validate template-specific configuration fields.

        Args:
            templates: List of template resources to validate.
        """
        for resource in templates:
            if resource.type != "template":
                continue
            config = resource.config or {}
            self._validate_download_filename(resource.name, config)

    def _validate_download_filename(self, name: str, config: dict[str, Any]) -> None:
        """Error if download_image.filename is missing or has an unaccepted extension."""
        download = config.get("download_image")
        if not isinstance(download, dict):
            return
        accepted = ", ".join(IMPORT_EXTENSIONS)
        filename = download.get("filename")
        if not isinstance(filename, str) or not filename.strip():
            self.report.add_check(
                check_name=f"proxmox_template_{name}_download_filename",
                passed=False,
                message=(
                    f"Template '{name}': download_image.filename is required; "
                    f"it must end in one of {accepted}."
                ),
                level=ValidationLevel.ERROR,
            )
            return
        suffix = PurePosixPath(filename).suffix.lower()
        if suffix in IMPORT_EXTENSIONS:
            return
        hint = ""
        if suffix == ".img":
            hint = f" Most cloud '.img' images are qcow2; try '{filename[: -len('.img')]}.qcow2'."
        self.report.add_check(
            check_name=f"proxmox_template_{name}_download_filename",
            passed=False,
            message=(
                f"Template '{name}': download_image.filename '{filename}' is not accepted "
                f"by Proxmox for import content; it must end in one of {accepted}.{hint}"
            ),
            level=ValidationLevel.ERROR,
        )
