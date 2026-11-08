"""Storage validation for Proxmox."""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from infrafoundry.core.exceptions import APIError
from infrafoundry.core.protocols import SpecializedValidator
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.proxmox.validators.context import ProxmoxLiveContext

if TYPE_CHECKING:
    pass


class StorageValidator(SpecializedValidator[ProxmoxLiveContext]):
    """Validates Proxmox storage pool availability and status."""

    def __init__(self, report: ValidationReport) -> None:
        """Initialize storage validator.

        Args:
            report: ValidationReport to add results to
        """
        self.report = report

    @override
    def validate(self, context: ProxmoxLiveContext) -> None:
        """Validate that storage pools exist and are active.

        Args:
            context: Validation context carrying the inputs this validator checks.
        """
        client = context.client
        storage_pools = context.storage_pools
        checked_storage: set[tuple[str, str]] = set()
        for node, storage in storage_pools:
            if (node, storage) in checked_storage:
                continue
            checked_storage.add((node, storage))

            try:
                storage_data = client.get_json(f"nodes/{node}/storage")
            except APIError:
                self.report.add_check(
                    check_name=f"proxmox_storage_{node}_{storage}",
                    passed=False,
                    message=(f"Storage '{storage}' on node '{node}' not accessible"),
                    level=ValidationLevel.WARNING,
                )
                continue

            storages = storage_data.get("data", [])
            storage_info = next((s for s in storages if s.get("storage") == storage), None)
            if storage_info:
                active = storage_info.get("active", 0)
                storage_type = storage_info.get("type", "unknown")
                if active:
                    self.report.add_check(
                        check_name=f"proxmox_storage_{node}_{storage}",
                        passed=True,
                        message=(
                            f"Storage '{storage}' on node '{node}' is active (type: {storage_type})"
                        ),
                        level=ValidationLevel.INFO,
                    )
                else:
                    self.report.add_check(
                        check_name=f"proxmox_storage_{node}_{storage}",
                        passed=False,
                        message=f"Storage '{storage}' on node '{node}' is inactive",
                        level=ValidationLevel.ERROR,
                    )
            else:
                available = [s.get("storage") for s in storages]
                self.report.add_check(
                    check_name=f"proxmox_storage_{node}_{storage}",
                    passed=False,
                    message=(
                        f"Storage '{storage}' not found on node '{node}'. Available: {available}"
                    ),
                    level=ValidationLevel.ERROR,
                )
