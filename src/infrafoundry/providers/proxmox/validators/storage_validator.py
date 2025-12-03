"""Storage validation for Proxmox."""

from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.core.validation_helpers import BaseAPIValidator


class StorageValidator:
    """Validates Proxmox storage pool availability and status."""

    def __init__(self, api_validator: BaseAPIValidator, report: ValidationReport) -> None:
        """Initialize storage validator.

        Args:
            api_validator: Shared API validator helper
            report: ValidationReport to add results to
        """
        self.api_validator = api_validator
        self.report = report

    def validate(
        self, api_url: str, headers: dict[str, str], storage_pools: set[tuple[str, str]]
    ) -> None:
        """Validate that storage pools exist and are active.

        Args:
            api_url: Proxmox API base URL
            headers: HTTP headers with authorization
            storage_pools: Set of (node, storage) tuples to validate
        """
        checked_storage = set()
        for node, storage in storage_pools:
            if (node, storage) in checked_storage:
                continue
            checked_storage.add((node, storage))

            storage_data = self.api_validator.fetch_json(
                url=f"{api_url}/nodes/{node}/storage",
                headers=headers,
                verify_ssl=False,
                timeout=10,
                check_name=f"proxmox_storage_{node}_{storage}",
                error_message=(
                    f"Storage '{storage}' on node '{node}' not accessible (status {{status}})"
                ),
                error_level=ValidationLevel.WARNING,
            )
            if not storage_data:
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
