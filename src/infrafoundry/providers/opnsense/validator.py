"""Validation logic for OPNsense provider.

This module contains all validation methods for checking OPNsense firewall
configurations against live API state before deployment.
"""

import os
from typing import Any

import requests
import urllib3

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class OPNsenseValidator:
    """Validates OPNsense configurations against live API state.

    Performs comprehensive pre-flight validation including:
    - API connectivity and authentication
    - System status and version
    - Existing aliases, VLANs, and interfaces
    - Firewall rule references
    - DHCP configuration validity
    """

    def __init__(self, env_config: dict[str, Any], report: ValidationReport):
        """Initialize OPNsense validator.

        Args:
            env_config: Environment configuration including provider_settings
            report: ValidationReport to add results to
        """
        self.env_config = env_config
        self.report = report
        self.provider_settings = env_config.get("provider_settings", {}).get("opnsense", {})

    def validate_connectivity(self) -> None:
        """Validate connectivity to OPNsense API.

        Checks:
        - API endpoint is reachable
        - Authentication credentials are valid
        - Can retrieve system status
        """
        api_url = self.provider_settings.get("api_url") or os.getenv("OPNSENSE_API_URL")
        api_key = self.provider_settings.get("api_key") or os.getenv("OPNSENSE_API_KEY")
        api_secret = self.provider_settings.get("api_secret") or os.getenv("OPNSENSE_API_SECRET")

        # Check if credentials are configured
        if not all([api_url, api_key, api_secret]):
            self.report.add_check(
                check_name="opnsense_credentials",
                passed=False,
                message=(
                    "OPNsense credentials not configured. Required: api_url, api_key, api_secret"
                ),
                level=ValidationLevel.ERROR,
            )
            return

        # Test API connectivity
        try:
            response = requests.get(
                f"{api_url}/api/core/system/status",
                auth=(api_key, api_secret),
                verify=False,  # OPNsense often uses self-signed certs
                timeout=10,
            )

            if response.status_code == 200:
                data = response.json()
                self.report.add_check(
                    check_name="opnsense_api_connection",
                    passed=True,
                    message=f"Successfully connected to OPNsense API at {api_url}",
                    level=ValidationLevel.INFO,
                )

                # Get system info if available
                if "product_version" in data:
                    version = data.get("product_version", "unknown")
                    self.report.add_check(
                        check_name="opnsense_version",
                        passed=True,
                        message=f"OPNsense version: {version}",
                        level=ValidationLevel.INFO,
                    )

            elif response.status_code == 401:
                self.report.add_check(
                    check_name="opnsense_api_connection",
                    passed=False,
                    message="OPNsense API credentials invalid (401 Unauthorized)",
                    level=ValidationLevel.ERROR,
                )
            else:
                self.report.add_check(
                    check_name="opnsense_api_connection",
                    passed=False,
                    message=f"OPNsense API returned status {response.status_code}",
                    level=ValidationLevel.WARNING,
                )

        except requests.exceptions.ConnectionError:
            self.report.add_check(
                check_name="opnsense_api_connection",
                passed=False,
                message=f"Cannot connect to OPNsense at {api_url} (connection refused)",
                level=ValidationLevel.ERROR,
            )
        except requests.exceptions.Timeout:
            self.report.add_check(
                check_name="opnsense_api_connection",
                passed=False,
                message=f"Connection to OPNsense at {api_url} timed out",
                level=ValidationLevel.ERROR,
            )
        except Exception as e:
            self.report.add_check(
                check_name="opnsense_api_connection",
                passed=False,
                message=f"Error connecting to OPNsense: {e}",
                level=ValidationLevel.ERROR,
            )

    def validate_references(self, resources: list[ResourceConfig]) -> None:
        """Validate that referenced OPNsense resources exist.

        Checks:
        - Aliases referenced in firewall rules exist
        - VLANs referenced in DHCP maps exist
        - Interfaces are valid
        - No duplicate resource names

        Args:
            resources: List of resources to validate
        """
        api_url = self.provider_settings.get("api_url") or os.getenv("OPNSENSE_API_URL")
        api_key = self.provider_settings.get("api_key") or os.getenv("OPNSENSE_API_KEY")
        api_secret = self.provider_settings.get("api_secret") or os.getenv("OPNSENSE_API_SECRET")

        if not all([api_url, api_key, api_secret]):
            return  # Already reported in validate_connectivity

        # Collect resources by type
        resource_refs = self._collect_resource_references(resources)

        # Validate against live API
        try:
            # Get existing aliases from OPNsense
            existing_aliases = self._get_existing_aliases(api_url, api_key, api_secret)

            # Get existing interfaces/VLANs
            existing_interfaces = self._get_existing_interfaces(api_url, api_key, api_secret)

            # Validate firewall rule references
            self._validate_firewall_rules(resource_refs, existing_aliases)

            # Validate DHCP static map references
            self._validate_dhcp_maps(resource_refs, existing_interfaces)

            # Validate VLANs
            self._validate_vlans(resource_refs, existing_interfaces)

            # Check for duplicate names
            self._validate_unique_names(resources)

        except Exception as e:
            self.report.add_check(
                check_name="opnsense_validation",
                passed=False,
                message=f"Error during validation: {e}",
                level=ValidationLevel.WARNING,
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

        alias_names = {a.name for a in aliases}
        vlan_names = {v.name for v in vlans}

        return {
            "aliases": aliases,
            "alias_names": alias_names,
            "vlans": vlans,
            "vlan_names": vlan_names,
            "firewall_rules": firewall_rules,
            "dhcp_maps": dhcp_maps,
        }

    def _get_existing_aliases(self, api_url: str, api_key: str, api_secret: str) -> dict[str, Any]:
        """Get existing aliases from OPNsense API.

        Args:
            api_url: OPNsense API base URL
            api_key: API key
            api_secret: API secret

        Returns:
            Dict of existing alias names
        """
        try:
            response = requests.get(
                f"{api_url}/api/firewall/alias/searchItem",
                auth=(api_key, api_secret),
                verify=False,
                timeout=10,
            )

            if response.status_code == 200:
                data = response.json()
                # Extract alias names from response
                aliases = {}
                if "rows" in data:
                    for row in data["rows"]:
                        name = row.get("name", "")
                        if name:
                            aliases[name] = row
                return aliases

        except Exception as e:
            self.report.add_check(
                check_name="opnsense_get_aliases",
                passed=False,
                message=f"Could not retrieve existing aliases: {e}",
                level=ValidationLevel.WARNING,
            )

        return {}

    def _get_existing_interfaces(
        self, api_url: str, api_key: str, api_secret: str
    ) -> dict[str, Any]:
        """Get existing interfaces and VLANs from OPNsense API.

        Args:
            api_url: OPNsense API base URL
            api_key: API key
            api_secret: API secret

        Returns:
            Dict of existing interface names
        """
        try:
            response = requests.get(
                f"{api_url}/api/interfaces/overview/export",
                auth=(api_key, api_secret),
                verify=False,
                timeout=10,
            )

            if response.status_code == 200:
                data = response.json()
                interfaces = {}
                # Parse interface data
                for iface_name, iface_data in data.items():
                    if isinstance(iface_data, dict):
                        interfaces[iface_name] = iface_data
                return interfaces

        except Exception as e:
            self.report.add_check(
                check_name="opnsense_get_interfaces",
                passed=False,
                message=f"Could not retrieve existing interfaces: {e}",
                level=ValidationLevel.WARNING,
            )

        return {}

    def _validate_firewall_rules(
        self, resource_refs: dict[str, Any], existing_aliases: dict[str, Any]
    ) -> None:
        """Validate firewall rules reference valid aliases.

        Args:
            resource_refs: Collected resource references
            existing_aliases: Existing aliases from API
        """
        firewall_rules = resource_refs["firewall_rules"]
        alias_names = resource_refs["alias_names"]

        for rule in firewall_rules:
            rule_config = rule.config or {}
            source_alias = rule_config.get("source", {}).get("alias")
            dest_alias = rule_config.get("destination", {}).get("alias")

            # Check source alias
            if source_alias:
                # Check if it's in our config or exists in OPNsense
                if source_alias not in alias_names and source_alias not in existing_aliases:
                    self.report.add_check(
                        check_name=f"firewall_rule_{rule.name}_source_alias",
                        passed=False,
                        message=(
                            f"Firewall rule '{rule.name}' references "
                            f"undefined source alias '{source_alias}'"
                        ),
                        level=ValidationLevel.ERROR,
                    )
                else:
                    self.report.add_check(
                        check_name=f"firewall_rule_{rule.name}_source_alias",
                        passed=True,
                        message=f"Source alias '{source_alias}' found for rule '{rule.name}'",
                        level=ValidationLevel.INFO,
                    )

            # Check destination alias
            if dest_alias:
                if dest_alias not in alias_names and dest_alias not in existing_aliases:
                    self.report.add_check(
                        check_name=f"firewall_rule_{rule.name}_dest_alias",
                        passed=False,
                        message=(
                            f"Firewall rule '{rule.name}' references "
                            f"undefined destination alias '{dest_alias}'"
                        ),
                        level=ValidationLevel.ERROR,
                    )
                else:
                    self.report.add_check(
                        check_name=f"firewall_rule_{rule.name}_dest_alias",
                        passed=True,
                        message=f"Destination alias '{dest_alias}' found for rule '{rule.name}'",
                        level=ValidationLevel.INFO,
                    )

    def _validate_dhcp_maps(
        self, resource_refs: dict[str, Any], existing_interfaces: dict[str, Any]
    ) -> None:
        """Validate DHCP static maps reference valid interfaces.

        Args:
            resource_refs: Collected resource references
            existing_interfaces: Existing interfaces from API
        """
        dhcp_maps = resource_refs["dhcp_maps"]
        vlan_names = resource_refs["vlan_names"]

        for dhcp_map in dhcp_maps:
            interface = dhcp_map.config.get("interface")
            if interface:
                # Check if it's in our VLAN config or exists in OPNsense
                if interface not in vlan_names and interface not in existing_interfaces:
                    self.report.add_check(
                        check_name=f"dhcp_static_map_{dhcp_map.name}_interface",
                        passed=False,
                        message=(
                            f"DHCP static map '{dhcp_map.name}' references "
                            f"undefined interface '{interface}'"
                        ),
                        level=ValidationLevel.WARNING,
                    )
                else:
                    self.report.add_check(
                        check_name=f"dhcp_static_map_{dhcp_map.name}_interface",
                        passed=True,
                        message=f"Interface '{interface}' found for DHCP map '{dhcp_map.name}'",
                        level=ValidationLevel.INFO,
                    )

    def _validate_vlans(
        self, resource_refs: dict[str, Any], existing_interfaces: dict[str, Any]
    ) -> None:
        """Validate VLANs configuration.

        Args:
            resource_refs: Collected resource references
            existing_interfaces: Existing interfaces from API
        """
        vlans = resource_refs["vlans"]

        for vlan in vlans:
            parent_if = vlan.config.get("parent")

            # Check if parent interface exists
            if parent_if and parent_if not in existing_interfaces:
                self.report.add_check(
                    check_name=f"vlan_{vlan.name}_parent",
                    passed=False,
                    message=(
                        f"VLAN '{vlan.name}' references undefined parent interface '{parent_if}'"
                    ),
                    level=ValidationLevel.ERROR,
                )
            elif parent_if:
                self.report.add_check(
                    check_name=f"vlan_{vlan.name}_parent",
                    passed=True,
                    message=f"Parent interface '{parent_if}' found for VLAN '{vlan.name}'",
                    level=ValidationLevel.INFO,
                )

    def _validate_unique_names(self, resources: list[ResourceConfig]) -> None:
        """Check for duplicate resource names within each type.

        Args:
            resources: List of resources to check
        """
        # Group by type
        by_type: dict[str, list[str]] = {}
        for resource in resources:
            if resource.type not in by_type:
                by_type[resource.type] = []
            by_type[resource.type].append(resource.name)

        # Check for duplicates
        for resource_type, names in by_type.items():
            seen = set()
            for name in names:
                if name in seen:
                    self.report.add_check(
                        check_name=f"opnsense_{resource_type}_duplicate_{name}",
                        passed=False,
                        message=f"Duplicate {resource_type} name: '{name}'",
                        level=ValidationLevel.ERROR,
                    )
                seen.add(name)
