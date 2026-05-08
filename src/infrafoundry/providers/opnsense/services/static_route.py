"""Static-route service for OPNsense direct-API operations (ADR-0014, #722).

Manages OPNsense static routes via the ``routes/routes/*route`` controller.
Identity is the natural key tuple ``(network, gateway)`` — OPNsense does not
expose a server-unique ``name`` field on routes (the YAML ``name`` is operator
metadata for cross-resource references only and never appears on the wire).
The diff engine matches by the natural-key tuple. No description-suffix tag,
no ``infrafoundry`` category bootstrap (routes have no categories).

Endpoint surface (confirmed live on ``opnsense-a`` running ``26.1.6_2``,
2026-05-04 probe; corroborated by the bundled ``opnsense_openapi==0.4.0``
spec for 26.1.6):

- ``POST routes/routes/searchroute`` — list rows for the dataTable view.
  Response shape ``{"rows": [...], "rowCount": N, "total": N, "current": 1}``;
  rows expose the flat ``gateway`` (selected key) plus ``%gateway`` (display
  string) — only ``gateway`` is read by the diff engine.
- ``GET  routes/routes/getroute/<uuid>`` — full record under ``{"route": {...}}``
  envelope, with ``gateway`` rendered as an option dict
  (``{<gw_name>: {"value": "<display>", "selected": 0|1}, ...}``).
- ``POST routes/routes/addroute`` — body envelope ``{"route": {...}}``;
  response ``{"result": "saved", "uuid": "..."}`` on success or
  ``{"result": "failed", "validations": {<field>: <message>}}`` on
  server-side validation failure.
- ``POST routes/routes/setroute/<uuid>`` — same body envelope as add.
- ``POST routes/routes/delroute/<uuid>`` — response ``{"result": "deleted"}``.
- ``POST routes/routes/toggleroute/<uuid>`` — flips ``disabled`` (not used by
  this service; the operator-facing ``enabled`` is set via add/set instead).
- ``POST routes/routes/reconfigure`` — typed response ``{"status": "ok"|"failed"}``.

Field schema (probe-derived, recorded here so a follow-up doesn't need to
re-probe). All write fields are simple strings on the wire:

- Required: ``network`` (CIDR matching the gateway's IP protocol),
  ``gateway`` (the next-hop gateway name — must reference a gateway that
  exists on the box; managed gateways listed in YAML or live system gateways
  like ``WAN_DHCP``/``WAN_DHCP6`` are both accepted at the validator level
  and at the API level).
- Booleans serialized as ``"0"``/``"1"`` strings: ``disabled``.
- Strings: ``descr``.

The wire surface is intentionally narrow — OPNsense's ``<staticroutes>/route``
schema in ``config.xml`` only exposes those four fields plus the auto-assigned
``uuid``. The probe confirmed no additional knobs (no metric / mtu / interface
override etc.) on ``26.1.6_2``. If a future OPNsense release exposes new
fields, the schema here grows in lockstep.

Cross-protocol mismatch (e.g., an IPv4 CIDR routed through an IPv6 gateway)
is *not* always rejected at the API level — empirically the box accepted
``203.0.113.0/24`` → ``WAN_DHCP6`` during the probe — so the validator
enforces the family match before the request lands.

Identity contract recap:

- Two routes with the same ``(network, gateway)`` tuple are considered the
  same record by the diff engine; updating either of those fields is a
  delete + add (the diff engine emits both). Updating ``descr`` or
  ``disabled`` only is an in-place ``setroute`` (preserves UUID).
- Operator-facing YAML ``name`` is metadata only — used for cross-resource
  reference lookups and ``ResourceOutcome.address``-style addressing — and
  is never sent on the wire as identity.
- ``lock: true`` is honored: locked entries appear in ``Diff.locked`` and
  are never added, updated, or deleted.

The operator-facing YAML uses ``enabled: bool`` (matches the rest of the
provider's resources); on serialization that's flipped to OPNsense's
``disabled`` field. Same applies to ``description`` (YAML) → ``descr`` (API).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import yaml

from infrafoundry.core.provider import ResourceConfig

from .base import BaseService

# Controller base for all static-route CRUD + reconfigure endpoints.
_ROUTE_BASE = "routes/routes"


# ---------------------------------------------------------------------------
# Domain model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StaticRouteConfig:
    """Desired-state static-route configuration.

    The operator-facing YAML ``name`` is metadata only — used for cross-
    resource references and ``ResourceOutcome`` addresses — and never
    travels on the wire. The diff engine matches on the natural-key
    tuple ``(network, gateway)``.

    ``lock`` is a per-resource safety annotation (ADR-0014 §6) — locked
    entries appear in ``Diff.locked`` but are never added, updated, or
    deleted.

    Attributes:
        name: Operator-facing YAML name; metadata only.
        network: Destination CIDR (IPv4 or IPv6).
        gateway: Next-hop gateway name (managed or live system gateway).
        enabled: Whether the route is active. Inverted to ``disabled``
            on the wire.
        description: Operator-facing free-form description (mapped to
            ``descr`` on the wire).
        lock: Per-resource safety annotation (ADR-0014 §6).
    """

    name: str
    network: str
    gateway: str
    enabled: bool = True
    description: str = ""
    lock: bool = False

    @property
    def diff_key(self) -> tuple[str, str]:
        """Identity of this route: the ``(network, gateway)`` natural-key tuple."""
        return (self.network, self.gateway)

    def to_payload(self) -> dict[str, Any]:
        """Serialize to the ``addroute``/``setroute`` envelope.

        Returns:
            ``{"route": {<fields>}}``. Booleans are stringified to
            ``"0"``/``"1"``; ``enabled`` is inverted to ``disabled``;
            ``description`` maps to ``descr``. The operator-facing
            ``name`` is intentionally NOT sent — it is metadata only.
        """
        return {
            "route": {
                "network": self.network,
                "gateway": self.gateway,
                "disabled": _bool_str(not self.enabled),
                "descr": self.description,
            }
        }


@dataclass(frozen=True)
class LiveStaticRoute:
    """A static route as currently configured on the OPNsense box.

    ``raw`` is the ``searchroute`` row, which exposes the flat ``gateway``
    field (the selected key, not the option dict) plus ``%gateway``
    (display string) — only ``gateway`` is read by the diff engine. The
    ``getroute`` envelope is read separately during ``export_to_yaml``
    to recover the option-dict-rendered fields.

    Attributes:
        uuid: OPNsense-assigned UUID.
        network: Destination CIDR.
        gateway: Next-hop gateway name.
        raw: Full original ``searchroute`` row for field comparison
            during update detection.
    """

    uuid: str
    network: str
    gateway: str
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def diff_key(self) -> tuple[str, str]:
        """Identity of this route: the ``(network, gateway)`` natural-key tuple."""
        return (self.network, self.gateway)


@dataclass
class Diff:
    """Result of comparing desired YAML state to live OPNsense state.

    Mirrors ``services.gateway.Diff`` and ``services.nat_rule.Diff``: adds /
    updates / deletes / locked, plus ``is_empty``. Updates carry the live
    record alongside the desired record so the caller has the UUID. Locked
    entries pair desired YAML with their (possibly missing) live record.

    Note that changing ``network`` or ``gateway`` (the identity tuple) on
    a YAML resource produces a delete + add, not an update — the live
    record's tuple no longer matches anything in YAML and a new tuple
    appears with no live counterpart.
    """

    adds: list[StaticRouteConfig] = field(default_factory=list)
    updates: list[tuple[LiveStaticRoute, StaticRouteConfig]] = field(default_factory=list)
    deletes: list[LiveStaticRoute] = field(default_factory=list)
    locked: list[tuple[StaticRouteConfig, LiveStaticRoute | None]] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        """Return True if there are no add/update/delete operations to apply."""
        return not (self.adds or self.updates or self.deletes)


# ---------------------------------------------------------------------------
# Diff engine
# ---------------------------------------------------------------------------


def compute_diff(
    desired: list[StaticRouteConfig],
    current: list[LiveStaticRoute],
    *,
    add_only: bool = False,
) -> Diff:
    """Compare desired YAML state to live state, keyed by ``(network, gateway)``.

    Args:
        desired: Routes the operator wants to exist.
        current: Routes currently on the box.
        add_only: If True, never emit deletes for live routes that don't
            appear in ``desired``. Adds and updates still happen.

    Returns:
        ``Diff`` with adds / updates / deletes plus locked entries.
    """
    desired_by_key: dict[tuple[str, str], StaticRouteConfig] = {r.diff_key: r for r in desired}
    current_by_key: dict[tuple[str, str], LiveStaticRoute] = {r.diff_key: r for r in current}
    locked_keys: set[tuple[str, str]] = {r.diff_key for r in desired if r.lock}

    adds: list[StaticRouteConfig] = []
    updates: list[tuple[LiveStaticRoute, StaticRouteConfig]] = []
    deletes: list[LiveStaticRoute] = []
    locked: list[tuple[StaticRouteConfig, LiveStaticRoute | None]] = []

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


def _needs_update(have: LiveStaticRoute, want: StaticRouteConfig) -> bool:
    """Return True if the live row's fields differ from the desired payload.

    Compares the inner ``route`` payload from ``want.to_payload()`` against
    the corresponding fields on ``have.raw``. ``searchroute`` returns
    ``gateway`` as a flat string (the selected option key) — same shape as
    ``want.to_payload()`` — so ``_normalize_field`` is mostly pass-through,
    but it keeps update detection robust if the API surface changes.
    """
    payload = want.to_payload()["route"]
    for key, want_value in payload.items():
        have_value = _normalize_field(have.raw.get(key))
        if str(want_value) != have_value:
            return True
    return False


def _normalize_field(value: Any) -> str:
    """Collapse an OPNsense field value to a comparable string.

    Booleans (returned from ``searchroute``'s post-processed view) are
    serialized as ``"1"`` / ``"0"`` to match what we'd send. Select fields
    returned as option dicts (from ``getroute``) extract the selected key.
    Plain scalars are stringified verbatim. ``None`` becomes ``""``.
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


def static_route_configs_from_resources(
    resources: list[ResourceConfig],
) -> list[StaticRouteConfig]:
    """Convert ``ResourceConfig`` entries to ``StaticRouteConfig`` instances.

    Validation here is intentionally minimal — the validator handles
    cross-resource references (gateway ref) and operator-friendly error
    messages; this parser only enforces type sanity so manager code can
    rely on field invariants.

    Args:
        resources: All provider resources from a ConfigManager load.
            Non-``static_routes`` entries are silently skipped.

    Returns:
        Validated ``StaticRouteConfig`` list.

    Raises:
        ValueError: If an entry has a non-dict config, missing required
            fields, or non-bool booleans / non-string fields.
    """
    configs: list[StaticRouteConfig] = []
    for resource in resources:
        if resource.type != "routing.static":
            continue

        config = resource.config
        if not isinstance(config, dict):
            raise ValueError(f"static_route '{resource.name}' has non-dict config")

        network = config.get("network", "")
        if not isinstance(network, str) or not network:
            raise ValueError(
                f"static_route '{resource.name}' requires a non-empty string 'network'"
            )

        gateway = config.get("gateway", "")
        if not isinstance(gateway, str) or not gateway:
            raise ValueError(
                f"static_route '{resource.name}' requires a non-empty string 'gateway'"
            )

        description = config.get("description", "")
        if not isinstance(description, str):
            raise ValueError(f"static_route '{resource.name}' description must be a string")

        enabled = _require_bool(config, "enabled", default=True, resource_name=resource.name)
        lock = _require_bool(config, "lock", default=False, resource_name=resource.name)

        configs.append(
            StaticRouteConfig(
                name=resource.name,
                network=network,
                gateway=gateway,
                enabled=enabled,
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
            f"static_route '{resource_name}' {field_name} must be a boolean (true/false), "
            f"got {type(value).__name__}"
        )
    return value


def _bool_str(value: bool) -> str:
    """Convert a Python bool to OPNsense's ``"0"``/``"1"`` representation."""
    return "1" if value else "0"


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class StaticRouteService(BaseService):
    """Service for OPNsense static-route operations via direct API.

    Single controller, single endpoint family — no per-kind dispatch.
    Identity is the natural-key ``(network, gateway)`` tuple, so the diff
    engine matches operator YAML directly to live records by tuple. The
    operator-facing ``name`` never travels on the wire.
    """

    # ------------------------------------------------------------------
    # API operations (CRUD + reconfigure)
    # ------------------------------------------------------------------

    def search(self) -> list[LiveStaticRoute]:
        """Fetch the live static-route list.

        Returns:
            ``LiveStaticRoute`` instances normalized from the search rows.
        """
        response = self.client.request("POST", f"{_ROUTE_BASE}/searchroute")

        rows: list[dict[str, Any]] = []
        if isinstance(response, dict):
            raw_rows = response.get("rows")
            if isinstance(raw_rows, list):
                rows = [r for r in raw_rows if isinstance(r, dict)]

        return [_row_to_live(row) for row in rows]

    def get(self, uuid: str) -> dict[str, Any]:
        """Fetch the full static-route record by UUID.

        Used by ``export_to_yaml`` to read the option-dict-rendered fields
        that ``searchroute`` doesn't expose. Returns the raw envelope
        ``{"route": {...}}``.
        """
        return self.client.request("GET", f"{_ROUTE_BASE}/getroute/{uuid}")

    def add(self, route: StaticRouteConfig) -> dict[str, Any]:
        """Create a static route.

        Args:
            route: Desired-state static-route configuration.

        Returns:
            API response dict (typically ``{"result": "saved", "uuid": ...}``).
        """
        return self.client.request(
            "POST",
            f"{_ROUTE_BASE}/addroute",
            data=route.to_payload(),
        )

    def update(self, uuid: str, route: StaticRouteConfig) -> dict[str, Any]:
        """Update an existing static route by UUID.

        Args:
            uuid: OPNsense-assigned route UUID.
            route: New desired-state configuration.

        Returns:
            API response dict.
        """
        return self.client.request(
            "POST",
            f"{_ROUTE_BASE}/setroute/{uuid}",
            data=route.to_payload(),
        )

    def delete(self, uuid: str) -> dict[str, Any]:
        """Delete a static route by UUID.

        Args:
            uuid: OPNsense-assigned route UUID.

        Returns:
            API response dict (typically ``{"result": "deleted"}``).
        """
        return self.client.request("POST", f"{_ROUTE_BASE}/delroute/{uuid}")

    def reconfigure(self) -> dict[str, Any]:
        """Apply pending route changes (commit staged config to running system).

        Must be called after add/update/delete operations to activate them.
        Response shape per the OpenAPI spec is ``{"status": "ok" | "failed"}``.
        """
        return self.client.request("POST", f"{_ROUTE_BASE}/reconfigure")

    # ------------------------------------------------------------------
    # Diff + apply orchestration
    # ------------------------------------------------------------------

    def compute_diff(
        self,
        desired: list[StaticRouteConfig],
        live: list[LiveStaticRoute],
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

        for route in diff.adds:
            self.add(route)
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
        """Export the current static-route configuration to InfraFoundry YAML.

        For each live route we issue a ``getroute/<uuid>`` to capture the
        option-dict-rendered ``gateway`` field at full fidelity. Operator-
        facing ``name`` is synthesized from ``(network, gateway)`` since
        OPNsense has no name field — the operator can rename freely after
        import; identity is the tuple, not the name.

        Returns:
            YAML string with ``provider/type/name/config`` entries.
        """
        live = self.search()
        resources = [
            {
                "provider": "opnsense",
                "type": "static_routes",
                "name": _synthesize_name(route),
                "config": _live_to_export_config(self.get(route.uuid)),
            }
            for route in live
        ]
        return yaml.safe_dump({"resources": resources}, sort_keys=False)


# ---------------------------------------------------------------------------
# Internal helpers (row parsing / export)
# ---------------------------------------------------------------------------


def _row_to_live(row: dict[str, Any]) -> LiveStaticRoute:
    """Normalize a ``searchroute`` row into a ``LiveStaticRoute``."""
    uuid = str(row.get("uuid", ""))
    network = str(row.get("network", ""))
    # ``searchroute`` returns ``gateway`` as a flat string already (the
    # selected option key); fall through to ``_normalize_field`` for safety.
    gateway = _normalize_field(row.get("gateway"))
    return LiveStaticRoute(uuid=uuid, network=network, gateway=gateway, raw=row)


def _synthesize_name(route: LiveStaticRoute) -> str:
    """Build a YAML-friendly synthetic name from a ``LiveStaticRoute``.

    Replaces characters that don't survive YAML keys / kebab-case
    conventions (``/``, ``:``) with hyphens. The operator can rename
    after import; identity is the ``(network, gateway)`` tuple, not
    the name.
    """
    sanitized = route.network.replace("/", "-").replace(":", "-").replace(".", "-")
    return f"route-{sanitized}-via-{route.gateway}".lower()


def _live_to_export_config(get_response: dict[str, Any]) -> dict[str, Any]:
    """Build a YAML-friendly config dict from a ``getroute`` envelope.

    Reads the option-dict ``gateway`` via ``_normalize_field`` to recover
    the selected gateway name. Booleans are decoded from the
    ``"0"``/``"1"`` strings that OPNsense returns. The operator-facing
    ``enabled`` is the inverse of the live ``disabled``.
    """
    item = get_response.get("route", {}) if isinstance(get_response, dict) else {}
    return {
        "enabled": _normalize_field(item.get("disabled")) != "1",
        "network": _normalize_field(item.get("network")),
        "gateway": _normalize_field(item.get("gateway")),
        "description": _normalize_field(item.get("descr")),
    }
