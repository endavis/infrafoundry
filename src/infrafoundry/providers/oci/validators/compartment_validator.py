"""Compartment validation for OCI provider."""

from __future__ import annotations

from typing import override

from infrafoundry.core.protocols import SpecializedValidator
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.oci.validators.context import OCIApiContext


class CompartmentValidator(SpecializedValidator[OCIApiContext]):
    """Validates that the configured compartment OCID exists in OCI.

    This is a report-only validator that works with pre-fetched compartment
    data. The main OCI validator handles API authentication and data fetching.
    """

    def __init__(self, report: ValidationReport) -> None:
        """Initialize compartment validator.

        Args:
            report: ValidationReport to add results to
        """
        self.report = report

    @override
    def validate(self, context: OCIApiContext) -> None:
        """Validate that compartment_ocid exists in the pre-fetched compartments list.

        Args:
            context: The compartment OCID and the pre-fetched compartments
                (None if the API call failed).
        """
        compartment_ocid = context.compartment_ocid
        compartments = context.compartments
        if compartments is None:
            return

        compartment_map = {c.get("id", ""): c.get("name", "") for c in compartments}

        if compartment_ocid in compartment_map:
            name = compartment_map[compartment_ocid]
            self.report.add_check(
                check_name="oci_compartment_exists",
                passed=True,
                message=f"Compartment '{name}' ({compartment_ocid}) exists",
            )
        else:
            available = sorted(
                f"  {c.get('name', 'unnamed')} ({c.get('id', '')})" for c in compartments
            )
            available_str = "\n".join(available) if available else "  (none)"
            self.report.add_check(
                check_name="oci_compartment_exists",
                passed=False,
                message=(
                    f"Compartment '{compartment_ocid}' not found. "
                    f"Available compartments:\n{available_str}"
                ),
                level=ValidationLevel.ERROR,
            )
