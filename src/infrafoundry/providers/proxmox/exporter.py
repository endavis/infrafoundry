"""Export existing Proxmox configuration to InfraFoundry YAML."""

from __future__ import annotations

from typing import Any

import requests
import yaml

from infrafoundry.core.types import EnvironmentData


class ProxmoxConfigExporter:
    """Exports Proxmox resources into InfraFoundry YAML format."""

    def __init__(self, env_config: EnvironmentData) -> None:
        self.env_config = env_config
        provider_settings = env_config.get("provider_settings", {}).get("proxmox", {})
        self.api_url = provider_settings.get("api_url")
        self.api_token = provider_settings.get("api_token")
        self.api_token_id = provider_settings.get("api_token_id")
        self.api_token_secret = provider_settings.get("api_token_secret")
        self.verify_ssl = provider_settings.get("verify_ssl", False)
        self.node = provider_settings.get("node")

    def export(
        self,
        node_filter: str | None = None,
        resource_filter: str | None = None,
    ) -> dict[str, str]:
        """Export Proxmox VMs, networks, and storage to YAML strings."""
        if not self.api_url:
            raise ValueError("Proxmox api_url not configured in provider_settings")

        token = self._build_token()
        headers = {"Authorization": f"PVEAPIToken={token}"}

        nodes = self._fetch_nodes(headers)
        if node_filter:
            nodes = [n for n in nodes if n["node"] == node_filter]

        exports: dict[str, str] = {}

        if resource_filter in (None, "vm"):
            exports.update(self._export_vms(headers, nodes))
        if resource_filter in (None, "network"):
            exports.update(self._export_networks(headers, nodes))
        if resource_filter in (None, "storage"):
            exports.update(self._export_storage(headers, nodes))

        return exports

    def _build_token(self) -> str:
        token: str | None = self.api_token
        if not token and self.api_token_id and self.api_token_secret:
            token = f"{self.api_token_id}={self.api_token_secret}"
        if not token:
            raise ValueError("Proxmox API token not configured")
        return token

    def _fetch(self, path: str, headers: dict[str, str]) -> list[dict[str, Any]]:
        url = f"{self.api_url}{path}"
        response = requests.get(url, headers=headers, verify=self.verify_ssl, timeout=10)
        response.raise_for_status()
        data = response.json().get("data", [])
        if not isinstance(data, list):
            return []
        return data

    def _fetch_nodes(self, headers: dict[str, str]) -> list[dict[str, Any]]:
        return self._fetch("/nodes", headers)

    def _export_vms(self, headers: dict[str, str], nodes: list[dict[str, Any]]) -> dict[str, str]:
        exports: dict[str, str] = {}
        for node in nodes:
            node_name = node["node"]
            vms = self._fetch(f"/nodes/{node_name}/qemu", headers)
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
                exports[f"{node_name}-vms.yaml"] = yaml.safe_dump(
                    {"resources": vm_resources}, sort_keys=False
                )
        return exports

    def _export_networks(
        self, headers: dict[str, str], nodes: list[dict[str, Any]]
    ) -> dict[str, str]:
        exports: dict[str, str] = {}
        for node in nodes:
            node_name = node["node"]
            networks = self._fetch(f"/nodes/{node_name}/network", headers)
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
                exports[f"{node_name}-networks.yaml"] = yaml.safe_dump(
                    {"resources": resources}, sort_keys=False
                )
        return exports

    def _export_storage(
        self, headers: dict[str, str], nodes: list[dict[str, Any]]
    ) -> dict[str, str]:
        exports: dict[str, str] = {}
        storages = self._fetch("/storage", headers)
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
            exports["storage.yaml"] = yaml.safe_dump({"resources": resources}, sort_keys=False)
        return exports
