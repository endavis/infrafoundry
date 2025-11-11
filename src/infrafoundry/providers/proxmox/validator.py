"""Validation logic for Proxmox provider.

This module contains all validation methods for checking Proxmox infrastructure
configurations against live API state before deployment.
"""

from typing import Any

import requests
import urllib3

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel
from infrafoundry.core.validation_helpers import BaseProviderValidator

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class ProxmoxValidator:
    """Validates Proxmox configurations against live API state.

    Performs comprehensive pre-flight validation including:
    - API connectivity and authentication
    - Node availability and status
    - Storage pool existence and state
    - Network bridge configuration
    - Template availability (by VMID or name)
    - VMID conflicts and availability
    - MAC address conflicts
    """

    def __init__(self, env_config: dict[str, Any], report: Any):
        """Initialize Proxmox validator.

        Args:
            env_config: Environment configuration including provider_settings
            report: ValidationReport to add results to
        """
        self.env_config = env_config
        self.report = report
        self.provider_settings = env_config.get("provider_settings", {}).get("proxmox", {})

    def validate_connectivity(self) -> None:
        """Validate connectivity to Proxmox API.

        Checks:
        - API endpoint is reachable
        - Authentication credentials are valid
        - Can retrieve cluster status
        """
        validator = BaseProviderValidator(
            provider_name="proxmox",
            env_config=self.env_config,
            report=self.report,
        )

        # Validate credentials - api_url and node are required
        credentials = validator.validate_credentials(required_fields=["api_url", "node"])
        if not credentials:
            return

        # Build API token from either format:
        # Format 1: api_token (full token string)
        # Format 2: api_token_id + api_token_secret (Terraform provider format)
        api_token = self._get_api_token()
        if not api_token:
            validator.add_error_check(
                check_name="proxmox_credentials",
                message=(
                    "Missing API token. Provide either 'api_token' or both "
                    "'api_token_id' and 'api_token_secret'"
                ),
            )
            return

        # Build auth header for Proxmox API
        # Format: "PVEAPIToken=USER@REALM!TOKENID=SECRET"
        auth_header = f"PVEAPIToken={api_token}"

        # Test API connectivity
        version_url = f"{credentials['api_url']}/version"
        response_ok = validator.check_api_connectivity(
            url=version_url,
            headers={"Authorization": auth_header},
            verify_ssl=False,
        )

        # If connection succeeded, get version info
        if response_ok:
            try:
                response = requests.get(
                    version_url,
                    headers={"Authorization": auth_header},
                    verify=False,
                    timeout=10,
                )
                if response.status_code == 200:
                    version_data = response.json().get("data", {})
                    version = version_data.get("version", "unknown")
                    # Update success message with version
                    validator.add_success_check(
                        check_name="proxmox_version",
                        message=f"Proxmox VE version: {version}",
                    )
            except Exception:
                pass  # Version info is optional, connectivity already validated

    def validate_references(self, resources: list[ResourceConfig]) -> None:
        """Validate that referenced Proxmox resources exist.

        Checks:
        - Target nodes exist and are online
        - VM templates exist (by VMID or name)
        - Network bridges are available
        - Storage pools exist and are active
        - VMIDs are not already in use
        - MAC addresses are not duplicated

        Args:
            resources: List of resources to validate
        """
        api_url = self.provider_settings.get("api_url")
        default_node = self.provider_settings.get("node")

        # Build API token
        api_token = self._get_api_token()
        if not all([api_url, api_token]):
            return  # Already reported in validate_connectivity

        try:
            # Build auth header
            auth_header = f"PVEAPIToken={api_token}"
            headers = {"Authorization": auth_header}

            # Collect all references from resources
            resource_refs = self._collect_resource_references(resources, default_node)

            # Validate each type of reference
            self._validate_nodes(api_url, headers, resource_refs["nodes"])
            self._validate_storage(api_url, headers, resource_refs["storage_pools"])
            self._validate_bridges(api_url, headers, resource_refs["bridges"])
            self._validate_templates(api_url, headers, resource_refs["template_refs"])
            self._validate_vmids(api_url, headers, resource_refs["vmids"])

        except ImportError:
            self.report.add_check(
                check_name="proxmox_validation",
                passed=False,
                message="requests library not available for validation",
                level=ValidationLevel.WARNING,
            )
        except Exception as e:
            self.report.add_check(
                check_name="proxmox_validation",
                passed=False,
                message=f"Unexpected error during validation: {e}",
                level=ValidationLevel.WARNING,
            )

    def _get_api_token(self) -> str | None:
        """Get API token from provider settings.

        Supports both formats:
        - api_token: Full token string
        - api_token_id + api_token_secret: Terraform provider format

        Returns:
            API token string or None if not configured
        """
        api_token = self.provider_settings.get("api_token")
        if not api_token:
            token_id = self.provider_settings.get("api_token_id")
            token_secret = self.provider_settings.get("api_token_secret")
            if token_id and token_secret:
                api_token = f"{token_id}={token_secret}"
        return api_token

    def _collect_resource_references(
        self, resources: list[ResourceConfig], default_node: str | None
    ) -> dict[str, Any]:
        """Collect all resource references from configurations.

        Args:
            resources: List of resources to scan
            default_node: Default node name

        Returns:
            Dict with collected references:
            - nodes: Set of node names
            - storage_pools: Set of (node, storage) tuples
            - bridges: Set of (node, bridge) tuples
            - template_refs: Dict of {vmid_or_name: [resource_names]}
            - vmids: Dict of {vmid: resource_name}
            - mac_addresses: Dict of {mac: resource_name}
        """
        nodes = set()
        storage_pools = set()
        bridges = set()
        template_refs: dict[Any, list[str]] = {}
        vmids: dict[int, str] = {}
        mac_addresses: dict[str, str] = {}

        for resource in resources:
            config = resource.config or {}
            resource_name = resource.name

            # Collect target nodes
            target_node = config.get("target_node", default_node)
            if target_node:
                nodes.add(target_node)

            # Collect storage pools
            if disk_config := config.get("disk"):
                if isinstance(disk_config, dict) and (storage := disk_config.get("storage")):
                    storage_pools.add((target_node, storage))
            if storage := config.get("storage"):
                storage_pools.add((target_node, storage))

            # Collect network bridges
            if network_config := config.get("network"):
                if isinstance(network_config, dict) and (bridge := network_config.get("bridge")):
                    bridges.add((target_node, bridge))

            # Collect template references (for VMs that clone)
            if resource.type == "vm" and (clone_ref := config.get("clone")):
                if clone_ref not in template_refs:
                    template_refs[clone_ref] = []
                template_refs[clone_ref].append(resource_name)

            # Collect VMIDs and check for duplicates
            if vmid := config.get("vmid"):
                if vmid in vmids:
                    self.report.add_check(
                        check_name=f"proxmox_vmid_{vmid}_duplicate",
                        passed=False,
                        message=(
                            f"VMID {vmid} used by multiple resources: "
                            f"{vmids[vmid]} and {resource_name}"
                        ),
                        level=ValidationLevel.ERROR,
                    )
                vmids[vmid] = resource_name

            # Collect MAC addresses and check for conflicts
            if network_config := config.get("network"):
                if isinstance(network_config, dict) and (mac := network_config.get("macaddr")):
                    mac_upper = mac.upper()
                    if mac_upper in mac_addresses:
                        self.report.add_check(
                            check_name=f"proxmox_mac_{mac}_duplicate",
                            passed=False,
                            message=(
                                f"MAC {mac} used by multiple resources: "
                                f"{mac_addresses[mac_upper]} and {resource_name}"
                            ),
                            level=ValidationLevel.ERROR,
                        )
                    mac_addresses[mac_upper] = resource_name

        return {
            "nodes": nodes,
            "storage_pools": storage_pools,
            "bridges": bridges,
            "template_refs": template_refs,
            "vmids": vmids,
            "mac_addresses": mac_addresses,
        }

    def _format_uptime(self, seconds: int) -> str:
        """Convert uptime in seconds to human-readable format.

        Args:
            seconds: Uptime in seconds

        Returns:
            Human-readable uptime string (e.g., "29 days, 3 hours, 15 minutes")
        """
        if seconds < 60:
            return f"{seconds} seconds"

        minutes = seconds // 60
        if minutes < 60:
            return f"{minutes} minutes"

        hours = minutes // 60
        remaining_minutes = minutes % 60
        if hours < 24:
            if remaining_minutes > 0:
                return f"{hours} hours, {remaining_minutes} minutes"
            return f"{hours} hours"

        days = hours // 24
        remaining_hours = hours % 24
        if remaining_hours > 0:
            return f"{days} days, {remaining_hours} hours"
        return f"{days} days"

    def _validate_nodes(self, api_url: str, headers: dict[str, str], nodes: set[str]) -> None:
        """Validate that nodes exist and are online.

        Args:
            api_url: Proxmox API base URL
            headers: HTTP headers with authorization
            nodes: Set of node names to validate
        """
        for node in nodes:
            try:
                node_url = f"{api_url}/nodes/{node}/status"
                response = requests.get(node_url, headers=headers, timeout=10, verify=False)
                if response.status_code == 200:
                    status = response.json().get("data", {})
                    uptime_seconds = status.get("uptime", 0)
                    uptime_formatted = self._format_uptime(uptime_seconds)
                    self.report.add_check(
                        check_name=f"proxmox_node_{node}",
                        passed=True,
                        message=f"Node '{node}' is online (uptime: {uptime_formatted})",
                        level=ValidationLevel.INFO,
                    )
                else:
                    self.report.add_check(
                        check_name=f"proxmox_node_{node}",
                        passed=False,
                        message=f"Node '{node}' not accessible (HTTP {response.status_code})",
                        level=ValidationLevel.ERROR,
                    )
            except Exception as e:
                self.report.add_check(
                    check_name=f"proxmox_node_{node}",
                    passed=False,
                    message=f"Error checking node '{node}': {e}",
                    level=ValidationLevel.ERROR,
                )

    def _validate_storage(
        self, api_url: str, headers: dict[str, str], storage_pools: set[tuple[str, str]]
    ) -> None:
        """Validate that storage pools exist and are active.

        Args:
            api_url: Proxmox API base URL
            headers: HTTP headers with authorization
            storage_pools: Set of (node, storage) tuples to validate
        """
        checked_storage = set()
        for node, storage in storage_pools:
            if (node, storage) in checked_storage:
                continue
            checked_storage.add((node, storage))

            try:
                storage_url = f"{api_url}/nodes/{node}/storage"
                response = requests.get(storage_url, headers=headers, timeout=10, verify=False)
                if response.status_code == 200:
                    storages = response.json().get("data", [])
                    storage_info = next((s for s in storages if s.get("storage") == storage), None)
                    if storage_info:
                        active = storage_info.get("active", 0)
                        storage_type = storage_info.get("type", "unknown")
                        if active:
                            self.report.add_check(
                                check_name=f"proxmox_storage_{node}_{storage}",
                                passed=True,
                                message=(
                                    f"Storage '{storage}' on node '{node}' is active "
                                    f"(type: {storage_type})"
                                ),
                                level=ValidationLevel.INFO,
                            )
                        else:
                            self.report.add_check(
                                check_name=f"proxmox_storage_{node}_{storage}",
                                passed=False,
                                message=f"Storage '{storage}' on node '{node}' is inactive",
                                level=ValidationLevel.ERROR,
                            )
                    else:
                        available = [s.get("storage") for s in storages]
                        self.report.add_check(
                            check_name=f"proxmox_storage_{node}_{storage}",
                            passed=False,
                            message=(
                                f"Storage '{storage}' not found on node '{node}'. "
                                f"Available: {available}"
                            ),
                            level=ValidationLevel.ERROR,
                        )
            except Exception as e:
                self.report.add_check(
                    check_name=f"proxmox_storage_{node}_{storage}",
                    passed=False,
                    message=f"Error checking storage '{storage}' on '{node}': {e}",
                    level=ValidationLevel.WARNING,
                )

    def _validate_bridges(
        self, api_url: str, headers: dict[str, str], bridges: set[tuple[str, str]]
    ) -> None:
        """Validate that network bridges exist.

        Args:
            api_url: Proxmox API base URL
            headers: HTTP headers with authorization
            bridges: Set of (node, bridge) tuples to validate
        """
        checked_bridges = set()
        for node, bridge in bridges:
            if (node, bridge) in checked_bridges:
                continue
            checked_bridges.add((node, bridge))

            try:
                network_url = f"{api_url}/nodes/{node}/network"
                response = requests.get(network_url, headers=headers, timeout=10, verify=False)
                if response.status_code == 200:
                    networks = response.json().get("data", [])
                    bridge_info = next(
                        (
                            n
                            for n in networks
                            if n.get("type") == "bridge" and n.get("iface") == bridge
                        ),
                        None,
                    )
                    if bridge_info:
                        self.report.add_check(
                            check_name=f"proxmox_bridge_{node}_{bridge}",
                            passed=True,
                            message=f"Bridge '{bridge}' exists on node '{node}'",
                            level=ValidationLevel.INFO,
                        )
                    else:
                        available = [n.get("iface") for n in networks if n.get("type") == "bridge"]
                        self.report.add_check(
                            check_name=f"proxmox_bridge_{node}_{bridge}",
                            passed=False,
                            message=(
                                f"Bridge '{bridge}' not found on node '{node}'. "
                                f"Available bridges: {available}"
                            ),
                            level=ValidationLevel.ERROR,
                        )
            except Exception as e:
                self.report.add_check(
                    check_name=f"proxmox_bridge_{node}_{bridge}",
                    passed=False,
                    message=f"Error checking bridge '{bridge}' on '{node}': {e}",
                    level=ValidationLevel.WARNING,
                )

    def _validate_templates(
        self, api_url: str, headers: dict[str, str], template_refs: dict[Any, list[str]]
    ) -> None:
        """Validate that templates exist (by VMID or name).

        Args:
            api_url: Proxmox API base URL
            headers: HTTP headers with authorization
            template_refs: Dict of {vmid_or_name: [resource_names]}
        """
        if not template_refs:
            return

        try:
            # Get all VMs from cluster to check templates
            cluster_url = f"{api_url}/cluster/resources?type=vm"
            response = requests.get(cluster_url, headers=headers, timeout=10, verify=False)

            if response.status_code == 200:
                vms_data = response.json().get("data", [])
                # Build maps of both VMIDs and names for templates
                templates_by_vmid = {vm["vmid"]: vm for vm in vms_data if vm.get("template") == 1}
                templates_by_name = {vm["name"]: vm for vm in vms_data if vm.get("template") == 1}

                for template_ref, resource_names in template_refs.items():
                    # Check if it's a VMID (integer) or name (string)
                    try:
                        vmid = int(template_ref)
                        if vmid in templates_by_vmid:
                            template = templates_by_vmid[vmid]
                            self.report.add_check(
                                check_name=f"proxmox_template_vmid_{vmid}",
                                passed=True,
                                message=(
                                    f"Template VMID {vmid} exists: {template.get('name', 'N/A')}"
                                ),
                                level=ValidationLevel.INFO,
                            )
                        else:
                            self.report.add_check(
                                check_name=f"proxmox_template_vmid_{vmid}",
                                passed=False,
                                message=(
                                    f"Template VMID {vmid} not found. "
                                    f"Used by: {', '.join(resource_names)}"
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
                                    f"Template '{template_ref}' exists "
                                    f"(VMID: {template.get('vmid')})"
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
            else:
                self.report.add_check(
                    check_name="proxmox_templates",
                    passed=False,
                    message=f"Failed to query templates: HTTP {response.status_code}",
                    level=ValidationLevel.WARNING,
                )
        except Exception as e:
            self.report.add_check(
                check_name="proxmox_templates",
                passed=False,
                message=f"Error validating templates: {e}",
                level=ValidationLevel.WARNING,
            )

    def _validate_vmids(self, api_url: str, headers: dict[str, str], vmids: dict[int, str]) -> None:
        """Validate that VMIDs are available (not already in use).

        Args:
            api_url: Proxmox API base URL
            headers: HTTP headers with authorization
            vmids: Dict of {vmid: resource_name}
        """
        if not vmids:
            return

        try:
            cluster_url = f"{api_url}/cluster/resources?type=vm"
            response = requests.get(cluster_url, headers=headers, timeout=10, verify=False)

            if response.status_code == 200:
                vms_data = response.json().get("data", [])
                existing_vmids = {vm["vmid"]: vm.get("name", "N/A") for vm in vms_data}

                for vmid, resource_name in vmids.items():
                    if vmid in existing_vmids:
                        # Check if it's the same resource (already exists)
                        existing_name = existing_vmids[vmid]
                        if existing_name == resource_name:
                            self.report.add_check(
                                check_name=f"proxmox_vmid_{vmid}_exists",
                                passed=True,
                                message=(
                                    f"VMID {vmid} ({resource_name}) already exists "
                                    f"(update/recreation)"
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
        except Exception as e:
            self.report.add_check(
                check_name="proxmox_vmids",
                passed=False,
                message=f"Error checking VMID availability: {e}",
                level=ValidationLevel.WARNING,
            )
