"""Network validation for OCI provider."""

from __future__ import annotations

from typing import Any

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport


class NetworkValidator:
    """Validates OCI network resources against live API state.

    This is a report-only validator that works with pre-fetched VCN and
    subnet data. Checks for VCN name collisions with existing resources
    and validates subnet references.
    """

    def __init__(self, report: ValidationReport) -> None:
        """Initialize network validator.

        Args:
            report: ValidationReport to add results to
        """
        self.report = report

    def validate(
        self,
        resources: list[ResourceConfig],
        existing_vcns: list[dict[str, Any]] | None,
        existing_subnets: list[dict[str, Any]] | None,
    ) -> None:
        """Validate network resources against pre-fetched API data.

        Args:
            resources: List of resources from the configuration
            existing_vcns: Pre-fetched VCN list from OCI API, or None if unavailable
            existing_subnets: Pre-fetched subnet list from OCI API, or None if unavailable
        """
        config_vcns = [r for r in resources if r.type == "vcn"]
        config_subnets = [r for r in resources if r.type == "subnet"]

        if existing_vcns is not None:
            self._check_vcn_collisions(config_vcns, existing_vcns)

        if existing_subnets is not None:
            self._check_subnet_collisions(config_subnets, existing_subnets)

    def _check_vcn_collisions(
        self,
        config_vcns: list[ResourceConfig],
        existing_vcns: list[dict[str, Any]],
    ) -> None:
        """Check for VCN name collisions with existing API resources.

        Args:
            config_vcns: VCN resources from config
            existing_vcns: Existing VCNs from OCI API
        """
        existing_names = {v.get("displayName", "") for v in existing_vcns} - {""}

        for vcn in config_vcns:
            display_name = vcn.config.get("display_name", vcn.name)
            if display_name in existing_names:
                self.report.add_check(
                    check_name=f"oci_vcn_collision_{vcn.name}",
                    passed=True,
                    message=(
                        f"VCN '{display_name}' already exists in compartment. "
                        f"Terraform will manage the existing resource if imported."
                    ),
                    level=ValidationLevel.WARNING,
                )
            else:
                self.report.add_check(
                    check_name=f"oci_vcn_collision_{vcn.name}",
                    passed=True,
                    message=f"VCN '{display_name}' does not conflict with existing VCNs",
                )

    def _check_subnet_collisions(
        self,
        config_subnets: list[ResourceConfig],
        existing_subnets: list[dict[str, Any]],
    ) -> None:
        """Check for subnet name collisions with existing API resources.

        Args:
            config_subnets: Subnet resources from config
            existing_subnets: Existing subnets from OCI API
        """
        existing_names = {s.get("displayName", "") for s in existing_subnets} - {""}

        for subnet in config_subnets:
            display_name = subnet.config.get("display_name", subnet.name)
            if display_name in existing_names:
                self.report.add_check(
                    check_name=f"oci_subnet_collision_{subnet.name}",
                    passed=True,
                    message=(
                        f"Subnet '{display_name}' already exists in compartment. "
                        f"Terraform will manage the existing resource if imported."
                    ),
                    level=ValidationLevel.WARNING,
                )
            else:
                self.report.add_check(
                    check_name=f"oci_subnet_collision_{subnet.name}",
                    passed=True,
                    message=(f"Subnet '{display_name}' does not conflict with existing subnets"),
                )
