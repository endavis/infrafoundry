"""Export existing Proxmox configuration to InfraFoundry YAML."""

from __future__ import annotations

import logging
from typing import Any

import requests
import yaml

from infrafoundry.core.types import EnvironmentData

logger = logging.getLogger(__name__)


class ProxmoxConfigExporter:
    """Exports Proxmox resources into InfraFoundry YAML format.

    This exporter connects to a Proxmox cluster via the API and extracts
    configuration for VMs, networks (bridges only), and storage.

    Note: Network export only includes bridge interfaces, not all network
    interface types.
    """

    def __init__(self, env_config: EnvironmentData) -> None:
        """Initialize the Proxmox config exporter.

        Args:
            env_config: Environment configuration containing Proxmox API settings
        """
        self.env_config = env_config
        provider_settings = env_config.get("provider_settings", {}).get("proxmox", {})
        self.api_url = provider_settings.get("api_url")
        self.api_token = provider_settings.get("api_token")
        self.api_token_id = provider_settings.get("api_token_id")
        self.api_token_secret = provider_settings.get("api_token_secret")
        self.verify_ssl = provider_settings.get("verify_ssl", True)
        self.node = provider_settings.get("node")
        self.timeout = provider_settings.get("timeout", 30)  # Default 30s for large clusters
        self._session: requests.Session | None = None

    @property
    def session(self) -> requests.Session:
        """Get or create a requests session for API calls.

        Returns:
            A configured requests Session object with authorization header
        """
        if self._session is None:
            self._session = requests.Session()
            token = self._build_token()
            self._session.headers.update({"Authorization": f"PVEAPIToken={token}"})
            self._session.verify = self.verify_ssl
        return self._session

    def close(self) -> None:
        """Close the API session if it exists."""
        if self._session is not None:
            self._session.close()
            self._session = None

    def export(
        self,
        node_filter: str | None = None,
        resource_filter: str | None = None,
    ) -> dict[str, str]:
        """Export Proxmox VMs, networks, and storage to YAML strings.

        Args:
            node_filter: Optional node name to filter exports
            resource_filter: Optional resource type ('vm', 'network', 'storage')

        Returns:
            Dictionary mapping filenames to YAML content strings

        Raises:
            ValueError: If API URL is not configured
            requests.exceptions.RequestException: If API calls fail
        """
        if not self.api_url:
            raise ValueError("Proxmox api_url not configured in provider_settings")

        try:
            logger.info("Fetching Proxmox nodes...")
            nodes = self._fetch_nodes()
            if node_filter:
                nodes = [n for n in nodes if n["node"] == node_filter]
                logger.info(f"Filtered to node: {node_filter}")
            else:
                logger.info(f"Found {len(nodes)} nodes")

            exports: dict[str, str] = {}

            if resource_filter in (None, "vm"):
                logger.info("Exporting VMs...")
                exports.update(self._export_vms(nodes))
            if resource_filter in (None, "network"):
                logger.info("Exporting networks...")
                exports.update(self._export_networks(nodes))
            if resource_filter in (None, "storage"):
                logger.info("Exporting storage...")
                exports.update(self._export_storage(nodes))

            return exports
        finally:
            self.close()

    def _build_token(self) -> str:
        """Build API token from configuration.

        Returns:
            API token string for authentication

        Raises:
            ValueError: If no token configuration is found
        """
        token: str | None = self.api_token
        if not token and self.api_token_id and self.api_token_secret:
            token = f"{self.api_token_id}={self.api_token_secret}"
        if not token:
            raise ValueError("Proxmox API token not configured")
        return token

    def _fetch(self, path: str) -> list[dict[str, Any]]:
        """Fetch data from Proxmox API.

        Args:
            path: API path to fetch (e.g., '/nodes')

        Returns:
            List of data items from API response

        Raises:
            requests.exceptions.RequestException: If API call fails
        """
        url = f"{self.api_url}{path}"
        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            data = response.json().get("data", [])
            if not isinstance(data, list):
                return []
            return data
        except requests.exceptions.HTTPError as exc:
            logger.error(f"HTTP error fetching {path}: {exc}")
            raise
        except requests.exceptions.ConnectionError as exc:
            logger.error(f"Connection error fetching {path}: {exc}")
            raise
        except requests.exceptions.Timeout as exc:
            logger.error(f"Timeout fetching {path} (timeout={self.timeout}s): {exc}")
            raise
        except requests.exceptions.RequestException as exc:
            logger.error(f"Request error fetching {path}: {exc}")
            raise

    def _fetch_nodes(self) -> list[dict[str, Any]]:
        """Fetch list of Proxmox nodes.

        Returns:
            List of node data dictionaries
        """
        return self._fetch("/nodes")

    def _export_vms(self, nodes: list[dict[str, Any]]) -> dict[str, str]:
        """Export VM configurations from Proxmox nodes.

        Args:
            nodes: List of node data dictionaries

        Returns:
            Dictionary mapping filenames to YAML content
        """
        exports: dict[str, str] = {}
        for node in nodes:
            node_name = node["node"]
            logger.info(f"Fetching VMs from node {node_name}...")
            vms = self._fetch(f"/nodes/{node_name}/qemu")
            vm_resources = []
            for vm in vms:
                vm_resources.append(
                    {
                        "name": vm.get("name") or f"vm-{vm.get('vmid')}",
                        "type": "vm",
                        "provider": "proxmox",
                        "config": {
                            "vmid": vm.get("vmid"),
                            "target_node": node_name,
                            "cores": vm.get("cores"),
                            "memory": vm.get("maxmem"),
                            "status": vm.get("status"),
                        },
                    }
                )
            if vm_resources:
                logger.info(f"Exported {len(vm_resources)} VMs from {node_name}")
                exports[f"{node_name}-vms.yaml"] = yaml.safe_dump(
                    {"resources": vm_resources}, sort_keys=False
                )
        return exports

    def _export_networks(self, nodes: list[dict[str, Any]]) -> dict[str, str]:
        """Export network configurations from Proxmox nodes.

        Note: Only exports bridge interfaces, not all network interface types.

        Args:
            nodes: List of node data dictionaries

        Returns:
            Dictionary mapping filenames to YAML content
        """
        exports: dict[str, str] = {}
        for node in nodes:
            node_name = node["node"]
            logger.info(f"Fetching networks from node {node_name}...")
            networks = self._fetch(f"/nodes/{node_name}/network")
            resources = []
            for net in networks:
                if net.get("type") != "bridge":
                    continue
                resources.append(
                    {
                        "name": net.get("iface"),
                        "type": "network",
                        "provider": "proxmox",
                        "config": {
                            "target_node": node_name,
                            "bridge": net.get("iface"),
                            "cidr": net.get("cidr", ""),
                        },
                    }
                )
            if resources:
                logger.info(f"Exported {len(resources)} networks from {node_name}")
                exports[f"{node_name}-networks.yaml"] = yaml.safe_dump(
                    {"resources": resources}, sort_keys=False
                )
        return exports

    def _export_storage(self, nodes: list[dict[str, Any]]) -> dict[str, str]:
        """Export storage configurations from Proxmox cluster.

        Args:
            nodes: List of node data dictionaries (not used but kept for consistency)

        Returns:
            Dictionary mapping filenames to YAML content
        """
        exports: dict[str, str] = {}
        logger.info("Fetching storage configurations...")
        storages = self._fetch("/storage")
        resources = []
        for storage in storages:
            resources.append(
                {
                    "name": storage.get("storage"),
                    "type": "storage",
                    "provider": "proxmox",
                    "config": {
                        "type": storage.get("type"),
                        "content": storage.get("content"),
                        "nodes": storage.get("nodes"),
                    },
                }
            )
        if resources:
            logger.info(f"Exported {len(resources)} storage configurations")
            exports["storage.yaml"] = yaml.safe_dump({"resources": resources}, sort_keys=False)
        return exports
