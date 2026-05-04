"""Virtual-IP service for OPNsense direct-API operations (ADR-0014, #723).

Manages OPNsense virtual IPs (CARP, IP aliases, ProxyARP) via the
``interfaces/vip_settings/*`` controller. Identity is the natural-key
tuple ``(interface, mode, address, vhid)`` — including ``mode`` and
``vhid`` lets multiple CARP VIPs coexist on the same interface+address
(different vhids), and distinguishes ipalias vs CARP at the same IP.
``vhid`` is the empty string for non-CARP modes.

Endpoint surface (confirmed live on ``opnsense-a`` running ``26.1.6_2``,
2026-05-04 probe):

- ``POST interfaces/vip_settings/searchItem`` — list rows for the
  dataTable view. Response shape ``{"rows": [...], ...}``; rows expose
  flat ``interface`` (selected key) plus other fields.
- ``GET  interfaces/vip_settings/getItem/<uuid>`` — full record under
  ``{"vip": {...}}`` envelope, with ``interface`` and ``mode`` rendered
  as option dicts.
- ``POST interfaces/vip_settings/addItem`` — body envelope
  ``{"vip": {...}}``; returns ``{"result": "saved", "uuid": "..."}``.
- ``POST interfaces/vip_settings/setItem/<uuid>`` — same body envelope.
- ``POST interfaces/vip_settings/delItem/<uuid>`` — response
  ``{"result": "deleted"}``.
- ``POST interfaces/vip_settings/reconfigure`` — typed response
  ``{"status": "ok" | "failed"}``.

Field schema (probe-derived, recorded here so a follow-up doesn't need
to re-probe). All write fields are simple strings on the wire:

- Required (every mode): ``interface``, ``mode``, ``address``,
  ``network`` (CIDR mask, e.g. ``"24"``).
- Required (CARP only): ``password``, ``vhid``.
- Optional (CARP): ``advbase`` (default ``"1"``), ``advskew`` (default
  ``"0"``), ``peer`` (unicast IPv4 peer), ``peer6`` (unicast IPv6 peer),
  ``nosync`` (bool string).
- Optional (ipalias): ``gateway`` (gateway name), ``noexpand`` (bool
  string), ``nobind`` (bool string).
- ``descr`` (wire) ↔ ``description`` (YAML) — matches the rest of the
  provider's resources.

The mode discriminator is enforced by the validator at plan time;
the parser here keeps the schema invariants tight enough that the
manager / service can rely on the field types.

Identity contract recap:

- Two VIPs with the same ``(interface, mode, address, vhid)`` tuple are
  the same record by the diff engine. Updating any of those fields is
  a delete + add (the diff engine emits both); updating ``descr``,
  ``password``, or any other non-identity field is an in-place
  ``setItem`` (preserves UUID).
- Operator-facing YAML ``name`` is metadata only — used for cross-
  resource references and ``ResourceOutcome.address``-style addressing.
- ``lock: true`` is honored: locked entries appear in ``Diff.locked``
  and are never added, updated, or deleted.

Secrets:

- The CARP ``password`` field accepts either a plaintext value or a
  ``secret://env_secrets/<dotted/path>`` URI. The component manager
  resolves URIs via ``SecretResolver`` before handing the config to
  this service; the service is unaware of secrets.
- ``export_to_yaml`` (used by ``migrate``) redacts the password since
  OPNsense never returns the plaintext on read — the operator must
  re-supply the secret manually after migration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

import yaml

from infrafoundry.core.provider import ResourceConfig

from .base import BaseService

# Allowed values for the ``mode`` discriminator. ``ipalias`` (NOT
# ``alias``) — the issue body's draft was wrong; the live probe is
# authoritative.
VirtualIPMode = Literal["ipalias", "carp", "proxyarp"]
ALLOWED_MODES: tuple[VirtualIPMode, ...] = ("ipalias", "carp", "proxyarp")

# Controller base for all virtual-IP CRUD + reconfigure endpoints.
_VIP_BASE = "interfaces/vip_settings"

# Default values for optional CARP fields (per probe).
_DEFAULT_ADVBASE = "1"
_DEFAULT_ADVSKEW = "0"

# Placeholder substituted into exported YAML for CARP passwords —
# OPNsense never returns the plaintext on ``getItem``, so a migration
# round-trip can never reproduce the secret.
_PASSWORD_REDACTED_PLACEHOLDER = "secret://env_secrets/opnsense/carp_passwords/REPLACE_ME"  # nosec B105


# ---------------------------------------------------------------------------
# Domain model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VirtualIPConfig:
    """Desired-state virtual-IP configuration.

    The operator-facing YAML ``name`` is metadata only — used for
    ``ResourceOutcome`` addresses and cross-resource references — and
    never travels on the wire. The diff engine matches on the natural-
    key tuple ``(interface, mode, address, vhid)``.

    ``lock`` is a per-resource safety annotation (ADR-0014 §6) — locked
    entries appear in ``Diff.locked`` but are never added, updated, or
    deleted.

    Attributes:
        name: Operator-facing YAML name; metadata only.
        interface: OPNsense interface name (e.g. ``lan``, ``wan``,
            ``opt1``).
        mode: ``ipalias``, ``carp``, or ``proxyarp``.
        address: The IP address (IPv4 or IPv6).
        network: CIDR mask as a string (e.g. ``"24"`` for IPv4 /24,
            ``"64"`` for IPv6 /64).
        description: Operator-facing free-form description (mapped to
            ``descr`` on the wire).
        enabled: Whether the VIP is active.
        lock: Per-resource safety annotation (ADR-0014 §6).
        password: CARP password (plaintext after secret resolution).
            Empty for non-CARP modes.
        vhid: CARP virtual host ID. Empty for non-CARP modes.
        advbase: CARP advertisement base (default ``"1"``).
        advskew: CARP advertisement skew (default ``"0"``).
        peer: CARP unicast peer (IPv4). Empty for default multicast.
        peer6: CARP unicast peer (IPv6). Empty for default multicast.
        nosync: CARP — skip xmlrpc sync to peer.
        gateway: ipalias gateway name. Empty if none.
        noexpand: ipalias — disable subnet expansion.
        nobind: ipalias — do not bind to this VIP.
    """

    name: str
    interface: str
    mode: VirtualIPMode
    address: str
    network: str
    description: str = ""
    enabled: bool = True
    lock: bool = False

    # CARP-only fields
    password: str = ""
    vhid: str = ""
    advbase: str = _DEFAULT_ADVBASE
    advskew: str = _DEFAULT_ADVSKEW
    peer: str = ""
    peer6: str = ""
    nosync: bool = False

    # ipalias-only fields
    gateway: str = ""
    noexpand: bool = False
    nobind: bool = False

    @property
    def diff_key(self) -> tuple[str, str, str, str]:
        """Identity tuple: ``(interface, mode, address, vhid)``."""
        return (self.interface, self.mode, self.address, self.vhid)

    def to_payload(self) -> dict[str, Any]:
        """Serialize to the ``addItem``/``setItem`` envelope.

        Returns:
            ``{"vip": {<fields>}}``. Booleans are stringified to
            ``"0"``/``"1"``; ``description`` maps to ``descr``. The
            operator-facing ``name`` is intentionally NOT sent.
        """
        payload: dict[str, Any] = {
            "interface": self.interface,
            "mode": self.mode,
            "address": self.address,
            "network": self.network,
            "descr": self.description,
        }

        if self.mode == "carp":
            payload["password"] = self.password
            payload["vhid"] = self.vhid
            payload["advbase"] = self.advbase
            payload["advskew"] = self.advskew
            payload["peer"] = self.peer
            payload["peer6"] = self.peer6
            payload["nosync"] = _bool_str(self.nosync)
        elif self.mode == "ipalias":
            payload["gateway"] = self.gateway
            payload["noexpand"] = _bool_str(self.noexpand)
            payload["nobind"] = _bool_str(self.nobind)

        # ``proxyarp`` carries no extra fields.
        return {"vip": payload}


@dataclass(frozen=True)
class LiveVirtualIP:
    """A virtual IP as currently configured on the OPNsense box.

    ``raw`` is the ``searchItem`` row, which exposes flat ``interface``,
    ``mode``, ``address``, ``network``, ``vhid`` columns plus the rest.
    The ``getItem`` envelope is read separately during ``export_to_yaml``
    to recover option-dict-rendered fields.

    Attributes:
        uuid: OPNsense-assigned UUID.
        interface: Interface name.
        mode: ``ipalias`` / ``carp`` / ``proxyarp``.
        address: The IP address.
        vhid: CARP vhid (empty string for non-CARP modes).
        raw: Full original ``searchItem`` row for field comparison
            during update detection.
    """

    uuid: str
    interface: str
    mode: str
    address: str
    vhid: str
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def diff_key(self) -> tuple[str, str, str, str]:
        """Identity tuple: ``(interface, mode, address, vhid)``."""
        return (self.interface, self.mode, self.address, self.vhid)


@dataclass
class Diff:
    """Result of comparing desired YAML state to live OPNsense state.

    Mirrors ``services.static_route.Diff`` and
    ``services.unbound_forward.Diff``: adds / updates / deletes /
    locked, plus ``is_empty``. Updates carry the live record alongside
    the desired record so the caller has the UUID. Locked entries pair
    desired YAML with their (possibly missing) live record.

    Note that changing any field in the identity tuple (``interface``,
    ``mode``, ``address``, or ``vhid``) on a YAML resource produces a
    delete + add, not an update.
    """

    adds: list[VirtualIPConfig] = field(default_factory=list)
    updates: list[tuple[LiveVirtualIP, VirtualIPConfig]] = field(default_factory=list)
    deletes: list[LiveVirtualIP] = field(default_factory=list)
    locked: list[tuple[VirtualIPConfig, LiveVirtualIP | None]] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        """Return True if there are no add/update/delete operations to apply."""
        return not (self.adds or self.updates or self.deletes)


# ---------------------------------------------------------------------------
# Diff engine
# ---------------------------------------------------------------------------


def compute_diff(
    desired: list[VirtualIPConfig],
    current: list[LiveVirtualIP],
    *,
    add_only: bool = False,
) -> Diff:
    """Compare desired YAML state to live state by ``(interface, mode, address, vhid)``.

    Args:
        desired: VIPs the operator wants to exist.
        current: VIPs currently on the box.
        add_only: If True, never emit deletes for live VIPs that don't
            appear in ``desired``. Adds and updates still happen.

    Returns:
        ``Diff`` with adds / updates / deletes plus locked entries.
    """
    desired_by_key: dict[tuple[str, str, str, str], VirtualIPConfig] = {
        v.diff_key: v for v in desired
    }
    current_by_key: dict[tuple[str, str, str, str], LiveVirtualIP] = {
        v.diff_key: v for v in current
    }
    locked_keys: set[tuple[str, str, str, str]] = {v.diff_key for v in desired if v.lock}

    adds: list[VirtualIPConfig] = []
    updates: list[tuple[LiveVirtualIP, VirtualIPConfig]] = []
    deletes: list[LiveVirtualIP] = []
    locked: list[tuple[VirtualIPConfig, LiveVirtualIP | None]] = []

    for key, want in desired_by_key.items():
        have = current_by_key.get(key)
        if want.lock:
            locked.append((want, have))
            continue
        if have is None:
            adds.append(want)
        elif _needs_update(have, want):
            updates.append((have, want))

    if not add_only:
        for key, have in current_by_key.items():
            if key in locked_keys:
                continue
            if key not in desired_by_key:
                deletes.append(have)

    return Diff(adds=adds, updates=updates, deletes=deletes, locked=locked)


def _needs_update(have: LiveVirtualIP, want: VirtualIPConfig) -> bool:
    """Return True if the live row's fields differ from the desired payload.

    Compares the inner ``vip`` payload from ``want.to_payload()`` against
    the corresponding fields on ``have.raw``. ``password`` is always
    excluded from this comparison: OPNsense never returns the plaintext
    on read, so any non-empty ``want.password`` would otherwise force a
    spurious update on every run. Operators rotate CARP passwords by
    supplying a new value alongside another field change (or by
    explicitly destroying + re-creating the VIP).
    """
    payload = want.to_payload()["vip"]
    for key, want_value in payload.items():
        if key == "password":
            continue
        have_value = _normalize_field(have.raw.get(key))
        if str(want_value) != have_value:
            return True
    return False


def _normalize_field(value: Any) -> str:
    """Collapse an OPNsense field value to a comparable string.

    Booleans (returned from ``searchItem``'s post-processed view) are
    serialized as ``"1"`` / ``"0"`` to match what we'd send. Select
    fields returned as option dicts (from ``getItem``) extract the
    selected key. Plain scalars are stringified verbatim. ``None``
    becomes ``""``.
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, dict):
        for option_key, option_value in value.items():
            if isinstance(option_value, dict) and option_value.get("selected"):
                return str(option_key)
        return ""
    return str(value)


# ---------------------------------------------------------------------------
# Resource-to-domain conversion
# ---------------------------------------------------------------------------


def virtual_ip_configs_from_resources(
    resources: list[ResourceConfig],
) -> list[VirtualIPConfig]:
    """Convert ``ResourceConfig`` entries to ``VirtualIPConfig`` instances.

    Validation here is intentionally minimal — the validator handles
    cross-resource references (interface ref, secret URI shape) and
    operator-friendly error messages; this parser only enforces type
    sanity so manager code can rely on field invariants.

    Args:
        resources: All provider resources from a ConfigManager load.
            Non-``virtual_ips`` entries are silently skipped.

    Returns:
        Validated ``VirtualIPConfig`` list.

    Raises:
        ValueError: If an entry has a non-dict config, missing required
            fields, an invalid ``mode``, or non-bool booleans / non-
            string fields.
    """
    configs: list[VirtualIPConfig] = []
    for resource in resources:
        if resource.type != "virtual_ips":
            continue

        config = resource.config
        if not isinstance(config, dict):
            raise ValueError(f"virtual_ip '{resource.name}' has non-dict config")

        mode_raw = config.get("mode", "ipalias")
        if not isinstance(mode_raw, str) or mode_raw not in ALLOWED_MODES:
            raise ValueError(
                f"virtual_ip '{resource.name}' mode {mode_raw!r} must be one of {ALLOWED_MODES}"
            )
        mode: VirtualIPMode = mode_raw

        interface = config.get("interface", "")
        if not isinstance(interface, str) or not interface:
            raise ValueError(
                f"virtual_ip '{resource.name}' requires a non-empty string 'interface'"
            )

        address = config.get("address", "")
        if not isinstance(address, str) or not address:
            raise ValueError(f"virtual_ip '{resource.name}' requires a non-empty string 'address'")

        network = _coerce_network(config.get("network"), resource.name)

        description = config.get("description", "")
        if not isinstance(description, str):
            raise ValueError(f"virtual_ip '{resource.name}' description must be a string")

        enabled = _require_bool(config, "enabled", default=True, resource_name=resource.name)
        lock = _require_bool(config, "lock", default=False, resource_name=resource.name)

        # Per-mode field handling.
        password = ""  # nosec B105
        vhid = ""
        advbase = _DEFAULT_ADVBASE
        advskew = _DEFAULT_ADVSKEW
        peer = ""
        peer6 = ""
        nosync = False
        gateway = ""
        noexpand = False
        nobind = False

        if mode == "carp":
            password = _coerce_string(config.get("password", ""), "password", resource.name)
            vhid = _coerce_vhid(config.get("vhid"), resource.name)
            advbase = _coerce_string(
                config.get("advbase", _DEFAULT_ADVBASE), "advbase", resource.name
            )
            advskew = _coerce_string(
                config.get("advskew", _DEFAULT_ADVSKEW), "advskew", resource.name
            )
            peer = _coerce_string(config.get("peer", ""), "peer", resource.name)
            peer6 = _coerce_string(config.get("peer6", ""), "peer6", resource.name)
            nosync = _require_bool(config, "nosync", default=False, resource_name=resource.name)
        elif mode == "ipalias":
            gateway = _coerce_string(config.get("gateway", ""), "gateway", resource.name)
            noexpand = _require_bool(config, "noexpand", default=False, resource_name=resource.name)
            nobind = _require_bool(config, "nobind", default=False, resource_name=resource.name)
        # ``proxyarp`` carries no extra fields.

        configs.append(
            VirtualIPConfig(
                name=resource.name,
                interface=interface,
                mode=mode,
                address=address,
                network=network,
                description=description,
                enabled=enabled,
                lock=lock,
                password=password,
                vhid=vhid,
                advbase=advbase,
                advskew=advskew,
                peer=peer,
                peer6=peer6,
                nosync=nosync,
                gateway=gateway,
                noexpand=noexpand,
                nobind=nobind,
            )
        )

    return configs


def _require_bool(
    config: dict[str, Any], field_name: str, *, default: bool, resource_name: str
) -> bool:
    value = config.get(field_name, default)
    if not isinstance(value, bool):
        raise ValueError(
            f"virtual_ip '{resource_name}' {field_name} must be a boolean (true/false), "
            f"got {type(value).__name__}"
        )
    return value


def _coerce_string(value: Any, field_name: str, resource_name: str) -> str:
    """Accept str (passthrough) or int (stringified). Reject other types."""
    if isinstance(value, str):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    raise ValueError(
        f"virtual_ip '{resource_name}' {field_name} must be a string or integer, "
        f"got {type(value).__name__}"
    )


def _coerce_network(value: Any, resource_name: str) -> str:
    """Coerce ``network`` (CIDR mask) — accept str or int; reject empty."""
    if value is None:
        raise ValueError(f"virtual_ip '{resource_name}' requires a non-empty 'network' (CIDR mask)")
    if isinstance(value, str):
        if not value:
            raise ValueError(
                f"virtual_ip '{resource_name}' requires a non-empty 'network' (CIDR mask)"
            )
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    raise ValueError(
        f"virtual_ip '{resource_name}' network must be a string or integer, "
        f"got {type(value).__name__}"
    )


def _coerce_vhid(value: Any, resource_name: str) -> str:
    """Coerce ``vhid`` for CARP — accept str or int; reject missing."""
    if value is None:
        raise ValueError(f"virtual_ip '{resource_name}' (carp) requires 'vhid'")
    if isinstance(value, str):
        if not value:
            raise ValueError(f"virtual_ip '{resource_name}' (carp) requires non-empty 'vhid'")
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    raise ValueError(
        f"virtual_ip '{resource_name}' vhid must be a string or integer, got {type(value).__name__}"
    )


def _bool_str(value: bool) -> str:
    """Convert a Python bool to OPNsense's ``"0"``/``"1"`` representation."""
    return "1" if value else "0"


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class VirtualIPService(BaseService):
    """Service for OPNsense virtual-IP operations via direct API.

    Single controller, single endpoint family. Identity is the natural-
    key ``(interface, mode, address, vhid)`` tuple; the diff engine
    matches operator YAML directly to live records by tuple.
    """

    # ------------------------------------------------------------------
    # API operations (CRUD + reconfigure)
    # ------------------------------------------------------------------

    def search(self) -> list[LiveVirtualIP]:
        """Fetch the live virtual-IP list.

        Returns:
            ``LiveVirtualIP`` instances normalized from the search rows.
        """
        response = self.client.request("POST", f"{_VIP_BASE}/searchItem")

        rows: list[dict[str, Any]] = []
        if isinstance(response, dict):
            raw_rows = response.get("rows")
            if isinstance(raw_rows, list):
                rows = [r for r in raw_rows if isinstance(r, dict)]

        return [_row_to_live(row) for row in rows]

    def get(self, uuid: str) -> dict[str, Any]:
        """Fetch the full virtual-IP record by UUID.

        Used by ``export_to_yaml`` to read the option-dict-rendered
        fields that ``searchItem`` doesn't expose. Returns the raw
        envelope ``{"vip": {...}}``.
        """
        return self.client.request("GET", f"{_VIP_BASE}/getItem/{uuid}")

    def add(self, vip: VirtualIPConfig) -> dict[str, Any]:
        """Create a virtual IP.

        Args:
            vip: Desired-state virtual-IP configuration.

        Returns:
            API response dict (typically ``{"result": "saved", "uuid": ...}``).
        """
        return self.client.request(
            "POST",
            f"{_VIP_BASE}/addItem",
            data=vip.to_payload(),
        )

    def update(self, uuid: str, vip: VirtualIPConfig) -> dict[str, Any]:
        """Update an existing virtual IP by UUID.

        Args:
            uuid: OPNsense-assigned virtual-IP UUID.
            vip: New desired-state configuration.

        Returns:
            API response dict.
        """
        return self.client.request(
            "POST",
            f"{_VIP_BASE}/setItem/{uuid}",
            data=vip.to_payload(),
        )

    def delete(self, uuid: str) -> dict[str, Any]:
        """Delete a virtual IP by UUID.

        Args:
            uuid: OPNsense-assigned virtual-IP UUID.

        Returns:
            API response dict (typically ``{"result": "deleted"}``).
        """
        return self.client.request("POST", f"{_VIP_BASE}/delItem/{uuid}")

    def reconfigure(self) -> dict[str, Any]:
        """Apply pending virtual-IP changes (commit staged config).

        Must be called after add/update/delete operations to activate
        them. Response shape per the OpenAPI spec is
        ``{"status": "ok" | "failed"}``.
        """
        return self.client.request("POST", f"{_VIP_BASE}/reconfigure")

    # ------------------------------------------------------------------
    # Diff + apply orchestration
    # ------------------------------------------------------------------

    def compute_diff(
        self,
        desired: list[VirtualIPConfig],
        live: list[LiveVirtualIP],
        *,
        add_only: bool = False,
    ) -> Diff:
        """Compute the add/update/delete diff between desired and live state.

        Thin wrapper over the module-level ``compute_diff`` for callers
        that prefer the service-method form.
        """
        return compute_diff(desired, live, add_only=add_only)

    def apply_diff(self, diff: Diff) -> dict[str, int]:
        """Dispatch the operations described by ``diff``, then reconfigure.

        Returns:
            Counts of operations actually performed:
            ``{"created": N, "updated": M, "deleted": K}``.
            ``reconfigure`` is called once at the end if any mutation
            happened.
        """
        created = 0
        updated = 0
        deleted = 0

        for vip in diff.adds:
            self.add(vip)
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
        """Export the current virtual-IP configuration to InfraFoundry YAML.

        For each live VIP we issue a ``getItem/<uuid>`` to capture the
        option-dict-rendered ``interface`` / ``mode`` fields at full
        fidelity. Operator-facing ``name`` is synthesized from
        ``(interface, mode, address, vhid)`` — the operator can rename
        freely after import; identity is the tuple, not the name.

        CARP passwords are NEVER returned by OPNsense's read endpoints,
        so the exported config emits a placeholder ``secret://``
        URI for CARP entries; the operator must populate the secret
        manually before re-applying.

        Returns:
            YAML string with ``provider/type/name/config`` entries.
        """
        live = self.search()
        resources = [
            {
                "provider": "opnsense",
                "type": "virtual_ips",
                "name": _synthesize_name(vip),
                "config": _live_to_export_config(self.get(vip.uuid)),
            }
            for vip in live
        ]
        return yaml.safe_dump({"resources": resources}, sort_keys=False)


# ---------------------------------------------------------------------------
# Internal helpers (row parsing / export)
# ---------------------------------------------------------------------------


def _row_to_live(row: dict[str, Any]) -> LiveVirtualIP:
    """Normalize a ``searchItem`` row into a ``LiveVirtualIP``."""
    uuid = str(row.get("uuid", ""))
    interface = _normalize_field(row.get("interface"))
    mode = _normalize_field(row.get("mode"))
    address = _normalize_field(row.get("address"))
    vhid = _normalize_field(row.get("vhid"))
    return LiveVirtualIP(
        uuid=uuid,
        interface=interface,
        mode=mode,
        address=address,
        vhid=vhid,
        raw=row,
    )


def _synthesize_name(vip: LiveVirtualIP) -> str:
    """Build a YAML-friendly synthetic name from a ``LiveVirtualIP``.

    Replaces characters that don't survive YAML keys / kebab-case
    conventions (``:``, ``.``, ``/``) with hyphens. The operator can
    rename after import; identity is the tuple, not the name.

    For CARP entries the ``vhid`` is appended so two CARP VIPs at the
    same address+interface can be distinguished. Non-CARP entries omit
    the vhid suffix (it's always ``""``).
    """
    address_part = vip.address.replace(":", "-").replace(".", "-").replace("/", "-")
    base = f"vip-{vip.mode}-{vip.interface}-{address_part}"
    if vip.mode == "carp" and vip.vhid:
        base = f"{base}-vhid{vip.vhid}"
    return base.lower()


def _live_to_export_config(get_response: dict[str, Any]) -> dict[str, Any]:
    """Build a YAML-friendly config dict from a ``getItem`` envelope.

    Reads option-dict ``interface`` and ``mode`` via ``_normalize_field``
    to recover the selected keys. Booleans are decoded from the
    ``"0"``/``"1"`` strings that OPNsense returns. CARP passwords are
    never returned by OPNsense — emit a placeholder ``secret://`` URI
    so the operator can populate the real secret before re-applying.
    """
    item = get_response.get("vip", {}) if isinstance(get_response, dict) else {}
    mode = _normalize_field(item.get("mode")) or "ipalias"

    config: dict[str, Any] = {
        "mode": mode,
        "interface": _normalize_field(item.get("interface")),
        "address": _normalize_field(item.get("address")),
        "network": _normalize_field(item.get("network")),
        "description": _normalize_field(item.get("descr")),
        "enabled": True,
    }

    if mode == "carp":
        config["vhid"] = _normalize_field(item.get("vhid"))
        config["password"] = _PASSWORD_REDACTED_PLACEHOLDER
        config["advbase"] = _normalize_field(item.get("advbase")) or _DEFAULT_ADVBASE
        config["advskew"] = _normalize_field(item.get("advskew")) or _DEFAULT_ADVSKEW
        config["peer"] = _normalize_field(item.get("peer"))
        config["peer6"] = _normalize_field(item.get("peer6"))
        config["nosync"] = _normalize_field(item.get("nosync")) == "1"
    elif mode == "ipalias":
        config["gateway"] = _normalize_field(item.get("gateway"))
        config["noexpand"] = _normalize_field(item.get("noexpand")) == "1"
        config["nobind"] = _normalize_field(item.get("nobind")) == "1"
    # ``proxyarp`` has no extra fields.

    return config
