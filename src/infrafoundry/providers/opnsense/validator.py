"""Validation logic for OPNsense provider.

This module contains all validation methods for checking OPNsense firewall
configurations against live API state before deployment.
"""

import logging
from typing import Any, TypedDict, cast

import urllib3

from infrafoundry.core.config.models import EnvironmentConfig
from infrafoundry.core.exceptions import ReferenceValidationError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.types import OPNsenseProviderSettings
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.core.validation_helpers import BaseAPIValidator
from infrafoundry.providers.opnsense.validators import (
    DHCPValidator,
    FirewallValidator,
    InterfaceAssignmentValidator,
    ResourceNameValidator,
    UnboundValidator,
    VLANValidator,
)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)


class AliasRow(TypedDict, total=False):
    """Partial representation of an alias row."""

    name: str


class InterfaceData(TypedDict, total=False):
    """Partial interface data exported by OPNsense."""

    if_type: str
    device: str


class OPNsenseValidator:
    """Validates OPNsense configurations against live API state.

    Performs comprehensive pre-flight validation including:
    - API connectivity and authentication
    - System status and version
    - Existing aliases, VLANs, and interfaces
    - Firewall rule references
    - DHCP configuration validity
    """

    def __init__(self, env_config: EnvironmentConfig, report: ValidationReport) -> None:
        """Initialize OPNsense validator.

        Args:
            env_config: Environment configuration including provider_settings
            report: ValidationReport to add results to
        """
        self.env_config = env_config
        self.report = report
        self.api_validator = BaseAPIValidator(
            "opnsense",
            env_config,
            report,
            env_prefix="OPNSENSE",
        )
        self.provider_settings = cast(
            OPNsenseProviderSettings, self.api_validator.provider_settings
        )

        # Initialize specialized validators
        self.firewall_validator = FirewallValidator(report)
        self.dhcp_validator = DHCPValidator(report)
        self.vlan_validator = VLANValidator(report)
        self.unbound_validator = UnboundValidator(report)
        self.resource_name_validator = ResourceNameValidator(report)
        self.interface_assignment_validator = InterfaceAssignmentValidator(report)

    def validate_connectivity(self) -> None:
        """Validate connectivity to OPNsense API.

        Checks:
        - API endpoint is reachable
        - Authentication credentials are valid
        - Can retrieve system status
        """
        env_map = {
            "api_url": "OPNSENSE_API_URL",
            "api_key": "OPNSENSE_API_KEY",
            "api_secret": "OPNSENSE_API_SECRET",  # nosec B105
        }
        credentials = self.api_validator.get_credentials(
            ["api_url", "api_key", "api_secret"],
            env_vars=env_map,
        )
        if not credentials:
            return

        api_url = credentials["api_url"]
        api_key = credentials["api_key"]
        api_secret = credentials["api_secret"]

        response = self.api_validator.api_request(
            url=f"{api_url}/api/core/system/status",
            auth=(api_key, api_secret),
            verify_ssl=False,
            timeout=10,
            check_name="opnsense_api_connection",
            expect_ok=False,
            error_message="Error connecting to OPNsense: {error}",
        )
        if not response:
            return

        if response.status_code == 200:
            data = response.json()
            self.api_validator.add_success(
                check_name="opnsense_api_connection",
                message=f"Successfully connected to OPNsense API at {api_url}",
            )

            if "product_version" in data:
                version = data.get("product_version", "unknown")
                self.api_validator.add_success(
                    check_name="opnsense_version",
                    message=f"OPNsense version: {version}",
                )
        elif response.status_code == 401:
            self.api_validator.add_error(
                check_name="opnsense_api_connection",
                message="OPNsense API credentials invalid (401 Unauthorized)",
            )
        else:
            self.api_validator.add_error(
                check_name="opnsense_api_connection",
                message=f"OPNsense API returned status {response.status_code}",
                level=ValidationLevel.WARNING,
            )

    def validate_references(self, resources: list[ResourceConfig]) -> None:
        """Validate that referenced OPNsense resources exist.

        Checks:
        - Aliases referenced in firewall rules exist
        - VLANs referenced in DHCP maps exist
        - Interfaces are valid
        - Unbound host override fields are valid
        - No duplicate resource names

        Args:
            resources: List of resources to validate
        """
        env_map = {
            "api_url": "OPNSENSE_API_URL",
            "api_key": "OPNSENSE_API_KEY",
            "api_secret": "OPNSENSE_API_SECRET",  # nosec B105
        }
        credentials = self.api_validator.get_credentials(
            ["api_url", "api_key", "api_secret"],
            env_vars=env_map,
        )
        if not credentials:
            return

        api_url = credentials["api_url"]
        api_key = credentials["api_key"]
        api_secret = credentials["api_secret"]

        # Collect resources by type
        resource_refs = self._collect_resource_references(resources)

        # Validate against live API
        try:
            # Get existing aliases from OPNsense
            existing_aliases = self._get_existing_aliases(api_url, api_key, api_secret)

            # Get existing interfaces/VLANs
            existing_interfaces = self._get_existing_interfaces(api_url, api_key, api_secret)

            # Validate using specialized validators
            self.firewall_validator.validate(
                resource_refs["firewall_rules"],
                resource_refs["alias_names"],
                existing_aliases,
            )
            self.dhcp_validator.validate(
                resource_refs["dhcp_maps"],
                resource_refs["vlan_names"],
                existing_interfaces,
            )
            self.vlan_validator.validate(
                resource_refs["vlans"],
                existing_interfaces,
            )
            self.interface_assignment_validator.validate(
                resource_refs["interface_assignments"],
                resource_refs["vlan_names"],
                existing_interfaces,
            )
            self.unbound_validator.validate(resource_refs["unbound_host_overrides"])
            self.resource_name_validator.validate(resources)

        except Exception as exc:
            check_name = "opnsense_validation"
            if isinstance(exc, ReferenceValidationError):
                check_name = "opnsense_reference_validation"
            self.api_validator.handle_validation_exception(
                check_name=check_name,
                error=exc,
                warning_level=ValidationLevel.ERROR,
            )

    def _collect_resource_references(self, resources: list[ResourceConfig]) -> dict[str, Any]:
        """Collect all resource references from configurations.

        Args:
            resources: List of resources to scan

        Returns:
            Dict with collected references organized by type
        """
        aliases = [r for r in resources if r.type == "aliases"]
        vlans = [r for r in resources if r.type == "vlans"]
        firewall_rules = [r for r in resources if r.type == "firewall_rules"]
        dhcp_maps = [r for r in resources if r.type == "dhcp_static_maps"]
        unbound_host_overrides = [r for r in resources if r.type == "unbound_host_override"]
        interface_assignments = [r for r in resources if r.type == "interface_assignments"]

        alias_names = {a.name for a in aliases}
        vlan_names = {v.name for v in vlans}
        interface_assignment_names = {a.name for a in interface_assignments}

        return {
            "aliases": aliases,
            "alias_names": alias_names,
            "vlans": vlans,
            "vlan_names": vlan_names,
            "firewall_rules": firewall_rules,
            "dhcp_maps": dhcp_maps,
            "unbound_host_overrides": unbound_host_overrides,
            "interface_assignments": interface_assignments,
            "interface_assignment_names": interface_assignment_names,
        }

    def _get_existing_aliases(
        self, api_url: str, api_key: str, api_secret: str
    ) -> dict[str, AliasRow]:
        """Get existing aliases from OPNsense API.

        Args:
            api_url: OPNsense API base URL
            api_key: API key
            api_secret: API secret

        Returns:
            Dict of existing alias names
        """
        data = self.api_validator.fetch_json(
            url=f"{api_url}/api/firewall/alias/searchItem",
            auth=(api_key, api_secret),
            verify_ssl=False,
            timeout=10,
            check_name="opnsense_get_aliases",
            error_message="Could not retrieve existing aliases (status {status})",
            error_level=ValidationLevel.WARNING,
        )
        if not data:
            return {}

        aliases: dict[str, AliasRow] = {}
        for row in data.get("rows", []):
            name = row.get("name")
            if name:
                aliases[name] = row
        return aliases

    def _normalize_interface_data(self, data: Any) -> list[dict[str, Any]]:
        """Normalize interface data to list format.

        The OPNsense API may return interface data in different formats:
        - As a dict keyed by interface name
        - As a list of interface dicts

        This method normalizes both formats to a consistent list format.

        Args:
            data: Raw interface data from API

        Returns:
            List of interface dicts
        """
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        elif isinstance(data, dict):
            return [
                {"name": name, **iface_data}
                for name, iface_data in data.items()
                if isinstance(iface_data, dict)
            ]
        return []

    def _extract_interface_name(self, iface_data: dict[str, Any]) -> str | None:
        """Extract interface name from various possible fields.

        Different interface types may store the name in different fields:
        - name: Standard field
        - device: Physical device name
        - if: Short form
        - interface: Full form

        Args:
            iface_data: Interface data dict

        Returns:
            Interface name if found, None otherwise
        """
        return (
            iface_data.get("name")
            or iface_data.get("device")
            or iface_data.get("if")
            or iface_data.get("interface")
        )

    def _get_existing_interfaces(
        self, api_url: str, api_key: str, api_secret: str
    ) -> dict[str, InterfaceData]:
        """Get existing interfaces and VLANs from OPNsense API.

        Args:
            api_url: OPNsense API base URL
            api_key: API key
            api_secret: API secret

        Returns:
            Dict of existing interface names
        """
        data = cast(
            Any,
            self.api_validator.fetch_json(
                url=f"{api_url}/api/interfaces/overview/export",
                auth=(api_key, api_secret),
                verify_ssl=False,
                timeout=10,
                check_name="opnsense_get_interfaces",
                error_message="Could not retrieve existing interfaces (status {status})",
                error_level=ValidationLevel.WARNING,
            ),
        )
        if not data:
            return {}

        # Normalize to list of interface dicts
        interface_list = self._normalize_interface_data(data)

        # Convert to dict keyed by name
        return {
            name: cast(InterfaceData, iface)
            for iface in interface_list
            if (name := self._extract_interface_name(iface))
        }
