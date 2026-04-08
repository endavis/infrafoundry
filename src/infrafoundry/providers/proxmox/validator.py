"""Validation logic for Proxmox provider."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypedDict, cast

import urllib3

from infrafoundry.core.exceptions import APIError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.tailscale import TailscaleSchemaError, process_tailscale_config
from infrafoundry.core.types import EnvironmentData, ProxmoxProviderSettings
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.core.validation_helpers import (
    BaseAPIValidator,
    validate_terraform_secrets_references,
)
from infrafoundry.providers.proxmox.api_client import ProxmoxClient
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
    - Node availability
    - Storage pool existence and status
    - Network bridge availability
    - VM template existence
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
        self.node_validator = NodeValidator(report)
        self.storage_validator = StorageValidator(report)
        self.network_validator = NetworkValidator(report)
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

        # Create API client from provider settings
        client = ProxmoxClient.from_provider_settings(self.provider_settings)
        if not client:
            self.api_validator.add_error(
                check_name="proxmox_credentials",
                message=(
                    "Missing API token. Provide either 'api_token' or both "
                    "'api_token_id' and 'api_token_secret'"
                ),
            )
            return

        # Test API connectivity
        try:
            version_data = client.get_json("version")
            version = version_data.get("data", {}).get("version", "unknown")
            self.api_validator.add_success(
                check_name="proxmox_connectivity",
                message=f"Proxmox API connected successfully (version: {version})",
            )
        except APIError as exc:
            self.api_validator.add_error(
                check_name="proxmox_connectivity",
                message=f"Proxmox API connectivity failed: {exc.message}",
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
        - ``terraform_secrets`` references resolve in env secrets

        Args:
            resources: List of resources to validate
        """
        # Local: validate tailscale schema (issue #212) and terraform_secrets
        # references against env secrets. Tailscale validation must run first
        # because process_tailscale_config auto-populates terraform_secrets
        # from the tailscale.auth.* references. Done before live API checks
        # so misconfigurations surface even when the cluster is unreachable.
        for resource in resources:
            if resource.type != "vm":
                continue
            if (resource.config or {}).get("tailscale") is None:
                continue
            try:
                process_tailscale_config(resource, base64_encode=False)
            except TailscaleSchemaError as exc:
                self.report.add_check(
                    check_name=f"proxmox_tailscale_schema_{resource.name}",
                    passed=False,
                    message=str(exc),
                    level=ValidationLevel.ERROR,
                )

        validate_terraform_secrets_references("proxmox", resources, self.env_config, self.report)

        default_node = self.provider_settings.get("node")

        # Create API client
        client = ProxmoxClient.from_provider_settings(self.provider_settings)
        if not client:
            return  # Already reported in validate_connectivity

        try:
            # Collect all references from resources
            resource_refs = self._collect_resource_references(resources, default_node)

            # Get cluster VMs once for template and VMID validation
            cluster_vms = self._get_cluster_vms(client)

            # Validate each type of reference using specialized validators
            self.node_validator.validate(client, resource_refs.nodes)
            self.storage_validator.validate(client, resource_refs.storage_pools)
            self.network_validator.validate(client, resource_refs.bridges)
            self.template_validator.validate(cluster_vms, resource_refs.template_refs)
            self.vmid_validator.validate(cluster_vms, resource_refs.vmids)

        except Exception as exc:
            self.api_validator.handle_validation_exception(
                check_name="proxmox_validation",
                error=exc,
                warning_level=ValidationLevel.WARNING,
            )

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

    def _get_cluster_vms(self, client: ProxmoxClient) -> list[ClusterVM] | None:
        """Fetch and cache cluster VM data for template/vmid checks."""
        if self._cluster_vm_cache_populated:
            return self._cluster_vm_cache

        self._cluster_vm_cache_populated = True
        try:
            data = client.get_json("cluster/resources", params={"type": "vm"})
        except APIError as exc:
            self.report.add_check(
                check_name="proxmox_cluster_resources",
                passed=False,
                message=f"Failed to query cluster resources: {exc.message}",
                level=ValidationLevel.WARNING,
            )
            self._cluster_vm_cache = None
            return None

        self._cluster_vm_cache = data.get("data", [])
        return self._cluster_vm_cache
