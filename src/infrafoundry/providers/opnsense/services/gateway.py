"""Gateway service for OPNsense direct-API operations (ADR-0014, #721).

Manages OPNsense routing gateways via the ``routing/settings/*Gateway``
controller. Identity is the natural key ``name`` — OPNsense enforces
uniqueness across all gateways, so the operator-facing YAML ``name`` maps
1:1 to the live ``name`` field. No description-suffix tag, no
``infrafoundry`` category bootstrap (gateways have no categories).

Endpoint surface (confirmed live on ``opnsense-a`` running ``26.1.6_2``,
2026-05-03 probe; corroborated by the bundled ``opnsense_openapi==0.4.0``
spec for 26.1.6):

- ``POST routing/settings/searchGateway`` — list rows for the dataTable view
- ``GET  routing/settings/getGateway/<uuid>`` — full record under
  ``{"gateway_item": {...}}`` envelope, with select fields rendered as
  option dicts (``{<key>: {"value": "...", "selected": 0|1}, ...}``)
- ``POST routing/settings/addGateway`` — body envelope ``{"gateway_item": {...}}``;
  response ``{"result": "saved", "uuid": "..."}``
- ``POST routing/settings/setGateway/<uuid>`` — same body envelope as add
- ``POST routing/settings/delGateway/<uuid>`` — response ``{"result": "deleted"}``
- ``POST routing/settings/reconfigure`` — typed response ``{"status": "ok"|"failed"}``

Field schema (probe-derived, recorded here so a follow-up doesn't need to
re-probe):

- Required: ``name``, ``interface``, ``ipprotocol`` (``inet`` | ``inet6``),
  ``gateway`` (next-hop IP or empty for "dynamic")
- Booleans serialized as ``"0"``/``"1"`` strings: ``disabled``, ``defaultgw``,
  ``fargw``, ``monitor_disable``, ``monitor_noroute``, ``monitor_killstates``,
  ``force_down``
- Strings: ``descr``, ``monitor`` (IP literal / hostname / empty)
- Stringified ints: ``priority`` (1-255), ``weight`` (1+),
  ``monitor_killstates_priority`` (0-255)
- Optional monitoring tunables (left empty by default to inherit OPNsense
  defaults): ``latencylow``, ``latencyhigh``, ``losslow``, ``losshigh``,
  ``interval``, ``time_period``, ``loss_interval``, ``data_length``

Dynamic / virtual gateways (e.g., ``WAN_DHCP``, ``WAN_DHCP6`` — those
synthesized by OPNsense from DHCP-acquired interface state) appear in
``searchGateway`` rows with ``dynamic: true`` and ``virtual: true`` and
their ``uuid`` is a synthetic string equal to the gateway name (not a
real UUID). They cannot be modified via ``addGateway``/``setGateway``/
``delGateway`` — they're recreated from interface state on reconfigure.
``LiveGateway.is_managed`` filters them out of the diff entirely (treated
the same as "not in YAML, not eligible for delete"). The operator should
not list dynamic gateways in YAML; the validator enforces this if the
``name`` collides with a live dynamic gateway.

The operator-facing YAML uses ``enabled: bool`` (matches the rest of the
provider's resources); on serialization that's flipped to OPNsense's
``disabled`` field. Same applies to ``description`` (YAML) → ``descr`` (API).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from infrafoundry.core.provider import ResourceConfig

from ._nested_emit import emit_nested_list_yaml
from .base import BaseService

# Allowed values for the ``ipprotocol`` discriminator.
GatewayProtocol = Literal["inet", "inet6"]
ALLOWED_PROTOCOLS: tuple[GatewayProtocol, ...] = ("inet", "inet6")

# Controller base for all gateway CRUD + reconfigure endpoints.
_GATEWAY_BASE = "routing/settings"

# OPNsense schema defaults — mirror the GUI's "Gateways: Add" form so
# operator-omitted fields land in the same place an interactive add would.
DEFAULT_PRIORITY = 254
DEFAULT_WEIGHT = 1


# ---------------------------------------------------------------------------
# Domain model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GatewayConfig:
    """Desired-state gateway configuration.

    The operator-facing YAML ``name`` is the diff key. OPNsense enforces
    uniqueness on ``name`` server-side, so name collisions raise at
    apply time (not at diff time).

    ``lock`` is a per-resource safety annotation (ADR-0014 §6) — locked
    entries appear in ``Diff.locked`` but are never added, updated, or
    deleted. ``ipaddr`` is operator-facing only: the literal ``"dynamic"``
    suppresses the ``gateway`` IP requirement (the box derives it from
    the interface), while any other value is a redundant convenience that
    must equal ``gateway``. The validator enforces the relationship; the
    service ignores ``ipaddr`` at serialization (only ``gateway`` is sent).

    Attributes:
        name: Operator-facing YAML name; the diff key.
        enabled: Whether the gateway is active. Inverted to ``disabled``
            on the wire.
        interface: Logical interface key (``lan``, ``wan``, ``opt1``, ...)
            or kebab name from a managed ``interface_assignment``.
        protocol: ``"inet"`` or ``"inet6"``.
        ipaddr: Operator-facing literal — ``"dynamic"`` or an IP. Not sent
            on the wire; validator-only.
        gateway: Next-hop IP. May be empty when ``ipaddr == "dynamic"``.
        defaultgw: Whether this is the default gateway for its protocol.
        monitor: Optional monitor address (IP / hostname).
        monitor_disable: Suppress monitoring entirely.
        monitor_noroute: Don't add a route for the monitor address.
        force_down: Force-mark the gateway down.
        fargw: Far-side gateway (out-of-subnet) flag.
        priority: 1-255 (lower = higher precedence).
        weight: ≥ 1 (load-balance ratio).
        description: Operator-facing free-form description (mapped to
            ``descr`` on the wire).
        lock: Per-resource safety annotation (ADR-0014 §6).
    """

    name: str
    interface: str
    protocol: GatewayProtocol
    gateway: str
    enabled: bool = True
    ipaddr: str = ""
    defaultgw: bool = False
    monitor: str = ""
    monitor_disable: bool = False
    monitor_noroute: bool = False
    force_down: bool = False
    fargw: bool = False
    priority: int = DEFAULT_PRIORITY
    weight: int = DEFAULT_WEIGHT
    description: str = ""
    lock: bool = False

    @property
    def diff_key(self) -> str:
        """Identity of this gateway: its server-unique ``name``."""
        return self.name

    def to_payload(self) -> dict[str, Any]:
        """Serialize to the ``addGateway``/``setGateway`` envelope.

        Returns:
            ``{"gateway_item": {<fields>}}``. Booleans are stringified to
            ``"0"``/``"1"``; ``enabled`` is inverted to ``disabled``;
            ``description`` maps to ``descr``. ``ipaddr`` is intentionally
            NOT sent — the validator enforces the relationship between
            ``ipaddr`` and ``gateway`` and only ``gateway`` is on the wire.
        """
        return {
            "gateway_item": {
                "name": self.name,
                "disabled": _bool_str(not self.enabled),
                "interface": self.interface,
                "ipprotocol": self.protocol,
                "gateway": self.gateway,
                "defaultgw": _bool_str(self.defaultgw),
                "fargw": _bool_str(self.fargw),
                "monitor_disable": _bool_str(self.monitor_disable),
                "monitor_noroute": _bool_str(self.monitor_noroute),
                "monitor": self.monitor,
                "force_down": _bool_str(self.force_down),
                "priority": str(self.priority),
                "weight": str(self.weight),
                "descr": self.description,
            }
        }


@dataclass(frozen=True)
class LiveGateway:
    """A gateway as currently configured on the OPNsense box.

    ``is_managed`` is False for dynamic / virtual gateways — those are
    synthesized from interface DHCP state and cannot be added, updated,
    or deleted via the gateway controller. The diff engine filters them
    out entirely.

    Attributes:
        uuid: OPNsense-assigned UUID (or the synthetic ``name`` for
            dynamic gateways).
        name: The gateway's server-unique name; the diff key.
        is_managed: True when the gateway is operator-creatable (i.e.,
            not a synthesized dynamic / virtual gateway).
        raw: Full original ``searchGateway`` row for field comparison
            during update detection.
    """

    uuid: str
    name: str
    is_managed: bool
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def diff_key(self) -> str:
        """Identity of this gateway: its server-unique ``name``."""
        return self.name


@dataclass
class Diff:
    """Result of comparing desired YAML state to live OPNsense state.

    Mirrors ``services.vlan.Diff`` and ``services.nat_rule.Diff``: adds /
    updates / deletes / locked, plus ``is_empty``. Updates carry the live
    record alongside the desired record so the caller has the UUID. Locked
    entries pair desired YAML with their (possibly missing) live record.
    """

    adds: list[GatewayConfig] = field(default_factory=list)
    updates: list[tuple[LiveGateway, GatewayConfig]] = field(default_factory=list)
    deletes: list[LiveGateway] = field(default_factory=list)
    locked: list[tuple[GatewayConfig, LiveGateway | None]] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        """Return True if there are no add/update/delete operations to apply."""
        return not (self.adds or self.updates or self.deletes)


# ---------------------------------------------------------------------------
# Diff engine
# ---------------------------------------------------------------------------


def compute_diff(
    desired: list[GatewayConfig],
    current: list[LiveGateway],
    *,
    add_only: bool = False,
) -> Diff:
    """Compare desired YAML state to live state, keyed by ``name``.

    Dynamic / virtual gateways (``LiveGateway.is_managed == False``) are
    silently ignored: not deleted, not updated, never reported. They are
    considered "out of band" and the operator must not list them in YAML.

    Args:
        desired: Gateways the operator wants to exist.
        current: Gateways currently on the box (managed + dynamic).
        add_only: If True, never emit deletes for managed live gateways
            that don't appear in ``desired``. Adds and updates still happen.

    Returns:
        ``Diff`` with adds / updates / deletes plus locked entries.
    """
    desired_by_key: dict[str, GatewayConfig] = {g.diff_key: g for g in desired}
    # Filter out dynamic gateways entirely.
    current_by_key: dict[str, LiveGateway] = {g.diff_key: g for g in current if g.is_managed}
    locked_keys: set[str] = {g.diff_key for g in desired if g.lock}

    adds: list[GatewayConfig] = []
    updates: list[tuple[LiveGateway, GatewayConfig]] = []
    deletes: list[LiveGateway] = []
    locked: list[tuple[GatewayConfig, LiveGateway | None]] = []

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


def _needs_update(have: LiveGateway, want: GatewayConfig) -> bool:
    """Return True if the live row's fields differ from the desired payload.

    Compares the inner ``gateway_item`` payload from ``want.to_payload()``
    against the corresponding fields on ``have.raw``. Live select fields
    (``interface``, ``ipprotocol``) come back as flat strings from
    ``searchGateway`` and as option dicts from ``getGateway``; this comparison
    only sees the ``searchGateway`` form, so ``_normalize_field`` is mostly
    pass-through, but it keeps update detection robust if the API surface
    changes.
    """
    payload = want.to_payload()["gateway_item"]
    for key, want_value in payload.items():
        have_value = _normalize_field(have.raw.get(key))
        if str(want_value) != have_value:
            return True
    return False


def _normalize_field(value: Any) -> str:
    """Collapse an OPNsense field value to a comparable string.

    Booleans (returned from ``searchGateway``'s post-processed view) are
    serialized as ``"1"`` / ``"0"`` to match what we'd send. Select fields
    returned as option dicts (from ``getGateway``) extract the selected
    key. Plain scalars are stringified verbatim. ``None`` becomes ``""``.
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


def gateway_configs_from_resources(
    resources: list[ResourceConfig],
) -> list[GatewayConfig]:
    """Convert ``ResourceConfig`` entries to ``GatewayConfig`` instances.

    Validation here is intentionally minimal — the validator handles
    cross-resource references and operator-friendly error messages; this
    parser only enforces type sanity so manager code can rely on field
    invariants.

    Args:
        resources: All provider resources from a ConfigManager load.
            Non-``gateways`` entries are silently skipped.

    Returns:
        Validated ``GatewayConfig`` list.

    Raises:
        ValueError: If an entry has a non-dict config, missing/invalid
            ``protocol``, missing required fields, or non-bool booleans /
            non-int ``priority``/``weight``.
    """
    configs: list[GatewayConfig] = []
    for resource in resources:
        if resource.type != "routing.gateways":
            continue

        config = resource.config
        if not isinstance(config, dict):
            raise ValueError(f"gateway '{resource.name}' has non-dict config")

        protocol_raw = config.get("protocol")
        if protocol_raw not in ALLOWED_PROTOCOLS:
            raise ValueError(
                f"gateway '{resource.name}' protocol must be one of "
                f"{ALLOWED_PROTOCOLS}, got {protocol_raw!r}"
            )
        protocol: GatewayProtocol = protocol_raw

        interface = config.get("interface", "")
        if not isinstance(interface, str) or not interface:
            raise ValueError(f"gateway '{resource.name}' requires a non-empty string 'interface'")

        ipaddr = config.get("ipaddr", "")
        if not isinstance(ipaddr, str):
            raise ValueError(f"gateway '{resource.name}' ipaddr must be a string")

        gateway_field = config.get("gateway", "")
        if not isinstance(gateway_field, str):
            raise ValueError(f"gateway '{resource.name}' gateway must be a string")
        if ipaddr != "dynamic" and not gateway_field:
            raise ValueError(
                f"gateway '{resource.name}' requires a non-empty 'gateway' "
                f"unless ipaddr is 'dynamic'"
            )

        description = config.get("description", "")
        if not isinstance(description, str):
            raise ValueError(f"gateway '{resource.name}' description must be a string")

        monitor = config.get("monitor", "")
        if not isinstance(monitor, str):
            raise ValueError(f"gateway '{resource.name}' monitor must be a string")

        priority_raw = config.get("priority", DEFAULT_PRIORITY)
        try:
            priority = int(priority_raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"gateway '{resource.name}' priority must be an integer, got {priority_raw!r}"
            ) from exc

        weight_raw = config.get("weight", DEFAULT_WEIGHT)
        try:
            weight = int(weight_raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"gateway '{resource.name}' weight must be an integer, got {weight_raw!r}"
            ) from exc

        enabled = _require_bool(config, "enabled", default=True, resource_name=resource.name)
        defaultgw = _require_bool(config, "defaultgw", default=False, resource_name=resource.name)
        monitor_disable = _require_bool(
            config, "monitor_disable", default=False, resource_name=resource.name
        )
        monitor_noroute = _require_bool(
            config, "monitor_noroute", default=False, resource_name=resource.name
        )
        force_down = _require_bool(config, "force_down", default=False, resource_name=resource.name)
        fargw = _require_bool(config, "fargw", default=False, resource_name=resource.name)
        lock = _require_bool(config, "lock", default=False, resource_name=resource.name)

        configs.append(
            GatewayConfig(
                name=resource.name,
                interface=interface,
                protocol=protocol,
                gateway=gateway_field,
                enabled=enabled,
                ipaddr=ipaddr,
                defaultgw=defaultgw,
                monitor=monitor,
                monitor_disable=monitor_disable,
                monitor_noroute=monitor_noroute,
                force_down=force_down,
                fargw=fargw,
                priority=priority,
                weight=weight,
                description=description,
                lock=lock,
            )
        )

    return configs


def _require_bool(
    config: dict[str, Any], field_name: str, *, default: bool, resource_name: str
) -> bool:
    value = config.get(field_name, default)
    if not isinstance(value, bool):
        raise ValueError(
            f"gateway '{resource_name}' {field_name} must be a boolean (true/false), "
            f"got {type(value).__name__}"
        )
    return value


def _bool_str(value: bool) -> str:
    """Convert a Python bool to OPNsense's ``"0"``/``"1"`` representation."""
    return "1" if value else "0"


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class GatewayService(BaseService):
    """Service for OPNsense gateway operations via direct API.

    Single controller, single endpoint family — no per-kind dispatch.
    Identity is the natural-key ``name``, so the diff engine matches
    operator YAML directly to live records by name. Dynamic / virtual
    gateways are silently filtered out.
    """

    # ------------------------------------------------------------------
    # API operations (CRUD + reconfigure)
    # ------------------------------------------------------------------

    def search(self) -> list[LiveGateway]:
        """Fetch the live gateway list.

        Returns:
            ``LiveGateway`` instances normalized from the search rows.
            Includes both managed and dynamic gateways; the diff engine
            filters dynamics out.
        """
        response = self.client.request("POST", f"{_GATEWAY_BASE}/searchGateway")

        rows: list[dict[str, Any]] = []
        if isinstance(response, dict):
            raw_rows = response.get("rows")
            if isinstance(raw_rows, list):
                rows = [r for r in raw_rows if isinstance(r, dict)]

        return [_row_to_live(row) for row in rows]

    def get(self, uuid: str) -> dict[str, Any]:
        """Fetch the full gateway record by UUID.

        Used by ``export_to_yaml`` to read the option-dict-rendered fields
        that ``searchGateway`` doesn't expose. Returns the raw envelope
        ``{"gateway_item": {...}}``.
        """
        return self.client.request("GET", f"{_GATEWAY_BASE}/getGateway/{uuid}")

    def add(self, gateway: GatewayConfig) -> dict[str, Any]:
        """Create a gateway.

        Args:
            gateway: Desired-state gateway configuration.

        Returns:
            API response dict (typically ``{"result": "saved", "uuid": ...}``).
        """
        return self.client.request(
            "POST",
            f"{_GATEWAY_BASE}/addGateway",
            data=gateway.to_payload(),
        )

    def update(self, uuid: str, gateway: GatewayConfig) -> dict[str, Any]:
        """Update an existing gateway by UUID.

        Args:
            uuid: OPNsense-assigned gateway UUID.
            gateway: New desired-state configuration.

        Returns:
            API response dict.
        """
        return self.client.request(
            "POST",
            f"{_GATEWAY_BASE}/setGateway/{uuid}",
            data=gateway.to_payload(),
        )

    def delete(self, uuid: str) -> dict[str, Any]:
        """Delete a gateway by UUID.

        Args:
            uuid: OPNsense-assigned gateway UUID.

        Returns:
            API response dict (typically ``{"result": "deleted"}``).
        """
        return self.client.request("POST", f"{_GATEWAY_BASE}/delGateway/{uuid}")

    def reconfigure(self) -> dict[str, Any]:
        """Apply pending gateway changes (commit staged config to running system).

        Must be called after add/update/delete operations to activate them.
        Response shape per the OpenAPI spec is ``{"status": "ok" | "failed"}``.
        """
        return self.client.request("POST", f"{_GATEWAY_BASE}/reconfigure")

    # ------------------------------------------------------------------
    # Diff + apply orchestration
    # ------------------------------------------------------------------

    def compute_diff(
        self,
        desired: list[GatewayConfig],
        live: list[LiveGateway],
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
            ``{"created": N, "updated": M, "deleted": K}``. ``reconfigure``
            is called once at the end if any mutation happened.
        """
        created = 0
        updated = 0
        deleted = 0

        for gateway in diff.adds:
            self.add(gateway)
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
        """Export the current managed gateway configuration to InfraFoundry YAML.

        Dynamic / virtual gateways are excluded — they're synthesized from
        interface state and shouldn't be in YAML. For each managed gateway
        we issue a ``getGateway/<uuid>`` to capture the option-dict-only
        fields (``interface``, ``ipprotocol``) at full fidelity.

        Output is the nested ``opnsense:`` schema defined by ADR-0016
        (#793 Phase 4); gateways land at ``opnsense.routing.gateways`` as
        a YAML sequence.

        Returns:
            YAML string with the nested ``opnsense:`` namespace and a
            ``routing.gateways`` list leaf.
        """
        live = self.search()
        managed = [g for g in live if g.is_managed]
        entries = [
            {
                "name": g.name,
                "config": _live_to_export_config(self.get(g.uuid)),
            }
            for g in managed
        ]
        return emit_nested_list_yaml("routing.gateways", entries)


# ---------------------------------------------------------------------------
# Internal helpers (row parsing / export)
# ---------------------------------------------------------------------------


def _row_to_live(row: dict[str, Any]) -> LiveGateway:
    """Normalize a ``searchGateway`` row into a ``LiveGateway``.

    Dynamic / virtual gateways are flagged via ``is_managed=False`` so the
    diff engine can ignore them.
    """
    uuid = str(row.get("uuid", ""))
    name = str(row.get("name", ""))
    dynamic = bool(row.get("dynamic", False))
    virtual = bool(row.get("virtual", False))
    is_managed = not (dynamic or virtual)
    return LiveGateway(uuid=uuid, name=name, is_managed=is_managed, raw=row)


def _live_to_export_config(get_response: dict[str, Any]) -> dict[str, Any]:
    """Build a YAML-friendly config dict from a ``getGateway`` envelope.

    Reads the option-dict ``interface`` and ``ipprotocol`` via
    ``_normalize_field`` to recover the operator-facing key. Booleans are
    decoded from the ``"0"``/``"1"`` strings that OPNsense returns. The
    operator-facing ``enabled`` is the inverse of the live ``disabled``.
    """
    item = get_response.get("gateway_item", {}) if isinstance(get_response, dict) else {}
    return {
        "enabled": _normalize_field(item.get("disabled")) != "1",
        "interface": _normalize_field(item.get("interface")),
        "protocol": _normalize_field(item.get("ipprotocol")) or "inet",
        "gateway": _normalize_field(item.get("gateway")),
        "defaultgw": _normalize_field(item.get("defaultgw")) == "1",
        "fargw": _normalize_field(item.get("fargw")) == "1",
        "monitor": _normalize_field(item.get("monitor")),
        "monitor_disable": _normalize_field(item.get("monitor_disable")) == "1",
        "monitor_noroute": _normalize_field(item.get("monitor_noroute")) == "1",
        "force_down": _normalize_field(item.get("force_down")) == "1",
        "priority": int(_normalize_field(item.get("priority")) or DEFAULT_PRIORITY),
        "weight": int(_normalize_field(item.get("weight")) or DEFAULT_WEIGHT),
        "description": _normalize_field(item.get("descr")),
    }
