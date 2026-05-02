"""VLAN service for OPNsense direct-API operations (ADR-0014).

This service is the production version of the VLAN diff/apply engine
prototyped in ``tools/spikes/vlan_direct_api.py``. It manages VLANs by
identity ``(device, tag)`` — the operator-visible YAML ``name`` is for
references only, never used for diff matching.

The service uses the production ``OPNsenseClient`` wrapper at
``infrafoundry.providers.opnsense.api_client``. Calls go through the
``client.request("POST", "interfaces/vlan_settings/<command>", data=...)``
form for cross-service consistency with ``services/kea_dhcp.py``.

The ``lock`` field on a ``VlanConfig`` is a per-resource safety annotation
sourced from the YAML ``config.lock: true`` (ADR-0014 §6). Locked entries
are reported in ``Diff.locked`` and never appear in ``adds``/``updates``/
``deletes`` — useful for partial migrations where the operator wants
visibility of a resource (e.g., a WAN trunk) without IaC asserting authority
over it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import yaml

from infrafoundry.core.provider import ResourceConfig

from .base import BaseService

# Required fields on every VLAN config. Matches the OPNsense schema:
#   device       — parent NIC name (e.g. "igb0")
#   tag          — 802.1Q VLAN tag (1-4094)
#   description  — free-form label
#   priority     — 802.1p priority code point (0-7)
VLAN_REQUIRED_FIELDS: tuple[str, ...] = ("device", "tag", "description", "priority")


# ---------------------------------------------------------------------------
# Data classes (lifted from the VLAN spike — domain model is stable)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VlanConfig:
    """Desired-state VLAN configuration.

    The diff key ``(device, tag)`` is the natural identity of a VLAN on an
    OPNsense box; the OPNsense-assigned ``uuid`` is opaque and the resource
    ``name`` is operator-facing only.

    ``lock`` is a meta-property — when ``True``, the diff engine treats the
    entry as "observed but untouchable". The matching live resource is
    recorded in ``Diff.locked`` but never added, updated, or deleted.
    """

    name: str
    device: str
    tag: int
    description: str
    priority: int
    lock: bool = False

    @property
    def diff_key(self) -> tuple[str, int]:
        """Identity of this VLAN on the box: parent NIC + 802.1Q tag."""
        return (self.device, self.tag)

    def to_payload(self) -> dict[str, Any]:
        """Serialize to the dict shape OPNsense's ``addItem``/``setItem`` expect.

        The payload is wrapped in a top-level ``vlan`` key; OPNsense follows
        a consistent ``{<resource_key>: {<fields>}}`` envelope across modules.
        Numeric fields are stringified — the API rejects raw integers.
        """
        return {
            "vlan": {
                "if": self.device,
                "tag": str(self.tag),
                "descr": self.description,
                "pcp": str(self.priority),
            }
        }


@dataclass(frozen=True)
class LiveVlan:
    """A VLAN as currently configured on the OPNsense box."""

    uuid: str
    device: str
    tag: int
    description: str
    priority: int

    @property
    def diff_key(self) -> tuple[str, int]:
        """Identity of this VLAN on the box: parent NIC + 802.1Q tag."""
        return (self.device, self.tag)


@dataclass
class Diff:
    """Result of comparing desired YAML state to live OPNsense state."""

    adds: list[VlanConfig] = field(default_factory=list)
    updates: list[tuple[LiveVlan, VlanConfig]] = field(default_factory=list)
    deletes: list[LiveVlan] = field(default_factory=list)
    # Locked YAML entries paired with their live counterpart (or ``None`` if
    # declared-but-missing). Always reported in the plan output, never acted
    # on by ``apply``.
    locked: list[tuple[VlanConfig, LiveVlan | None]] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        """Return True if there are no add/update/delete operations to apply."""
        return not (self.adds or self.updates or self.deletes)


# ---------------------------------------------------------------------------
# Diff engine (lifted from the VLAN spike with no behavioral changes)
# ---------------------------------------------------------------------------


def compute_diff(
    desired: list[VlanConfig], current: list[LiveVlan], *, add_only: bool = False
) -> Diff:
    """Compare desired YAML state to live state, keyed by ``(device, tag)``.

    Args:
        desired: VLANs the operator wants to exist.
        current: VLANs the OPNsense box currently has.
        add_only: If ``True``, never emit deletes for live resources that
            don't appear in ``desired``. Adds and updates still happen
            normally. Useful for partial migrations.

    Returns:
        A ``Diff`` with adds/updates/deletes plus a ``locked`` list of
        observed-but-untouchable pairs. ``updates`` carries the live record
        alongside the desired record so the caller has the UUID.
    """
    desired_by_key: dict[tuple[str, int], VlanConfig] = {v.diff_key: v for v in desired}
    current_by_key: dict[tuple[str, int], LiveVlan] = {v.diff_key: v for v in current}
    locked_keys: set[tuple[str, int]] = {v.diff_key for v in desired if v.lock}

    adds: list[VlanConfig] = []
    updates: list[tuple[LiveVlan, VlanConfig]] = []
    deletes: list[LiveVlan] = []
    locked: list[tuple[VlanConfig, LiveVlan | None]] = []

    for key, want in desired_by_key.items():
        have = current_by_key.get(key)
        if want.lock:
            locked.append((want, have))
            continue
        if have is None:
            adds.append(want)
        elif (have.description, have.priority) != (want.description, want.priority):
            updates.append((have, want))

    if not add_only:
        for key, have in current_by_key.items():
            if key in locked_keys:
                # Already recorded above as locked; never emit a delete.
                continue
            if key not in desired_by_key:
                deletes.append(have)

    return Diff(adds=adds, updates=updates, deletes=deletes, locked=locked)


# ---------------------------------------------------------------------------
# Resource-to-domain conversion
# ---------------------------------------------------------------------------


def vlan_configs_from_resources(resources: list[ResourceConfig]) -> list[VlanConfig]:
    """Convert InfraFoundry ``ResourceConfig`` entries to ``VlanConfig`` instances.

    Args:
        resources: Resources from a ConfigManager load. Non-VLAN entries are
            ignored.

    Returns:
        Validated ``VlanConfig`` list; the same field-level validation that
        ``VLANValidator`` runs at plan time runs here too as a defensive
        second check.

    Raises:
        ValueError: If any VLAN entry is missing a required field, has an
            out-of-range value, or carries a non-bool ``lock``.
    """
    vlans: list[VlanConfig] = []
    for resource in resources:
        if resource.type != "vlans":
            continue

        config = resource.config
        if not isinstance(config, dict):
            raise ValueError(f"VLAN '{resource.name}' has non-dict config")

        missing = [f for f in VLAN_REQUIRED_FIELDS if f not in config]
        if missing:
            raise ValueError(
                f"VLAN '{resource.name}' missing required field(s): {', '.join(missing)}"
            )

        try:
            tag = int(config["tag"])
            priority = int(config["priority"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"VLAN '{resource.name}' has non-integer tag or priority") from exc

        if not 1 <= tag <= 4094:
            raise ValueError(f"VLAN '{resource.name}' tag {tag} out of range 1-4094")
        if not 0 <= priority <= 7:
            raise ValueError(f"VLAN '{resource.name}' priority {priority} out of range 0-7")

        device = config["device"]
        description = config["description"]
        if not isinstance(device, str) or not device:
            raise ValueError(f"VLAN '{resource.name}' missing string 'device'")
        if not isinstance(description, str):
            raise ValueError(f"VLAN '{resource.name}' description must be a string")

        # ``lock`` lives under ``config:`` per ADR-0014 §6 amendment.
        # Top-level lock would be silently dropped because ``ResourceConfig``
        # is a Pydantic BaseModel without ``extra="allow"``.
        lock_raw = config.get("lock", False)
        if not isinstance(lock_raw, bool):
            raise ValueError(f"VLAN '{resource.name}' lock must be a boolean (true/false)")

        vlans.append(
            VlanConfig(
                name=resource.name,
                device=device,
                tag=tag,
                description=description,
                priority=priority,
                lock=lock_raw,
            )
        )

    return vlans


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class VlanService(BaseService):
    """Service for OPNsense VLAN operations via direct API.

    Exposes the diff/apply primitives the ``VlanManager`` orchestrates. The
    service is environment-agnostic: it operates on the live OPNsense box
    bound to the ``OPNsenseClient`` it was constructed with.
    """

    # ------------------------------------------------------------------
    # API operations (CRUD + reconfigure)
    # ------------------------------------------------------------------

    def search(self) -> list[LiveVlan]:
        """Fetch the live VLAN list from OPNsense.

        Returns:
            ``LiveVlan`` instances normalized from the search rows.
        """
        # OPNsense's searchItem is a POST despite being a "search" verb.
        response = self.client.request("POST", "interfaces/vlan_settings/searchItem")

        rows: list[dict[str, Any]] = []
        if isinstance(response, dict):
            raw_rows = response.get("rows")
            if isinstance(raw_rows, list):
                rows = [r for r in raw_rows if isinstance(r, dict)]

        return [_row_to_live_vlan(row) for row in rows]

    def add(self, vlan: VlanConfig) -> dict[str, Any]:
        """Create a VLAN.

        Args:
            vlan: Desired-state VLAN configuration.

        Returns:
            API response dict (typically ``{"result": "saved", "uuid": ...}``).
        """
        return self.client.request(
            "POST",
            "interfaces/vlan_settings/addItem",
            data=vlan.to_payload(),
        )

    def update(self, uuid: str, vlan: VlanConfig) -> dict[str, Any]:
        """Update an existing VLAN by UUID.

        Args:
            uuid: OPNsense-assigned VLAN UUID.
            vlan: New desired-state configuration.

        Returns:
            API response dict.
        """
        return self.client.request(
            "POST",
            f"interfaces/vlan_settings/setItem/{uuid}",
            data=vlan.to_payload(),
        )

    def delete(self, uuid: str) -> dict[str, Any]:
        """Delete a VLAN by UUID.

        Args:
            uuid: OPNsense-assigned VLAN UUID.

        Returns:
            API response dict.
        """
        return self.client.request("POST", f"interfaces/vlan_settings/delItem/{uuid}")

    def reconfigure(self) -> dict[str, Any]:
        """Apply pending VLAN changes (commit staged config to running system).

        Must be called after add/update/delete operations to activate them.
        """
        return self.client.request("POST", "interfaces/vlan_settings/reconfigure")

    # ------------------------------------------------------------------
    # Diff + apply orchestration
    # ------------------------------------------------------------------

    def compute_diff(
        self,
        desired: list[VlanConfig],
        live: list[LiveVlan],
        *,
        add_only: bool = False,
    ) -> Diff:
        """Compute the add/update/delete diff between desired and live state.

        Thin wrapper over the module-level ``compute_diff`` for callers that
        prefer the service-method form.
        """
        return compute_diff(desired, live, add_only=add_only)

    def apply_diff(self, diff: Diff) -> dict[str, int]:
        """Dispatch the operations described by ``diff``, then reconfigure.

        Returns:
            Counts of operations actually performed:
            ``{"created": N, "updated": M, "deleted": K}``.
            Reconfigure is called once at the end if any mutation happened.
        """
        created = 0
        updated = 0
        deleted = 0

        for vlan in diff.adds:
            self.add(vlan)
            created += 1

        for live, want in diff.updates:
            self.update(live.uuid, want)
            updated += 1

        for live in diff.deletes:
            self.delete(live.uuid)
            deleted += 1

        if created or updated or deleted:
            self.reconfigure()

        return {"created": created, "updated": updated, "deleted": deleted}

    # ------------------------------------------------------------------
    # Migration / export
    # ------------------------------------------------------------------

    def export_to_yaml(self) -> str:
        """Export the current VLAN configuration to InfraFoundry YAML.

        Returns:
            YAML string containing ``provider/type/name/config`` entries
            suitable for inclusion in a resource-centric config file.
        """
        live = self.search()
        resources = [
            {
                "provider": "opnsense",
                "type": "vlans",
                "name": f"vlan-{v.device}-{v.tag}",
                "config": {
                    "device": v.device,
                    "tag": v.tag,
                    "description": v.description,
                    "priority": v.priority,
                },
            }
            for v in live
        ]
        return yaml.safe_dump({"resources": resources}, sort_keys=False)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _row_to_live_vlan(row: dict[str, Any]) -> LiveVlan:
    """Normalize a ``searchItem`` row into a ``LiveVlan``.

    The OPNsense API returns ``tag`` and ``pcp`` as strings; we coerce them
    to int and fall back to 0 on parse failure rather than crash.
    """
    uuid = str(row.get("uuid", ""))
    device = str(row.get("if", ""))
    try:
        tag = int(row.get("tag", 0))
    except (TypeError, ValueError):
        tag = 0
    try:
        priority = int(row.get("pcp", 0))
    except (TypeError, ValueError):
        priority = 0
    description = str(row.get("descr", ""))
    return LiveVlan(
        uuid=uuid,
        device=device,
        tag=tag,
        description=description,
        priority=priority,
    )
