"""Compartment validation for OCI provider."""

from __future__ import annotations

from typing import Any

from infrafoundry.core.validation import ValidationLevel, ValidationReport


class CompartmentValidator:
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

    def validate(
        self,
        compartment_ocid: str,
        compartments: list[dict[str, Any]] | None,
    ) -> None:
        """Validate that compartment_ocid exists in the pre-fetched compartments list.

        Args:
            compartment_ocid: The compartment OCID from provider settings
            compartments: Pre-fetched list of compartment dicts from OCI API,
                or None if the API call failed
        """
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
