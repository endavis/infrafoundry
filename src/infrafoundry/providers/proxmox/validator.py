"""Validation logic for Proxmox provider."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypedDict, cast

import urllib3

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.types import EnvironmentData, ProxmoxProviderSettings
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.core.validation_helpers import BaseAPIValidator
from infrafoundry.providers.proxmox.validators import (
    NetworkValidator,
    NodeValidator,
    StorageValidator,
    TemplateValidator,
    VMIDValidator,
)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class ClusterVM(TypedDict, total=False):
    """Typed representation of a VM entry in the Proxmox cluster listing."""

    vmid: int
    name: str
    template: int
    type: str


@dataclass
class ProxmoxResourceReferences:
    """Aggregated references extracted from resource configs."""

    nodes: set[str]
    storage_pools: set[tuple[str, str]]
    bridges: set[tuple[str, str]]
    template_refs: dict[str, list[str]]
    vmids: dict[int, str]
    mac_addresses: dict[str, str]


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

    def __init__(self, env_config: EnvironmentData, report: ValidationReport) -> None:
        """Initialize Proxmox validator.

        Args:
            env_config: Environment configuration including provider_settings
            report: ValidationReport to add results to
        """
        self.env_config = env_config
        self.report = report
        self.api_validator = BaseAPIValidator("proxmox", env_config, report)
        self.provider_settings = cast(ProxmoxProviderSettings, self.api_validator.provider_settings)
        self._cluster_vm_cache: list[ClusterVM] | None = None
        self._cluster_vm_cache_populated = False

        # Initialize specialized validators
        self.node_validator = NodeValidator(self.api_validator, report)
        self.storage_validator = StorageValidator(self.api_validator, report)
        self.network_validator = NetworkValidator(self.api_validator, report)
        self.template_validator = TemplateValidator(report)
        self.vmid_validator = VMIDValidator(report)

    def validate_connectivity(self) -> None:
        """Validate connectivity to Proxmox API.

        Checks:
        - API endpoint is reachable
        - Authentication credentials are valid
        - Can retrieve cluster status
        """
        # Validate credentials - api_url and node are required
        credentials = self.api_validator.get_credentials(required_fields=["api_url", "node"])
        if not credentials:
            return

        # Build API token from either format:
        # Format 1: api_token (full token string)
        # Format 2: api_token_id + api_token_secret (Terraform provider format)
        api_token = self._get_api_token()
        if not api_token:
            self.api_validator.add_error(
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
        response_ok = self.api_validator.check_api_connectivity(
            url=version_url,
            headers={"Authorization": auth_header},
            verify_ssl=False,
        )

        # If connection succeeded, get version info (best-effort)
        if response_ok:
            version_data = self.api_validator.fetch_json(
                url=version_url,
                headers={"Authorization": auth_header},
                verify_ssl=False,
                timeout=10,
                check_name="proxmox_version",
                error_level=ValidationLevel.INFO,
                optional=True,
            )
            if version_data:
                version = version_data.get("data", {}).get("version", "unknown")
                self.api_validator.add_success(
                    check_name="proxmox_version",
                    message=f"Proxmox VE version: {version}",
                )

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
        if api_url is None or api_token is None:
            return  # Already reported in validate_connectivity

        try:
            # Build auth header
            auth_header = f"PVEAPIToken={api_token}"
            headers = {"Authorization": auth_header}

            # Collect all references from resources
            resource_refs = self._collect_resource_references(resources, default_node)

            # Get cluster VMs once for template and VMID validation
            cluster_vms = self._get_cluster_vms(
                api_url, headers, check_name="proxmox_cluster_resources"
            )

            # Validate each type of reference using specialized validators
            self.node_validator.validate(api_url, headers, resource_refs.nodes)
            self.storage_validator.validate(api_url, headers, resource_refs.storage_pools)
            self.network_validator.validate(api_url, headers, resource_refs.bridges)
            self.template_validator.validate(cluster_vms, resource_refs.template_refs)
            self.vmid_validator.validate(cluster_vms, resource_refs.vmids)

        except Exception as exc:
            self.api_validator.handle_validation_exception(
                check_name="proxmox_validation",
                error=exc,
                warning_level=ValidationLevel.WARNING,
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
    ) -> ProxmoxResourceReferences:
        """Collect all resource references from configurations."""
        nodes: set[str] = set()
        storage_pools: set[tuple[str, str]] = set()
        bridges: set[tuple[str, str]] = set()
        template_refs: dict[str, list[str]] = {}
        vmids: dict[int, str] = {}
        mac_addresses: dict[str, str] = {}

        for resource in resources:
            config = resource.config or {}
            resource_name = resource.name

            # Collect target nodes
            target_node = config.get("target_node", default_node)
            if target_node:
                nodes.add(target_node)

            # Collect storage pools (VM disk, container rootfs, or top-level storage)
            if (
                (disk_config := config.get("disk"))
                and isinstance(disk_config, dict)
                and (storage := disk_config.get("storage"))
                and target_node
            ):
                storage_pools.add((target_node, storage))
            if (
                (rootfs_config := config.get("rootfs"))
                and isinstance(rootfs_config, dict)
                and (storage := rootfs_config.get("storage"))
                and target_node
            ):
                storage_pools.add((target_node, storage))
            if (storage := config.get("storage")) and target_node:
                storage_pools.add((target_node, storage))

            # Collect network bridges (network can be a dict or list of dicts)
            network_config = config.get("network")
            nic_list: list[dict[str, Any]] = []
            if isinstance(network_config, dict):
                nic_list = [network_config]
            elif isinstance(network_config, list):
                nic_list = [n for n in network_config if isinstance(n, dict)]
            for nic in nic_list:
                if (bridge := nic.get("bridge")) and target_node:
                    bridges.add((target_node, bridge))

            # Collect template references (for VMs that clone)
            # clone can be a scalar VMID or a dict with vm_id key
            if resource.type == "vm" and (clone_ref := config.get("clone")):
                if isinstance(clone_ref, dict):
                    key = str(clone_ref.get("vm_id", ""))
                else:
                    key = str(clone_ref)
                if key:
                    template_refs.setdefault(key, []).append(resource_name)

            # Collect VMIDs/CTIDs and check for duplicates
            # Containers use 'ctid' but share the same Proxmox ID space as VMs
            vmid = config.get("vmid") or config.get("ctid")
            if vmid:
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

            # Collect MAC addresses and check for conflicts (uses nic_list from above)
            for nic in nic_list:
                if mac := nic.get("macaddr"):
                    mac_upper = mac.upper()
                    if mac_upper in mac_addresses:
                        self.report.add_check(
                            check_name=f"proxmox_mac_{mac}_duplicate",
                            passed=False,
                            message=(
                                f"MAC address {mac} used by multiple resources: "
                                f"{mac_addresses[mac_upper]} and {resource_name}"
                            ),
                            level=ValidationLevel.ERROR,
                        )
                    mac_addresses[mac_upper] = resource_name

        return ProxmoxResourceReferences(
            nodes=nodes,
            storage_pools=storage_pools,
            bridges=bridges,
            template_refs=template_refs,
            vmids=vmids,
            mac_addresses=mac_addresses,
        )

    def _get_cluster_vms(
        self,
        api_url: str,
        headers: dict[str, str],
        *,
        check_name: str,
    ) -> list[ClusterVM] | None:
        """Fetch and cache cluster VM data for template/vmid checks."""
        if self._cluster_vm_cache_populated:
            return self._cluster_vm_cache

        data = self.api_validator.fetch_json(
            url=f"{api_url}/cluster/resources",
            headers=headers,
            verify_ssl=False,
            timeout=10,
            params={"type": "vm"},
            check_name=check_name,
            error_message="Failed to query cluster resources (status {status})",
            error_level=ValidationLevel.WARNING,
        )
        self._cluster_vm_cache_populated = True
        if not data:
            self._cluster_vm_cache = None
            return None
        self._cluster_vm_cache = data.get("data", [])
        return self._cluster_vm_cache
