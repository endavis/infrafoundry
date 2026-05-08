"""Unbound forward service for OPNsense direct-API operations (ADR-0014, #724).

Manages OPNsense Unbound DNS forwarders (both DNS-over-TLS and plain
forward) via the
``unbound/settings/{search,get,add,set,del,toggle}Forward`` controller.

OPNsense merges what the GUI calls "Domain Override" and "Forwarder" into
a single resource: a ``Forward`` entry with ``type=forward, domain=""``
acts as a global forwarder, while ``type=forward, domain="example.com"``
acts as a per-domain forwarder. ``type=dot`` selects DNS-over-TLS as the
upstream protocol. The operator-facing field is ``type``; both modes
share the same envelope key ``dot`` (counter-intuitive on the wire but
empirically confirmed by the live API probe).

Identity is the natural-key tuple ``(type, domain, server, port)``.
Including ``type`` in the key lets DoT and plain forwarders coexist for
the same domain/server/port (a common dual-resolver setup). The
operator-facing YAML ``name`` is metadata only.

Endpoint surface (confirmed live on ``opnsense-a`` running ``26.1.6_2``,
2026-05-04 probe):

- ``POST unbound/settings/searchForward`` — list rows for the dataTable
  view. Response shape ``{"rows": [...], ...}``; rows expose flat
  ``type`` (selected key), ``domain``, ``server``, ``port``,
  ``description``, ``enabled``.
- ``GET  unbound/settings/getForward/<uuid>`` — full record under
  ``{"dot": {...}}`` envelope (envelope name is "dot" regardless of the
  ``type`` field's value), with ``type`` rendered as an option dict.
- ``POST unbound/settings/addForward`` — body envelope ``{"dot": {...}}``.
- ``POST unbound/settings/setForward/<uuid>`` — same body envelope.
- ``POST unbound/settings/delForward/<uuid>`` — response
  ``{"result": "deleted"}``.
- ``POST unbound/service/reconfigure`` — typed response
  ``{"status": "ok" | "failed"}``.

Field schema (probe-derived, recorded here so a follow-up doesn't need to
re-probe):

- Required: ``server`` (IPv4 or IPv6).
- Select: ``type`` (``forward`` default, or ``dot``).
- Optional strings: ``domain`` (empty = global forwarder),
  ``port`` (default ``"53"``), ``verify`` (CN to verify when
  ``type=dot``), ``description``.
- Booleans serialized as ``"0"``/``"1"`` strings: ``enabled``,
  ``forward_tcp_upstream``, ``forward_first``.

Field names match the wire format verbatim — no YAML aliases. Note that
this is unusual: ``verify`` (not ``verify_cn``) and
``forward_tcp_upstream`` (not ``forward_tls_upstream``) — the original
issue body's sketch was incorrect; the probe is the authority.

Identity contract recap:

- Two forwarders with the same ``(type, domain, server, port)`` tuple
  are the same record by the diff engine; updating any of those fields
  is a delete + add. Updating ``description``, ``verify``,
  ``forward_tcp_upstream``, ``forward_first``, or ``enabled`` only is an
  in-place ``setForward`` (preserves UUID).
- Operator-facing YAML ``name`` is metadata only — used for
  ``ResourceOutcome.address``-style addressing.
- ``lock: true`` is honored: locked entries appear in ``Diff.locked`` and
  are never added, updated, or deleted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

import yaml

from infrafoundry.core.provider import ResourceConfig

from .base import BaseService

# Allowed values for the ``type`` discriminator.
ForwardType = Literal["forward", "dot"]
ALLOWED_FORWARD_TYPES: tuple[ForwardType, ...] = ("forward", "dot")

# Controller base for all forward CRUD endpoints.
_FORWARD_BASE = "unbound/settings"
# The Unbound service's reconfigure verb is shared across every
# Unbound-managed component (host overrides / aliases / forwards).
_RECONFIGURE_PATH = "unbound/service/reconfigure"

# Default port when operator omits ``port`` from YAML.
_DEFAULT_PORT = "53"


# ---------------------------------------------------------------------------
# Domain model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class UnboundForwardConfig:
    """Desired-state Unbound forward configuration.

    The operator-facing YAML ``name`` is metadata only — used for
    ``ResourceOutcome`` addresses — and never travels on the wire. The
    diff engine matches on the natural-key tuple
    ``(type, domain, server, port)``.

    ``lock`` is a per-resource safety annotation (ADR-0014 §6) — locked
    entries appear in ``Diff.locked`` but are never added, updated, or
    deleted.

    Attributes:
        name: Operator-facing YAML name; metadata only.
        type: ``forward`` (default; plain UDP/TCP forward) or ``dot``
            (DNS-over-TLS forward).
        server: Upstream server IP (IPv4 or IPv6). Required.
        domain: Domain to forward (empty = global forwarder).
        port: Upstream port. Default ``"53"`` when omitted.
        verify: Common Name to verify upstream certificate against
            (only meaningful when ``type=dot``).
        forward_tcp_upstream: Whether to force TCP for the upstream
            query.
        forward_first: Whether to fall back to recursion if the
            forwarder fails.
        enabled: Whether the forwarder is active.
        description: Operator-facing free-form description.
        lock: Per-resource safety annotation (ADR-0014 §6).
    """

    name: str
    server: str
    type: ForwardType = "forward"
    domain: str = ""
    port: str = _DEFAULT_PORT
    verify: str = ""
    forward_tcp_upstream: bool = False
    forward_first: bool = False
    enabled: bool = True
    description: str = ""
    lock: bool = False

    @property
    def diff_key(self) -> tuple[str, str, str, str]:
        """Identity of this forward: the ``(type, domain, server, port)`` tuple."""
        return (self.type, self.domain, self.server, self.port)

    def to_payload(self) -> dict[str, Any]:
        """Serialize to the ``addForward``/``setForward`` envelope.

        Returns:
            ``{"dot": {<fields>}}``. Booleans are stringified to
            ``"0"``/``"1"``. The operator-facing ``name`` is intentionally
            NOT sent — it is metadata only.

        Note that the envelope key is ``dot`` regardless of the ``type``
        field's value (this is empirically confirmed and counter-intuitive;
        see module docstring).
        """
        return {
            "dot": {
                "type": self.type,
                "domain": self.domain,
                "server": self.server,
                "port": self.port,
                "verify": self.verify,
                "forward_tcp_upstream": _bool_str(self.forward_tcp_upstream),
                "forward_first": _bool_str(self.forward_first),
                "enabled": _bool_str(self.enabled),
                "description": self.description,
            }
        }


@dataclass(frozen=True)
class LiveUnboundForward:
    """An Unbound forwarder as currently configured on the OPNsense box.

    ``raw`` is the ``searchForward`` row, which exposes flat
    ``type`` (selected key), ``domain``, ``server``, ``port`` columns
    plus the rest. The ``getForward`` envelope is read separately during
    ``export_to_yaml`` to recover option-dict-rendered fields.

    Attributes:
        uuid: OPNsense-assigned UUID for the forwarder.
        type: ``forward`` or ``dot`` (from the row's selected option key).
        domain: Domain (empty = global forwarder).
        server: Upstream server IP.
        port: Upstream port.
        raw: Full original ``searchForward`` row for field comparison
            during update detection.
    """

    uuid: str
    type: str
    domain: str
    server: str
    port: str
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def diff_key(self) -> tuple[str, str, str, str]:
        """Identity of this forward: the ``(type, domain, server, port)`` tuple."""
        return (self.type, self.domain, self.server, self.port)


@dataclass
class Diff:
    """Result of comparing desired YAML state to live OPNsense state.

    Mirrors ``services.static_route.Diff``: adds / updates / deletes /
    locked, plus ``is_empty``. Updates carry the live record alongside
    the desired record so the caller has the UUID. Locked entries pair
    desired YAML with their (possibly missing) live record.

    Note that changing any field in the identity tuple (``type``,
    ``domain``, ``server``, or ``port``) on a YAML resource produces a
    delete + add, not an update.
    """

    adds: list[UnboundForwardConfig] = field(default_factory=list)
    updates: list[tuple[LiveUnboundForward, UnboundForwardConfig]] = field(default_factory=list)
    deletes: list[LiveUnboundForward] = field(default_factory=list)
    locked: list[tuple[UnboundForwardConfig, LiveUnboundForward | None]] = field(
        default_factory=list
    )

    @property
    def is_empty(self) -> bool:
        """Return True if there are no add/update/delete operations to apply."""
        return not (self.adds or self.updates or self.deletes)


# ---------------------------------------------------------------------------
# Diff engine
# ---------------------------------------------------------------------------


def compute_diff(
    desired: list[UnboundForwardConfig],
    current: list[LiveUnboundForward],
    *,
    add_only: bool = False,
) -> Diff:
    """Compare desired YAML state to live state, keyed by ``(type, domain, server, port)``.

    Args:
        desired: Forwards the operator wants to exist.
        current: Forwards currently on the box.
        add_only: If True, never emit deletes for live forwards that
            don't appear in ``desired``. Adds and updates still happen.

    Returns:
        ``Diff`` with adds / updates / deletes plus locked entries.
    """
    desired_by_key: dict[tuple[str, str, str, str], UnboundForwardConfig] = {
        f.diff_key: f for f in desired
    }
    current_by_key: dict[tuple[str, str, str, str], LiveUnboundForward] = {
        f.diff_key: f for f in current
    }
    locked_keys: set[tuple[str, str, str, str]] = {f.diff_key for f in desired if f.lock}

    adds: list[UnboundForwardConfig] = []
    updates: list[tuple[LiveUnboundForward, UnboundForwardConfig]] = []
    deletes: list[LiveUnboundForward] = []
    locked: list[tuple[UnboundForwardConfig, LiveUnboundForward | None]] = []

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


def _needs_update(have: LiveUnboundForward, want: UnboundForwardConfig) -> bool:
    """Return True if the live row's fields differ from the desired payload."""
    payload = want.to_payload()["dot"]
    for key, want_value in payload.items():
        have_value = _normalize_field(have.raw.get(key))
        if str(want_value) != have_value:
            return True
    return False


def _normalize_field(value: Any) -> str:
    """Collapse an OPNsense field value to a comparable string.

    Booleans are serialized as ``"1"`` / ``"0"`` to match what we'd send.
    Select fields returned as option dicts (from ``getForward``) extract
    the selected key. Plain scalars are stringified verbatim. ``None``
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


def unbound_forward_configs_from_resources(
    resources: list[ResourceConfig],
) -> list[UnboundForwardConfig]:
    """Convert ``ResourceConfig`` entries to ``UnboundForwardConfig`` instances.

    Validation here is intentionally minimal — the validator handles
    cross-resource references and operator-friendly error messages; this
    parser only enforces type sanity so manager code can rely on field
    invariants.

    Args:
        resources: All provider resources from a ConfigManager load.
            Non-``unbound_forward`` entries are silently skipped.

    Returns:
        Validated ``UnboundForwardConfig`` list.

    Raises:
        ValueError: If an entry has a non-dict config, missing required
            fields, or non-bool booleans / non-string fields, or an
            invalid ``type``.
    """
    configs: list[UnboundForwardConfig] = []
    for resource in resources:
        if resource.type != "unbound.forwards":
            continue

        config = resource.config
        if not isinstance(config, dict):
            raise ValueError(f"unbound_forward '{resource.name}' has non-dict config")

        server = config.get("server", "")
        if not isinstance(server, str) or not server:
            raise ValueError(
                f"unbound_forward '{resource.name}' requires a non-empty string 'server'"
            )

        forward_type_raw = config.get("type", "forward")
        if not isinstance(forward_type_raw, str):
            raise ValueError(
                f"unbound_forward '{resource.name}' type must be a string "
                f"({'/'.join(ALLOWED_FORWARD_TYPES)})"
            )
        if forward_type_raw not in ALLOWED_FORWARD_TYPES:
            raise ValueError(
                f"unbound_forward '{resource.name}' type {forward_type_raw!r} not in "
                f"{ALLOWED_FORWARD_TYPES}"
            )
        forward_type: ForwardType = forward_type_raw

        domain = config.get("domain", "")
        if not isinstance(domain, str):
            raise ValueError(f"unbound_forward '{resource.name}' domain must be a string")

        # Port is operator-facing as int OR string; we always serialize
        # to a string. Validator handles range checks.
        port_raw = config.get("port", _DEFAULT_PORT)
        if isinstance(port_raw, int) and not isinstance(port_raw, bool):
            port = str(port_raw)
        elif isinstance(port_raw, str):
            port = port_raw or _DEFAULT_PORT
        else:
            raise ValueError(f"unbound_forward '{resource.name}' port must be an integer or string")

        verify = config.get("verify", "")
        if not isinstance(verify, str):
            raise ValueError(f"unbound_forward '{resource.name}' verify must be a string")

        description = config.get("description", "")
        if not isinstance(description, str):
            raise ValueError(f"unbound_forward '{resource.name}' description must be a string")

        forward_tcp_upstream = _require_bool(
            config, "forward_tcp_upstream", default=False, resource_name=resource.name
        )
        forward_first = _require_bool(
            config, "forward_first", default=False, resource_name=resource.name
        )
        enabled = _require_bool(config, "enabled", default=True, resource_name=resource.name)
        lock = _require_bool(config, "lock", default=False, resource_name=resource.name)

        configs.append(
            UnboundForwardConfig(
                name=resource.name,
                type=forward_type,
                server=server,
                domain=domain,
                port=port,
                verify=verify,
                forward_tcp_upstream=forward_tcp_upstream,
                forward_first=forward_first,
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
            f"unbound_forward '{resource_name}' {field_name} must be a boolean (true/false), "
            f"got {type(value).__name__}"
        )
    return value


def _bool_str(value: bool) -> str:
    """Convert a Python bool to OPNsense's ``"0"``/``"1"`` representation."""
    return "1" if value else "0"


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class UnboundForwardService(BaseService):
    """Service for OPNsense Unbound forward operations via direct API.

    Identity is the natural-key ``(type, domain, server, port)`` tuple —
    the diff engine matches operator YAML directly to live records by
    tuple. The operator-facing ``name`` never travels on the wire.
    """

    # ------------------------------------------------------------------
    # API operations (CRUD + reconfigure)
    # ------------------------------------------------------------------

    def search(self) -> list[LiveUnboundForward]:
        """Fetch the live forward list.

        Returns:
            ``LiveUnboundForward`` instances normalized from the search rows.
        """
        response = self.client.request("POST", f"{_FORWARD_BASE}/searchForward")

        rows: list[dict[str, Any]] = []
        if isinstance(response, dict):
            raw_rows = response.get("rows")
            if isinstance(raw_rows, list):
                rows = [r for r in raw_rows if isinstance(r, dict)]

        return [_row_to_live(row) for row in rows]

    def get(self, uuid: str) -> dict[str, Any]:
        """Fetch the full forward record by UUID.

        Used by ``export_to_yaml`` to read the option-dict-rendered fields
        that ``searchForward`` doesn't expose. Returns the raw envelope
        ``{"dot": {...}}``.
        """
        return self.client.request("GET", f"{_FORWARD_BASE}/getForward/{uuid}")

    def add(self, forward: UnboundForwardConfig) -> dict[str, Any]:
        """Create a forward.

        Args:
            forward: Desired-state forward configuration.

        Returns:
            API response dict (typically ``{"result": "saved", "uuid": ...}``).
        """
        return self.client.request(
            "POST",
            f"{_FORWARD_BASE}/addForward",
            data=forward.to_payload(),
        )

    def update(self, uuid: str, forward: UnboundForwardConfig) -> dict[str, Any]:
        """Update an existing forward by UUID.

        Args:
            uuid: OPNsense-assigned forward UUID.
            forward: New desired-state configuration.

        Returns:
            API response dict.
        """
        return self.client.request(
            "POST",
            f"{_FORWARD_BASE}/setForward/{uuid}",
            data=forward.to_payload(),
        )

    def delete(self, uuid: str) -> dict[str, Any]:
        """Delete a forward by UUID.

        Args:
            uuid: OPNsense-assigned forward UUID.

        Returns:
            API response dict (typically ``{"result": "deleted"}``).
        """
        return self.client.request("POST", f"{_FORWARD_BASE}/delForward/{uuid}")

    def reconfigure(self) -> dict[str, Any]:
        """Apply pending Unbound changes (commit staged config to running system).

        Must be called after add/update/delete operations to activate them.
        Response shape per the OpenAPI spec is ``{"status": "ok" | "failed"}``.
        """
        return self.client.request("POST", _RECONFIGURE_PATH)

    # ------------------------------------------------------------------
    # Diff + apply orchestration
    # ------------------------------------------------------------------

    def compute_diff(
        self,
        desired: list[UnboundForwardConfig],
        live: list[LiveUnboundForward],
        *,
        add_only: bool = False,
    ) -> Diff:
        """Compute the add/update/delete diff between desired and live state.

        Thin wrapper over the module-level ``compute_diff`` for callers
        that prefer the service-method form.
        """
        return compute_diff(desired, live, add_only=add_only)

    def apply_diff(self, diff: Diff) -> dict[str, int]:
        """Dispatch the operations described by ``diff``.

        Does **not** call ``reconfigure()`` — the runner fires the shared
        ``unbound_reconfigure`` finalization hook exactly once per apply
        across all three unbound managers (#776). Mutation-without-
        reconfigure is the new contract; callers wanting the legacy
        inline behavior can call ``service.reconfigure()`` directly.

        Returns:
            Counts of operations actually performed:
            ``{"created": N, "updated": M, "deleted": K}``.
        """
        created = 0
        updated = 0
        deleted = 0

        for forward in diff.adds:
            self.add(forward)
            created += 1

        for live, want in diff.updates:
            self.update(live.uuid, want)
            updated += 1

        for live in diff.deletes:
            self.delete(live.uuid)
            deleted += 1

        return {"created": created, "updated": updated, "deleted": deleted}

    # ------------------------------------------------------------------
    # Migration / export
    # ------------------------------------------------------------------

    def export_to_yaml(self) -> str:
        """Export the current forward configuration to InfraFoundry YAML.

        For each live forward we issue a ``getForward/<uuid>`` to capture
        the option-dict-rendered ``type`` field at full fidelity.
        Operator-facing ``name`` is synthesized from
        ``(type, domain, server, port)`` since OPNsense has no name field
        — the operator can rename freely after import; identity is the
        tuple, not the name.

        Returns:
            YAML string with ``provider/type/name/config`` entries.
        """
        live = self.search()
        resources = [
            {
                "provider": "opnsense",
                "type": "unbound_forward",
                "name": _synthesize_name(forward),
                "config": _live_to_export_config(self.get(forward.uuid)),
            }
            for forward in live
        ]
        return yaml.safe_dump({"resources": resources}, sort_keys=False)


# ---------------------------------------------------------------------------
# Internal helpers (row parsing / export)
# ---------------------------------------------------------------------------


def _row_to_live(row: dict[str, Any]) -> LiveUnboundForward:
    """Normalize a ``searchForward`` row into a ``LiveUnboundForward``."""
    uuid = str(row.get("uuid", ""))
    forward_type = _normalize_field(row.get("type"))
    domain = _normalize_field(row.get("domain"))
    server = _normalize_field(row.get("server"))
    port = _normalize_field(row.get("port"))
    return LiveUnboundForward(
        uuid=uuid,
        type=forward_type,
        domain=domain,
        server=server,
        port=port,
        raw=row,
    )


def _synthesize_name(forward: LiveUnboundForward) -> str:
    """Build a YAML-friendly synthetic name from a ``LiveUnboundForward``.

    Replaces characters that don't survive YAML keys / kebab-case
    conventions (``:`` for IPv6, ``.``) with hyphens. The operator can
    rename after import; identity is the tuple, not the name.
    """
    domain_part = forward.domain.replace(".", "-") if forward.domain else "global"
    server_part = forward.server.replace(":", "-").replace(".", "-")
    return f"forward-{forward.type}-{domain_part}-{server_part}-{forward.port}".lower()


def _live_to_export_config(get_response: dict[str, Any]) -> dict[str, Any]:
    """Build a YAML-friendly config dict from a ``getForward`` envelope.

    Reads the option-dict ``type`` via ``_normalize_field`` to recover
    the selected forward type. Booleans are decoded from the ``"0"``/``"1"``
    strings that OPNsense returns.
    """
    item = get_response.get("dot", {}) if isinstance(get_response, dict) else {}
    return {
        "type": _normalize_field(item.get("type")) or "forward",
        "domain": _normalize_field(item.get("domain")),
        "server": _normalize_field(item.get("server")),
        "port": _normalize_field(item.get("port")) or _DEFAULT_PORT,
        "verify": _normalize_field(item.get("verify")),
        "forward_tcp_upstream": _normalize_field(item.get("forward_tcp_upstream")) == "1",
        "forward_first": _normalize_field(item.get("forward_first")) == "1",
        "enabled": _normalize_field(item.get("enabled")) == "1",
        "description": _normalize_field(item.get("description")),
    }
