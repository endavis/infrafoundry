"""Template configuration field-level validation for Proxmox.

Checks ``download_image.filename``, the ``import_id`` and the ``customize`` block of a template.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any, override

from infrafoundry.core.protocols import SpecializedValidator
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.proxmox.validators.context import ProxmoxConfigContext
from infrafoundry.providers.proxmox.validators.import_id import import_id_problems

# Extensions Proxmox VE accepts for ``import`` content (PVE::Storage ``$IMPORT_EXT_RE_1``),
# which is what ``download_image`` downloads into (#1188).
IMPORT_EXTENSIONS = (".ova", ".ovf", ".qcow2", ".raw", ".vmdk")

# Formats ``virt-customize`` can modify; ``.ova`` and ``.ovf`` are archives (#1622).
CUSTOMIZE_EXTENSIONS = (".qcow2", ".raw", ".vmdk")

# Package names allowed in ``customize.packages``: no shell or Terraform metacharacters (#1622).
PACKAGE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.+_:~-]*$")

_CUSTOMIZE_KEYS = ("packages",)


class TemplateConfigValidator(SpecializedValidator[ProxmoxConfigContext]):
    """Validates template configuration fields before Terraform generation.

    Performs field-level validation:
    - ERROR for ``download_image.filename`` values Proxmox rejects for import content
    - ERROR for an ``import_id`` that is not ``<node>/<vmid>`` or disagrees with ``vmid`` or
      ``target_node``
    - ERROR for a ``customize`` block without ``download_image``, with unsupported keys, a bad
      ``packages`` list, or a download file that is not a disk image
    """

    def __init__(self, report: ValidationReport) -> None:
        """Initialize template config validator.

        Args:
            report: ValidationReport to add results to.
        """
        self.report = report

    @override
    def validate(self, context: ProxmoxConfigContext) -> None:
        """Validate template-specific configuration fields.

        Args:
            context: Validation context carrying the inputs this validator checks.
        """
        templates = context.templates
        for resource in templates:
            if resource.type != "template":
                continue
            config = resource.config or {}
            self._validate_download_filename(resource.name, config)
            self._validate_import_id(resource.name, resource.import_id, config)
            self._validate_customize(resource.name, config)

    def _validate_import_id(self, name: str, import_id: str | None, config: dict[str, Any]) -> None:
        """Error if import_id is malformed or disagrees with vmid or target_node."""
        if import_id is None:
            return
        for problem in import_id_problems(import_id, config):
            self.report.add_check(
                check_name=f"proxmox_template_{name}_import_id",
                passed=False,
                message=f"Template '{name}': {problem}",
                level=ValidationLevel.ERROR,
            )

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

    def _validate_customize(self, name: str, config: dict[str, Any]) -> None:
        """Error if the ``customize`` block is malformed or cannot apply to the image."""
        if "customize" not in config:
            return
        for problem in self._customize_problems(config):
            self.report.add_check(
                check_name=f"proxmox_template_{name}_customize",
                passed=False,
                message=f"Template '{name}': {problem}",
                level=ValidationLevel.ERROR,
            )

    @staticmethod
    def _customize_problems(config: dict[str, Any]) -> list[str]:
        """Return the problems with a template's ``customize`` block."""
        download = config.get("download_image")
        if not isinstance(download, dict):
            return ["customize requires download_image."]
        customize = config["customize"]
        supported = ", ".join(_CUSTOMIZE_KEYS)
        if not isinstance(customize, dict):
            return [f"customize must be a mapping with the key(s): {supported}."]
        problems: list[str] = []
        extra = sorted(str(k) for k in customize if k not in _CUSTOMIZE_KEYS)
        if extra:
            problems.append(
                f"customize has unsupported key(s) {', '.join(extra)}; supported: {supported}."
            )
        packages = customize.get("packages")
        if not isinstance(packages, list) or not packages:
            problems.append("customize.packages must be a non-empty list of package names.")
        else:
            problems.extend(
                f"customize.packages item {pkg!r} is not a valid package name; it must match "
                f"{PACKAGE_NAME_RE.pattern}."
                for pkg in packages
                if not isinstance(pkg, str) or not PACKAGE_NAME_RE.fullmatch(pkg)
            )
        filename = download.get("filename")
        if (
            isinstance(filename, str)
            and PurePosixPath(filename).suffix.lower() not in CUSTOMIZE_EXTENSIONS
        ):
            problems.append(
                f"customize needs a disk image; download_image.filename '{filename}' must end "
                f"in one of {', '.join(CUSTOMIZE_EXTENSIONS)}."
            )
        return problems
