"""VMID validation for Proxmox."""

from typing import TypedDict

from infrafoundry.core.validation import ValidationLevel, ValidationReport


class ClusterVM(TypedDict, total=False):
    """Typed representation of a VM entry in the Proxmox cluster listing."""

    vmid: int
    name: str
    template: int
    type: str


class VMIDValidator:
    """Validates Proxmox VMID availability and conflicts."""

    def __init__(self, report: ValidationReport) -> None:
        """Initialize VMID validator.

        Args:
            report: ValidationReport to add results to
        """
        self.report = report

    def validate(
        self,
        cluster_vms: list[ClusterVM] | None,
        vmids: dict[int, str],
    ) -> None:
        """Validate that VMIDs are available (not already in use).

        Args:
            cluster_vms: List of cluster VM data (None if fetch failed)
            vmids: Dict of {vmid: resource_name}
        """
        if not vmids:
            return

        if cluster_vms is None:
            return

        existing_vmids = {vm["vmid"]: vm.get("name", "N/A") for vm in cluster_vms}

        for vmid, resource_name in vmids.items():
            if vmid in existing_vmids:
                existing_name = existing_vmids[vmid]
                if existing_name == resource_name:
                    self.report.add_check(
                        check_name=f"proxmox_vmid_{vmid}_exists",
                        passed=True,
                        message=(
                            f"VMID {vmid} ({resource_name}) already exists (update/recreation)"
                        ),
                        level=ValidationLevel.INFO,
                    )
                else:
                    self.report.add_check(
                        check_name=f"proxmox_vmid_{vmid}_conflict",
                        passed=False,
                        message=(
                            f"VMID {vmid} already in use by '{existing_name}' "
                            f"(wanted by: {resource_name})"
                        ),
                        level=ValidationLevel.ERROR,
                    )
            else:
                self.report.add_check(
                    check_name=f"proxmox_vmid_{vmid}_available",
                    passed=True,
                    message=f"VMID {vmid} is available for {resource_name}",
                    level=ValidationLevel.INFO,
                )
