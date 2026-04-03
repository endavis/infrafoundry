"""Storage validation for Proxmox."""

from __future__ import annotations

from typing import TYPE_CHECKING

from infrafoundry.core.exceptions import APIError
from infrafoundry.core.validation import ValidationLevel, ValidationReport

if TYPE_CHECKING:
    from infrafoundry.providers.proxmox.api_client import ProxmoxClient


class StorageValidator:
    """Validates Proxmox storage pool availability and status."""

    def __init__(self, report: ValidationReport) -> None:
        """Initialize storage validator.

        Args:
            report: ValidationReport to add results to
        """
        self.report = report

    def validate(self, client: ProxmoxClient, storage_pools: set[tuple[str, str]]) -> None:
        """Validate that storage pools exist and are active.

        Args:
            client: Proxmox API client
            storage_pools: Set of (node, storage) tuples to validate
        """
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
