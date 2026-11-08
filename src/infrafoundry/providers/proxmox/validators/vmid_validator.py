"""VMID validation for Proxmox."""

from typing import override

from infrafoundry.core.protocols import SpecializedValidator
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.proxmox.validators.context import ProxmoxClusterContext


class VMIDValidator(SpecializedValidator[ProxmoxClusterContext]):
    """Validates Proxmox VMID availability and conflicts."""

    def __init__(self, report: ValidationReport) -> None:
        """Initialize VMID validator.

        Args:
            report: ValidationReport to add results to
        """
        self.report = report

    @override
    def validate(self, context: ProxmoxClusterContext) -> None:
        """Validate that VMIDs are available (not already in use).

        Args:
            context: Validation context carrying the inputs this validator checks.
        """
        cluster_vms = context.cluster_vms
        vmids = context.vmids
        if not vmids:
            return

        if cluster_vms is None:
            return

        # ClusterVM keys are optional; an entry without a vmid cannot conflict (#1121).
        existing_vmids = {vm["vmid"]: vm.get("name", "N/A") for vm in cluster_vms if "vmid" in vm}

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
