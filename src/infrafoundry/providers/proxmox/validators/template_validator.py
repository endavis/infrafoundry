"""Template validation for Proxmox."""

from typing import TypedDict

from infrafoundry.core.validation import ValidationLevel, ValidationReport


class ClusterVM(TypedDict, total=False):
    """Typed representation of a VM entry in the Proxmox cluster listing."""

    vmid: int
    name: str
    template: int
    type: str


class TemplateValidator:
    """Validates Proxmox VM template availability."""

    def __init__(self, report: ValidationReport) -> None:
        """Initialize template validator.

        Args:
            report: ValidationReport to add results to
        """
        self.report = report

    def validate(
        self,
        cluster_vms: list[ClusterVM] | None,
        template_refs: dict[str, list[str]],
    ) -> None:
        """Validate that templates exist (by VMID or name).

        Args:
            cluster_vms: List of cluster VM data (None if fetch failed)
            template_refs: Dict of {vmid_or_name: [resource_names]}
        """
        if not template_refs:
            return

        if cluster_vms is None:
            return

        templates_by_vmid = {vm["vmid"]: vm for vm in cluster_vms if vm.get("template") == 1}
        templates_by_name = {vm["name"]: vm for vm in cluster_vms if vm.get("template") == 1}

        for template_ref, resource_names in template_refs.items():
            # Check if it's a VMID (integer) or name (string)
            try:
                vmid = int(template_ref)
                if vmid in templates_by_vmid:
                    template = templates_by_vmid[vmid]
                    self.report.add_check(
                        check_name=f"proxmox_template_vmid_{vmid}",
                        passed=True,
                        message=f"Template VMID {vmid} exists: {template.get('name', 'N/A')}",
                        level=ValidationLevel.INFO,
                    )
                else:
                    self.report.add_check(
                        check_name=f"proxmox_template_vmid_{vmid}",
                        passed=False,
                        message=(
                            f"Template VMID {vmid} not found. Used by: {', '.join(resource_names)}"
                        ),
                        level=ValidationLevel.ERROR,
                    )
            except ValueError:
                # It's a name reference
                if template_ref in templates_by_name:
                    template = templates_by_name[template_ref]
                    self.report.add_check(
                        check_name=f"proxmox_template_{template_ref}",
                        passed=True,
                        message=(
                            f"Template '{template_ref}' exists (VMID: {template.get('vmid')})"
                        ),
                        level=ValidationLevel.INFO,
                    )
                else:
                    available_names = list(templates_by_name.keys())
                    self.report.add_check(
                        check_name=f"proxmox_template_{template_ref}",
                        passed=False,
                        message=(
                            f"Template '{template_ref}' not found. "
                            f"Used by: {', '.join(resource_names)}. "
                            f"Available: {available_names[:5]}"
                        ),
                        level=ValidationLevel.ERROR,
                    )
