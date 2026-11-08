"""Template validation for Proxmox."""

from typing import override

from infrafoundry.core.protocols import SpecializedValidator
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.proxmox.validators.context import ProxmoxClusterContext


class TemplateValidator(SpecializedValidator[ProxmoxClusterContext]):
    """Validates Proxmox VM template availability."""

    def __init__(self, report: ValidationReport) -> None:
        """Initialize template validator.

        Args:
            report: ValidationReport to add results to
        """
        self.report = report

    @override
    def validate(self, context: ProxmoxClusterContext) -> None:
        """Validate that templates exist (by VMID or name).

        Args:
            context: Validation context carrying the inputs this validator checks.
        """
        cluster_vms = context.cluster_vms
        template_refs = context.template_refs
        if not template_refs:
            return

        if cluster_vms is None:
            return

        # ClusterVM keys are optional; an entry without the key cannot match it (#1121).
        templates = [vm for vm in cluster_vms if vm.get("template") == 1]
        templates_by_vmid = {vm["vmid"]: vm for vm in templates if "vmid" in vm}
        templates_by_name = {vm["name"]: vm for vm in templates if "name" in vm}

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
