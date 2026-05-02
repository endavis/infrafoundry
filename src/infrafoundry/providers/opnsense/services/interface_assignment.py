"""Interface-assignment service for OPNsense direct-API operations (ADR-0014).

This service provides **read-only** access to OPNsense interface assignments
on the OPNsense `26.1.6_2` REST surface. The OPNsense GUI's
"Interfaces → Assignments" page edits ``config.xml`` via legacy PHP form posts
(``interfaces_assign.php``); no REST write endpoint exists today. The
``InterfaceAssignmentManager`` consumes this service for ``list``/``migrate``
flows and exposes loud no-op stubs for ``apply``/``destroy``.

Live data source: ``client.request("GET", "interfaces/overview/interfacesInfo")``
returns ``{"rows": [...]}`` where each row carries ``identifier`` (logical
interface name like ``lan``/``wan``/``opt1``), ``device`` (physical NIC or
VLAN child), ``description``, ``ipv4``/``ipv6`` (raw dicts), ``is_physical``,
and others. Rows with empty ``identifier`` are physical NICs that are
not assigned to any logical interface — the service skips them.

The data model intentionally keeps ``ipv4``/``ipv6`` as raw ``dict[str, Any]``
pass-throughs. The OPNsense API exposes a heterogeneous mix of static, DHCP,
PPPoE, and tracking modes; deep parsing is deferred until the write path
arrives.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import yaml

from infrafoundry.core.provider import ResourceConfig

from .base import BaseService

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LiveInterfaceAssignment:
    """An interface assignment as currently configured on the OPNsense box.

    Attributes:
        identifier: Logical interface name (e.g., ``"lan"``, ``"wan"``,
            ``"opt1"``). Used as the resource ``name`` in YAML.
        device: Physical NIC or VLAN child device (e.g., ``"ixl0"``,
            ``"ixl0_vlan4000"``).
        description: Free-form description from the GUI.
        is_physical: ``True`` if ``device`` is a real NIC (not a VLAN child).
        ipv4: Raw ipv4 config from the API (mode, address, gateway, etc.).
        ipv6: Raw ipv6 config from the API.
        macaddr: Effective MAC address.
        mtu: Configured MTU (0 if unset).
    """

    identifier: str
    device: str
    description: str
    is_physical: bool
    ipv4: dict[str, Any]
    ipv6: dict[str, Any]
    macaddr: str
    mtu: int


@dataclass(frozen=True)
class InterfaceAssignmentConfig:
    """Desired-state interface-assignment configuration.

    Forward-compat schema (ADR-0013, #711): ``ipv4``/``ipv6``/``enabled``/
    ``lock`` are accepted at parse time even though writes are no-op
    today. When the write path lands, the runtime begins honoring them
    without breaking existing YAML.

    Attributes:
        name: Operator-facing identifier; equals ``identifier`` on the box.
        device: Physical NIC or VLAN child device.
        description: Free-form description.
        enabled: Forward-compat; defaults True. Ignored at runtime.
        lock: Forward-compat; defaults False. Ignored at runtime.
        ipv4: Forward-compat raw dict; ignored at runtime.
        ipv6: Forward-compat raw dict; ignored at runtime.
    """

    name: str
    device: str
    description: str
    enabled: bool = True
    lock: bool = False
    ipv4: dict[str, Any] = field(default_factory=dict)
    ipv6: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Resource-to-domain conversion
# ---------------------------------------------------------------------------


def interface_assignment_configs_from_resources(
    resources: list[ResourceConfig],
) -> list[InterfaceAssignmentConfig]:
    """Convert ``ResourceConfig`` entries to ``InterfaceAssignmentConfig`` instances.

    Non-matching resource types are silently skipped. Validation here is
    intentionally light — the validator handles cross-resource references;
    the service only enforces type sanity so manager code can rely on
    ``device`` being a ``str``, etc.

    Args:
        resources: All provider resources from ConfigManager.

    Returns:
        Validated ``InterfaceAssignmentConfig`` list.

    Raises:
        ValueError: If an entry has a non-dict config, missing ``device``,
            or non-bool ``enabled``/``lock``.
    """
    configs: list[InterfaceAssignmentConfig] = []
    for resource in resources:
        if resource.type != "interface_assignments":
            continue

        config = resource.config
        if not isinstance(config, dict):
            raise ValueError(f"interface_assignment '{resource.name}' has non-dict config")

        device = config.get("device")
        if not isinstance(device, str) or not device:
            raise ValueError(f"interface_assignment '{resource.name}' missing string 'device'")

        description = config.get("description", "")
        if not isinstance(description, str):
            raise ValueError(f"interface_assignment '{resource.name}' description must be a string")

        enabled_raw = config.get("enabled", True)
        if not isinstance(enabled_raw, bool):
            raise ValueError(f"interface_assignment '{resource.name}' enabled must be a boolean")

        lock_raw = config.get("lock", False)
        if not isinstance(lock_raw, bool):
            raise ValueError(f"interface_assignment '{resource.name}' lock must be a boolean")

        ipv4_raw = config.get("ipv4", {}) or {}
        if not isinstance(ipv4_raw, dict):
            raise ValueError(f"interface_assignment '{resource.name}' ipv4 must be a mapping")

        ipv6_raw = config.get("ipv6", {}) or {}
        if not isinstance(ipv6_raw, dict):
            raise ValueError(f"interface_assignment '{resource.name}' ipv6 must be a mapping")

        configs.append(
            InterfaceAssignmentConfig(
                name=resource.name,
                device=device,
                description=description,
                enabled=enabled_raw,
                lock=lock_raw,
                ipv4=dict(ipv4_raw),
                ipv6=dict(ipv6_raw),
            )
        )

    return configs


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class InterfaceAssignmentService(BaseService):
    """Read-only service for OPNsense interface assignments via direct API.

    OPNsense `26.1.6_2` exposes interface assignment state at
    ``GET /api/interfaces/overview/interfacesInfo`` but offers no REST
    write endpoint; writes are deferred until either an upstream API
    addition or an XML-edit shim lands. The service therefore provides:

    - ``list()`` — fetch live assignments (skip unassigned NICs).
    - ``export_to_yaml()`` — render the live state as InfraFoundry YAML.

    Method names follow the VLAN service for consistency.
    """

    def list(self) -> list[LiveInterfaceAssignment]:
        """Return all interface assignments currently configured on the box.

        Skips rows with an empty ``identifier`` — those are physical NICs
        that are not assigned to any logical interface, which is not what
        operators want to manage with this resource type.

        Returns:
            ``LiveInterfaceAssignment`` entries normalized from the API.
        """
        response = self.client.request("GET", "interfaces/overview/interfacesInfo")

        rows: list[dict[str, Any]] = []
        if isinstance(response, dict):
            raw_rows = response.get("rows")
            if isinstance(raw_rows, list):
                rows = [r for r in raw_rows if isinstance(r, dict)]

        return [_row_to_live_assignment(row) for row in rows if row.get("identifier")]

    # ------------------------------------------------------------------
    # Migration / export
    # ------------------------------------------------------------------

    def export_to_yaml(self) -> str:
        """Export the current interface assignments to InfraFoundry YAML.

        Produces a resource-centric YAML document where each row's
        ``identifier`` becomes both ``name`` (operator-facing) and the
        future-state binding key. ``ipv4``/``ipv6`` are emitted verbatim
        for forward-compat — the schema accepts them today even though
        the write path doesn't yet honor them.

        Returns:
            YAML string suitable for placement under
            ``envs/<env>/resources/`` or
            ``envs/<env>/opnsense/interface_assignments.yaml``.
        """
        live = self.list()
        resources = [
            {
                "provider": "opnsense",
                "type": "interface_assignments",
                "name": entry.identifier,
                "config": {
                    "device": entry.device,
                    "description": entry.description,
                    "enabled": True,
                    "ipv4": entry.ipv4,
                    "ipv6": entry.ipv6,
                },
            }
            for entry in live
        ]
        return yaml.safe_dump({"resources": resources}, sort_keys=False)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _row_to_live_assignment(row: dict[str, Any]) -> LiveInterfaceAssignment:
    """Normalize an ``interfacesInfo`` row into a ``LiveInterfaceAssignment``.

    The API returns ``mtu`` as a string in some versions and as a missing
    key in others; we coerce defensively. ``ipv4``/``ipv6`` are passed
    through as raw dicts.
    """
    identifier = str(row.get("identifier", ""))
    device = str(row.get("device", ""))
    description = str(row.get("description", "") or "")
    is_physical = bool(row.get("is_physical", False))
    macaddr = str(row.get("macaddr", "") or "")

    ipv4_raw = row.get("ipv4", {})
    ipv4: dict[str, Any] = ipv4_raw if isinstance(ipv4_raw, dict) else {}

    ipv6_raw = row.get("ipv6", {})
    ipv6: dict[str, Any] = ipv6_raw if isinstance(ipv6_raw, dict) else {}

    try:
        mtu = int(row.get("mtu", 0) or 0)
    except (TypeError, ValueError):
        mtu = 0

    return LiveInterfaceAssignment(
        identifier=identifier,
        device=device,
        description=description,
        is_physical=is_physical,
        ipv4=ipv4,
        ipv6=ipv6,
        macaddr=macaddr,
        mtu=mtu,
    )
