"""Raw Proxmox API state snapshot."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import requests

from infrafoundry.core.exceptions import APIError
from infrafoundry.core.types import EnvironmentData, ProxmoxProviderSettings
from infrafoundry.providers.proxmox.api_client import ProxmoxClient

logger = logging.getLogger(__name__)


class ProxmoxStateDumper:
    """Capture a raw JSON snapshot of a live Proxmox cluster's API state.

    The dumper walks a curated list of Proxmox Virtual Environment (PVE) API
    endpoints and saves the unwrapped ``data`` payloads grouped by section
    into a single JSON file. Saves are atomic and incremental: after each
    section completes, the full accumulated result is written to a temp file
    and then ``os.replace``-d over the target, so ``Ctrl+C`` or a crash
    leaves a usable partial dump rather than a truncated file.

    Per-call failures do not abort the dump:

    - timeouts are recorded inline as ``{"__timeout__": True, "path": ...}``
    - other API errors are recorded as ``{"__error__": str, "path": ...}``

    This is intended for cluster audit, drift debugging, and post-incident
    forensics — not for day-to-day config management. For generating
    InfraFoundry YAML, use :class:`ProxmoxConfigExporter` instead.
    """

    # Static per-cluster endpoints (no node/VM enumeration required).
    _STATIC_ENDPOINTS: tuple[tuple[str, str], ...] = (
        ("meta.version", "version"),
        ("cluster.status", "cluster/status"),
        ("cluster.resources", "cluster/resources"),
        ("cluster.options", "cluster/options"),
        ("cluster.ha.status", "cluster/ha/status/current"),
        ("cluster.ha.groups", "cluster/ha/groups"),
        ("cluster.ha.resources", "cluster/ha/resources"),
        ("cluster.replication", "cluster/replication"),
        ("cluster.backup", "cluster/backup"),
        ("cluster.firewall.options", "cluster/firewall/options"),
        ("cluster.firewall.rules", "cluster/firewall/rules"),
        ("cluster.firewall.groups", "cluster/firewall/groups"),
        ("cluster.firewall.aliases", "cluster/firewall/aliases"),
        ("cluster.firewall.ipset", "cluster/firewall/ipset"),
        ("cluster.firewall.refs", "cluster/firewall/refs"),
        ("access.users", "access/users"),
        ("access.groups", "access/groups"),
        ("access.roles", "access/roles"),
        ("access.acl", "access/acl"),
        ("access.domains", "access/domains"),
        ("pools", "pools"),
        ("storage", "storage"),
    )

    # Endpoints collected once per node, relative to ``nodes/{node}``.
    _NODE_ENDPOINTS: tuple[tuple[str, str], ...] = (
        ("status", "status"),
        ("version", "version"),
        ("dns", "dns"),
        ("hosts", "hosts"),
        ("time", "time"),
        ("network", "network"),
        ("storage", "storage"),
        ("disks.list", "disks/list"),
        ("disks.zfs", "disks/zfs"),
        ("disks.lvm", "disks/lvm"),
        ("disks.directory", "disks/directory"),
        ("firewall.options", "firewall/options"),
        ("firewall.rules", "firewall/rules"),
        ("qemu", "qemu"),
        ("lxc", "lxc"),
        ("apt.versions", "apt/versions"),
        ("services", "services"),
        ("subscription", "subscription"),
    )

    # Endpoints collected once per QEMU VM, relative to ``nodes/{node}/qemu/{vmid}``.
    _QEMU_ENDPOINTS: tuple[tuple[str, str], ...] = (
        ("config", "config"),
        ("pending", "pending"),
    )

    # Endpoints collected once per LXC container, relative to ``nodes/{node}/lxc/{vmid}``.
    _LXC_ENDPOINTS: tuple[tuple[str, str], ...] = (("config", "config"),)

    def __init__(self, env_config: EnvironmentData, timeout: int = 20) -> None:
        """Initialize the dumper.

        Args:
            env_config: Environment configuration (as produced by
                ``EnvironmentConfig.model_dump()``). The ``provider_settings``
                section must include a ``proxmox`` entry with ``api_url`` plus
                either ``api_token`` or the ``api_token_id``/``api_token_secret``
                pair.
            timeout: Per-request timeout in seconds. Defaults to 20 — large
                enough for most cluster endpoints, short enough that a hung
                node does not stall the whole dump.
        """
        self.env_config = env_config
        self.timeout = timeout
        provider_settings: ProxmoxProviderSettings = env_config.get("provider_settings", {}).get(
            "proxmox", {}
        )  # type: ignore[assignment]
        client = ProxmoxClient.from_provider_settings(provider_settings)
        if client is None:
            raise ValueError(
                "Proxmox credentials are not configured: set "
                "provider_settings.proxmox.api_url plus api_token or "
                "api_token_id/api_token_secret."
            )
        # Override the default client timeout with the dumper's per-call budget.
        client.timeout = timeout
        self._client = client

    def dump(self, output_path: Path) -> dict[str, Any]:
        """Walk the Proxmox API and write a JSON snapshot to ``output_path``.

        The dump is saved incrementally after each section so the file on
        disk is always valid JSON even if the process is interrupted.

        Args:
            output_path: Target file. Parent directories are created if
                needed; any existing file is atomically replaced at the end.

        Returns:
            The complete dump dictionary (also written to disk).
        """
        output_path = output_path.expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)

        result: dict[str, Any] = {}

        # Static per-cluster endpoints.
        for section_key, endpoint in self._STATIC_ENDPOINTS:
            self._store(result, section_key, self._fetch(endpoint))
            self._save(result, output_path)

        # Per-storage detail (discovered from the ``storage`` listing).
        storages = self._storage_ids(result.get("storage"))
        if storages:
            result["storage.detail"] = {}
            for sid in storages:
                result["storage.detail"][sid] = self._fetch(f"storage/{sid}")
            self._save(result, output_path)

        # Per-node enumeration (includes VMs and containers).
        nodes = self._node_names(self._fetch("nodes"))
        result["nodes"] = nodes
        self._save(result, output_path)

        for node in nodes:
            node_section: dict[str, Any] = {}
            for label, suffix in self._NODE_ENDPOINTS:
                node_section[label] = self._fetch(f"nodes/{node}/{suffix}")
            result[f"node:{node}"] = node_section
            self._save(result, output_path)

            qemu_section = self._dump_guests(
                node_section.get("qemu"),
                node,
                "qemu",
                self._QEMU_ENDPOINTS,
            )
            if qemu_section:
                result[f"node:{node}:qemu"] = qemu_section
                self._save(result, output_path)

            lxc_section = self._dump_guests(
                node_section.get("lxc"),
                node,
                "lxc",
                self._LXC_ENDPOINTS,
            )
            if lxc_section:
                result[f"node:{node}:lxc"] = lxc_section
                self._save(result, output_path)

        return result

    def _fetch(self, path: str) -> Any:
        """Fetch and unwrap a single PVE endpoint.

        Returns the ``data`` payload on success. On timeout, returns a
        sentinel ``{"__timeout__": True, "path": path}``. On any other
        ``APIError`` (including auth failures and connection errors),
        returns ``{"__error__": message, "path": path}``. This mirrors the
        prototype's behavior: one bad endpoint should never abort the dump.
        """
        try:
            response = self._client.get_json(path)
        except APIError as exc:
            if isinstance(exc.__cause__, requests.exceptions.Timeout):
                logger.warning("Timeout fetching %s after %ss", path, self.timeout)
                return {"__timeout__": True, "path": path}
            logger.warning("Error fetching %s: %s", path, exc)
            return {"__error__": str(exc), "path": path}
        return response.get("data")

    @staticmethod
    def _storage_ids(storage_data: Any) -> list[str]:
        """Extract storage IDs from the ``storage`` section payload."""
        if not isinstance(storage_data, list):
            return []
        ids: list[str] = []
        for item in storage_data:
            if not isinstance(item, dict):
                continue
            sid = item.get("storage")
            if isinstance(sid, str):
                ids.append(sid)
        return ids

    @staticmethod
    def _node_names(nodes_data: Any) -> list[str]:
        """Extract node names from the ``nodes`` endpoint payload."""
        if not isinstance(nodes_data, list):
            return []
        names: list[str] = []
        for item in nodes_data:
            if not isinstance(item, dict):
                continue
            name = item.get("node")
            if isinstance(name, str):
                names.append(name)
        return names

    def _dump_guests(
        self,
        guests_data: Any,
        node: str,
        kind: str,
        endpoints: tuple[tuple[str, str], ...],
    ) -> dict[str, dict[str, Any]]:
        """Collect per-guest endpoints (QEMU VMs or LXC containers) on a node."""
        if not isinstance(guests_data, list):
            return {}
        section: dict[str, dict[str, Any]] = {}
        for guest in guests_data:
            if not isinstance(guest, dict):
                continue
            vmid = guest.get("vmid")
            if vmid is None:
                continue
            guest_payload: dict[str, Any] = {}
            for label, suffix in endpoints:
                guest_payload[label] = self._fetch(f"nodes/{node}/{kind}/{vmid}/{suffix}")
            section[str(vmid)] = guest_payload
        return section

    @staticmethod
    def _store(result: dict[str, Any], dotted_key: str, value: Any) -> None:
        """Store ``value`` in ``result`` at the nested path described by ``dotted_key``.

        Example: ``_store(r, "cluster.firewall.rules", v)`` is equivalent to
        ``r.setdefault("cluster", {}).setdefault("firewall", {})["rules"] = v``.
        """
        parts = dotted_key.split(".")
        target = result
        for part in parts[:-1]:
            existing = target.get(part)
            if not isinstance(existing, dict):
                existing = {}
                target[part] = existing
            target = existing
        target[parts[-1]] = value

    @staticmethod
    def _save(result: dict[str, Any], path: Path) -> None:
        """Atomically write ``result`` to ``path`` (via ``<path>.tmp``)."""
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(result, indent=2, sort_keys=False))
        tmp_path.replace(path)
