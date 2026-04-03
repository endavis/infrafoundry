"""Validation logic for ESXi provider."""

from __future__ import annotations

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.types import EnvironmentData
from infrafoundry.core.validation import ValidationReport
from infrafoundry.core.validation_helpers import BaseAPIValidator

from .validators import (
    HostConnectivityValidator,
    OvfDeploymentValidator,
    PortgroupReferenceValidator,
    VswitchReferenceValidator,
)


class EsxiValidator:
    """Validates ESXi configurations.

    Performs pre-flight validation including:
    - SSH connectivity to ESXi hosts (port 22)
    - Vswitch reference validation (portgroups reference existing vswitches)
    - Portgroup reference validation (VMs reference existing portgroups)
    """

    def __init__(self, env_config: EnvironmentData, report: ValidationReport) -> None:
        """Initialize ESXi validator.

        Args:
            env_config: Environment configuration including provider_settings
            report: ValidationReport to add results to
        """
        self.env_config = env_config
        self.report = report
        self.api_validator = BaseAPIValidator("esxi", env_config, report)
        self.provider_settings = self.api_validator.provider_settings

        self.host_connectivity_validator = HostConnectivityValidator(report)
        self.vswitch_reference_validator = VswitchReferenceValidator(report)
        self.portgroup_reference_validator = PortgroupReferenceValidator(report)
        self.ovf_deployment_validator = OvfDeploymentValidator(report)

    def validate_connectivity(self) -> None:
        """Validate SSH connectivity to ESXi hosts.

        Checks that each configured ESXi host is reachable on port 22.
        """
        hosts_config = self.provider_settings.get("hosts", {})

        if not hosts_config:
            self.api_validator.add_error(
                check_name="esxi_hosts_configured",
                message="No ESXi hosts configured in provider_settings.esxi.hosts",
            )
            return

        for host_name, host_settings in hosts_config.items():
            hostname = host_settings.get("hostname", host_name)
            self.host_connectivity_validator.validate(hostname)

    def validate_references(self, resources: list[ResourceConfig]) -> None:
        """Validate cross-references between ESXi resources.

        Checks:
        - Portgroups reference vswitches that exist on the same host
        - VMs reference portgroups that exist on the same host

        Args:
            resources: List of resources to validate
        """
        self.vswitch_reference_validator.validate(resources)
        self.portgroup_reference_validator.validate(resources)
        self.ovf_deployment_validator.validate(resources)
