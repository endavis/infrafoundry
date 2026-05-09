"""Unbound host-override service for OPNsense direct-API operations (#776).

Manages OPNsense Unbound DNS host overrides via the
``unbound/settings/{search,get,add,set,del}HostOverride`` controller. Read-side
``search`` / ``export_to_yaml`` were added in #748 (read-only); the full
``add``/``update``/``delete``/``get``/``reconfigure``/``compute_diff``/
``apply_diff`` write surface lands in #776 to retire the legacy terraform
write path (``unbound_host_override.tf.j2`` +
``browningluke/opnsense_unbound_host_override``).

Endpoint surface (the ``unbound/settings`` controller in OPNsense 26.x; the
same controller already used by :mod:`services.unbound_host_alias` for parent
UUID resolution and by :mod:`validator` for cross-reference validation):

- ``POST unbound/settings/searchHostOverride`` — list rows for the dataTable
  view. Response shape ``{"rows": [...], "rowCount": N, "total": N,
  "current": 1}``. Each row exposes flat ``hostname``, ``domain``, ``server``,
  ``description``, ``rr`` (selected dict on read — ``A`` / ``AAAA`` / ``MX``),
  ``mxprio`` (string; MX records only), ``mx`` (string; MX records only), and
  ``enabled`` (string ``"0"``/``"1"``).
- ``GET unbound/settings/getHostOverride/<uuid>`` — full record under
  ``{"host": {...}}`` envelope.
- ``POST unbound/settings/addHostOverride`` — body envelope
  ``{"host": {...}}``; response ``{"result": "saved", "uuid": "..."}`` on
  success or ``{"result": "failed", "validations": {...}}`` on server-side
  validation failure.
- ``POST unbound/settings/setHostOverride/<uuid>`` — same body envelope as add.
- ``POST unbound/settings/delHostOverride/<uuid>`` — response
  ``{"result": "deleted"}``.
- ``POST unbound/service/reconfigure`` — typed response
  ``{"status": "ok"|"failed"}``. Verb shared across the entire Unbound module.

YAML schema (extended in #748 — must agree with the operator-facing
contract):

The base fields (``hostname``, ``domain``, ``enabled``, ``server``,
``description``) match what the legacy terraform template accepted since day
one; the type-specific fields below are emitted only when the live record
carries a non-default value, so existing 5-field operator YAML continues to
round-trip identically.

- ``rr`` (str) — record type. ``A`` (default), ``AAAA``, or ``MX``. Omitted
  from YAML when ``A``.
- ``mxprio`` (str, MX only) — MX priority. Preserved as a string because
  OPNsense renders it as a numeric string and we don't want to round-trip
  lose precision (mirrors ``updatefreq`` handling on aliases).
- ``mx`` (str, MX only) — MX target hostname.

Wire field names: OPNsense's REST API uses ``rr`` / ``mxprio`` / ``mx`` on
the wire. The legacy terraform schema (browningluke) renamed these to
``type`` / ``mx_priority`` / ``mx_host`` (#765/#766 schema-compliance fix).
The direct-API path stays true to OPNsense's own names — both YAML and wire
are ``rr`` / ``mxprio`` / ``mx``.

Identity contract (#776):

- Identity is the natural-key tuple ``(hostname, domain, rr)``. OPNsense
  exposes no server-unique ``name`` field; the operator-facing top-level
  ``ResourceConfig.name`` is metadata only and never travels on the wire.
- Two host overrides with the same ``(hostname, domain, rr)`` tuple are the
  same record by the diff engine. Updating any of those three fields is a
  delete + add (the diff engine emits both); updating only ``server`` /
  ``description`` / ``enabled`` / ``mxprio`` / ``mx`` is an in-place
  ``setHostOverride`` (preserves UUID).
- Including ``rr`` in the key allows an A and an AAAA record on the same
  ``(hostname, domain)`` pair to coexist (a common dual-stack setup);
  same shape ``unbound_forward`` uses to permit DoT and plain forwarders to
  coexist on the same domain/server.
- ``lock: true`` is honored: locked entries appear in ``Diff.locked`` and
  are never added, updated, or deleted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import yaml

from infrafoundry.core.provider import ResourceConfig

from .base import BaseService

# Controller base for all host-override endpoints (shared with host-alias
# parent UUID resolution and validator cross-references).
_HOST_OVERRIDE_BASE = "unbound/settings"

# The Unbound service's reconfigure verb is shared across every
# Unbound-managed component (host overrides / aliases / forwards). The
# runner coalesces all three managers' reconfigure calls via the
# ``unbound_reconfigure`` finalization hook so a multi-unbound apply
# fires a single reconfigure call (#776).
_RECONFIGURE_PATH = "unbound/service/reconfigure"

# Default record type. ``A`` is the most common shape and is also what
# OPNsense assigns when the operator leaves the ``rr`` field unset in
# the GUI; emit ``rr`` to YAML only when the live record carries a
# non-default value so existing 5-field operator YAML round-trips.
_DEFAULT_RR = "A"


# ---------------------------------------------------------------------------
# Domain model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class UnboundHostOverrideConfig:
    """Desired-state Unbound host-override configuration.

    The operator-facing top-level YAML ``name`` is metadata only — used for
    ``ResourceOutcome`` addresses — and never travels on the wire. The diff
    engine matches on the natural-key tuple ``(hostname, domain, rr)``.

    ``lock`` is a per-resource safety annotation (ADR-0014 §6) — locked
    entries appear in ``Diff.locked`` but are never added, updated, or
    deleted.

    Attributes:
        name: Operator-facing YAML name; metadata only.
        hostname: Hostname label (e.g., ``"web"`` in ``web.example.com``).
        domain: Parent domain (e.g., ``"example.com"``).
        rr: Record type — ``A`` (default) / ``AAAA`` / ``MX``.
        server: IP address (IPv4 for A; IPv6 for AAAA; commonly absent on MX).
        description: Operator-facing free-form description.
        enabled: Whether the override is active.
        mxprio: MX priority (MX records only; preserved as a string).
        mx: MX target hostname (MX records only).
        lock: Per-resource safety annotation (ADR-0014 §6).
    """

    name: str
    hostname: str
    domain: str
    rr: str = _DEFAULT_RR
    server: str = ""
    description: str = ""
    enabled: bool = True
    mxprio: str = ""
    mx: str = ""
    lock: bool = False

    @property
    def diff_key(self) -> tuple[str, str, str]:
        """Identity of this override: the ``(hostname, domain, rr)`` tuple."""
        return (self.hostname, self.domain, self.rr)

    def to_payload(self) -> dict[str, Any]:
        """Serialize to the ``addHostOverride``/``setHostOverride`` envelope.

        Returns:
            ``{"host": {<fields>}}``. Booleans are stringified to
            ``"0"``/``"1"``. The operator-facing top-level ``name`` is
            intentionally NOT sent — it is metadata only. Optional MX
            fields are emitted as empty strings rather than omitted so
            the wire payload shape is consistent across rr types.
        """
        return {
            "host": {
                "hostname": self.hostname,
                "domain": self.domain,
                "rr": self.rr,
                "server": self.server,
                "description": self.description,
                "enabled": _bool_str(self.enabled),
                "mxprio": self.mxprio,
                "mx": self.mx,
            }
        }


@dataclass(frozen=True)
class LiveUnboundHostOverride:
    """An Unbound host override as currently configured on the OPNsense box.

    ``raw`` is the ``searchHostOverride`` row, which carries every field we
    need to round-trip the override to YAML (no separate ``getHostOverride``
    call needed for export — the search row is dense).

    Attributes:
        uuid: OPNsense-assigned UUID for the host override.
        hostname: Hostname label (e.g., ``"web"`` in ``web.example.com``).
        domain: Parent domain (e.g., ``"example.com"``).
        rr: Record type — ``A`` / ``AAAA`` / ``MX``.
        raw: Full original ``searchHostOverride`` row.
    """

    uuid: str
    hostname: str
    domain: str
    rr: str
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def diff_key(self) -> tuple[str, str, str]:
        """Identity of this override: the ``(hostname, domain, rr)`` tuple."""
        return (self.hostname, self.domain, self.rr)


@dataclass
class Diff:
    """Result of comparing desired YAML state to live OPNsense state.

    Mirrors ``services.unbound_host_alias.Diff``: adds / updates / deletes /
    locked, plus ``is_empty``. Updates carry the live record alongside the
    desired record so the caller has the UUID. Locked entries pair desired
    YAML with their (possibly missing) live record.

    Note that changing ``hostname`` / ``domain`` / ``rr`` produces a delete +
    add, not an update — the live record's tuple no longer matches anything
    in YAML and a new tuple appears with no live counterpart.
    """

    adds: list[UnboundHostOverrideConfig] = field(default_factory=list)
    updates: list[tuple[LiveUnboundHostOverride, UnboundHostOverrideConfig]] = field(
        default_factory=list
    )
    deletes: list[LiveUnboundHostOverride] = field(default_factory=list)
    locked: list[tuple[UnboundHostOverrideConfig, LiveUnboundHostOverride | None]] = field(
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
    desired: list[UnboundHostOverrideConfig],
    current: list[LiveUnboundHostOverride],
    *,
    add_only: bool = False,
) -> Diff:
    """Compare desired YAML state to live state, keyed by ``(hostname, domain, rr)``.

    Args:
        desired: Overrides the operator wants to exist.
        current: Overrides currently on the box.
        add_only: If True, never emit deletes for live overrides that don't
            appear in ``desired``. Adds and updates still happen.

    Returns:
        ``Diff`` with adds / updates / deletes plus locked entries.
    """
    desired_by_key: dict[tuple[str, str, str], UnboundHostOverrideConfig] = {
        a.diff_key: a for a in desired
    }
    current_by_key: dict[tuple[str, str, str], LiveUnboundHostOverride] = {
        a.diff_key: a for a in current
    }
    locked_keys: set[tuple[str, str, str]] = {a.diff_key for a in desired if a.lock}

    adds: list[UnboundHostOverrideConfig] = []
    updates: list[tuple[LiveUnboundHostOverride, UnboundHostOverrideConfig]] = []
    deletes: list[LiveUnboundHostOverride] = []
    locked: list[tuple[UnboundHostOverrideConfig, LiveUnboundHostOverride | None]] = []

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


def _needs_update(have: LiveUnboundHostOverride, want: UnboundHostOverrideConfig) -> bool:
    """Return True if the live row's fields differ from the desired payload.

    Compares the inner ``host`` payload from ``want.to_payload()`` against
    the corresponding fields on ``have.raw``. ``searchHostOverride`` returns
    most fields as flat strings, with ``rr`` rendered as a select option
    dict — ``_normalize_field`` collapses both shapes to a comparable
    string.
    """
    payload = want.to_payload()["host"]
    for key, want_value in payload.items():
        have_value = _normalize_field(have.raw.get(key))
        if str(want_value) != have_value:
            return True
    return False


def _normalize_field(value: Any) -> str:
    """Collapse an OPNsense field value to a comparable string.

    Mirrors ``services.unbound_host_alias._normalize_field``: select fields
    returned as option dicts (``{value: {selected: 1, value: ...}}``) have
    their selected key extracted; bools serialize to ``"1"``/``"0"``; ``None``
    becomes ``""``; plain scalars are stringified.
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


def _bool_str(value: bool) -> str:
    """Convert a Python bool to OPNsense's ``"0"``/``"1"`` representation."""
    return "1" if value else "0"


# ---------------------------------------------------------------------------
# Resource-to-domain conversion
# ---------------------------------------------------------------------------


def unbound_host_override_configs_from_resources(
    resources: list[ResourceConfig],
) -> list[UnboundHostOverrideConfig]:
    """Convert ``ResourceConfig`` entries to ``UnboundHostOverrideConfig`` instances.

    Validation here is intentionally minimal — the validator handles
    operator-friendly error messages with cross-resource awareness; this
    parser only enforces type sanity so manager code can rely on field
    invariants.

    Args:
        resources: All provider resources from a ConfigManager load.
            Non-``unbound_host_override`` entries are silently skipped.

    Returns:
        Validated ``UnboundHostOverrideConfig`` list.

    Raises:
        ValueError: If an entry has a non-dict config, missing required
            fields, or non-bool booleans / non-string fields.
    """
    configs: list[UnboundHostOverrideConfig] = []
    for resource in resources:
        if resource.type != "unbound.host_overrides":
            continue

        config = resource.config
        if not isinstance(config, dict):
            raise ValueError(f"unbound_host_override '{resource.name}' has non-dict config")

        hostname = config.get("hostname", "")
        if not isinstance(hostname, str) or not hostname:
            raise ValueError(
                f"unbound_host_override '{resource.name}' requires a non-empty string 'hostname'"
            )

        domain = config.get("domain", "")
        if not isinstance(domain, str) or not domain:
            raise ValueError(
                f"unbound_host_override '{resource.name}' requires a non-empty string 'domain'"
            )

        rr = config.get("rr", _DEFAULT_RR)
        if not isinstance(rr, str) or not rr:
            raise ValueError(
                f"unbound_host_override '{resource.name}' rr must be a non-empty string"
            )

        server = config.get("server", "")
        if not isinstance(server, str):
            raise ValueError(f"unbound_host_override '{resource.name}' server must be a string")

        description = config.get("description", "")
        if not isinstance(description, str):
            raise ValueError(
                f"unbound_host_override '{resource.name}' description must be a string"
            )

        mxprio = config.get("mxprio", "")
        if not isinstance(mxprio, str):
            raise ValueError(
                f"unbound_host_override '{resource.name}' mxprio must be a string "
                f"(preserved as string to retain numeric precision)"
            )

        mx = config.get("mx", "")
        if not isinstance(mx, str):
            raise ValueError(f"unbound_host_override '{resource.name}' mx must be a string")

        enabled = _require_bool(config, "enabled", default=True, resource_name=resource.name)
        lock = _require_bool(config, "lock", default=False, resource_name=resource.name)

        configs.append(
            UnboundHostOverrideConfig(
                name=resource.name,
                hostname=hostname,
                domain=domain,
                rr=rr,
                server=server,
                description=description,
                enabled=enabled,
                mxprio=mxprio,
                mx=mx,
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
            f"unbound_host_override '{resource_name}' {field_name} must be a boolean "
            f"(true/false), got {type(value).__name__}"
        )
    return value


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class UnboundHostOverrideService(BaseService):
    """Service for OPNsense Unbound host-override operations via direct API.

    Identity is the natural-key ``(hostname, domain, rr)`` tuple — the diff
    engine matches operator YAML directly to live records by tuple. The
    operator-facing top-level ``name`` never travels on the wire.

    The read-side ``search`` / ``export_to_yaml`` were added in #748; the
    full write surface (add / update / delete / get / reconfigure /
    compute_diff / apply_diff) lands in #776.
    """

    # ------------------------------------------------------------------
    # API operations (CRUD + reconfigure)
    # ------------------------------------------------------------------

    def search(self) -> list[LiveUnboundHostOverride]:
        """Fetch the live host-override list.

        Returns:
            ``LiveUnboundHostOverride`` instances normalized from the
            ``searchHostOverride`` rows. Defensive against non-dict
            responses and missing ``rows`` key — both yield ``[]``.
        """
        response = self.client.request("POST", f"{_HOST_OVERRIDE_BASE}/searchHostOverride")

        rows: list[dict[str, Any]] = []
        if isinstance(response, dict):
            raw_rows = response.get("rows")
            if isinstance(raw_rows, list):
                rows = [r for r in raw_rows if isinstance(r, dict)]

        return [_row_to_live(row) for row in rows]

    def get(self, uuid: str) -> dict[str, Any]:
        """Fetch the full host-override record by UUID.

        Returns the raw envelope ``{"host": {...}}``.

        Args:
            uuid: OPNsense-assigned host-override UUID.

        Returns:
            API response dict.
        """
        return self.client.request("GET", f"{_HOST_OVERRIDE_BASE}/getHostOverride/{uuid}")

    def add(self, override: UnboundHostOverrideConfig) -> dict[str, Any]:
        """Create a host override.

        Args:
            override: Desired-state host-override configuration.

        Returns:
            API response dict (typically ``{"result": "saved", "uuid": ...}``).
        """
        return self.client.request(
            "POST",
            f"{_HOST_OVERRIDE_BASE}/addHostOverride",
            data=override.to_payload(),
        )

    def update(self, uuid: str, override: UnboundHostOverrideConfig) -> dict[str, Any]:
        """Update an existing host override by UUID.

        Args:
            uuid: OPNsense-assigned override UUID.
            override: New desired-state configuration.

        Returns:
            API response dict.
        """
        return self.client.request(
            "POST",
            f"{_HOST_OVERRIDE_BASE}/setHostOverride/{uuid}",
            data=override.to_payload(),
        )

    def delete(self, uuid: str) -> dict[str, Any]:
        """Delete a host override by UUID.

        Args:
            uuid: OPNsense-assigned override UUID.

        Returns:
            API response dict (typically ``{"result": "deleted"}``).
        """
        return self.client.request("POST", f"{_HOST_OVERRIDE_BASE}/delHostOverride/{uuid}")

    def reconfigure(self) -> dict[str, Any]:
        """Apply pending Unbound changes (commit staged config to running system).

        Must be called after add/update/delete operations to activate them.
        Response shape per the OpenAPI spec is ``{"status": "ok" | "failed"}``.

        Note:
            ``UnboundHostOverrideManager`` does **not** call this method
            from its ``apply``/``destroy`` paths (#776). The runner fires
            the shared ``unbound_reconfigure`` finalization hook exactly
            once per apply when any of the three unbound managers
            (host_override / host_alias / forward) mutated state. Callers
            that bypass the manager (e.g., manual operator scripts) can
            still invoke ``reconfigure()`` directly.
        """
        return self.client.request("POST", _RECONFIGURE_PATH)

    # ------------------------------------------------------------------
    # Diff + apply orchestration
    # ------------------------------------------------------------------

    def compute_diff(
        self,
        desired: list[UnboundHostOverrideConfig],
        live: list[LiveUnboundHostOverride],
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

        for override in diff.adds:
            self.add(override)
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
        """Export the current host overrides to InfraFoundry YAML.

        For each live host override the ``searchHostOverride`` row already
        carries every field we need (no extra ``getHostOverride`` round-trip
        required). Operator-facing ``name`` is synthesized from
        ``hostname.domain`` (with ``-<rr>`` suffix when ``rr`` is non-default)
        for stable, human-readable resource keys. The operator can rename
        after import — identity is the natural-key tuple, not the name.

        Returns:
            YAML string with ``provider/type/name/config`` entries.
        """
        live = self.search()
        resources = [
            {
                "provider": "opnsense",
                "type": "unbound_host_override",
                "name": _synthesize_name(override),
                "config": _live_to_export_config(override),
            }
            for override in live
        ]
        return yaml.safe_dump({"resources": resources}, sort_keys=False)


# ---------------------------------------------------------------------------
# Internal helpers (row parsing / export)
# ---------------------------------------------------------------------------


def _row_to_live(row: dict[str, Any]) -> LiveUnboundHostOverride:
    """Normalize a ``searchHostOverride`` row into a ``LiveUnboundHostOverride``."""
    uuid = str(row.get("uuid", ""))
    hostname = _normalize_field(row.get("hostname"))
    domain = _normalize_field(row.get("domain"))
    rr = _normalize_field(row.get("rr")) or _DEFAULT_RR
    return LiveUnboundHostOverride(uuid=uuid, hostname=hostname, domain=domain, rr=rr, raw=row)


def _synthesize_name(override: LiveUnboundHostOverride) -> str:
    """Build a resource ``name`` from a live host override.

    Uses the ``<hostname>-<dot-replaced-domain>`` form (mirrors
    ``services.unbound_forward._synthesize_name``). When ``rr`` is non-default
    (``AAAA`` / ``MX``), the record type is appended as a suffix so an A and
    an AAAA (or MX) record on the same hostname produce distinct resource
    names rather than colliding.

    Falls back gracefully when either part is missing (defensive — should
    not happen in practice but keeps the extractor robust against
    malformed rows).
    """
    parts: list[str] = []
    if override.hostname:
        parts.append(override.hostname)
    if override.domain:
        parts.append(override.domain.replace(".", "-"))
    if override.rr and override.rr != _DEFAULT_RR:
        parts.append(override.rr)
    if not parts:
        return override.uuid.lower()
    return "-".join(parts).lower()


def _live_to_export_config(override: LiveUnboundHostOverride) -> dict[str, Any]:
    """Build a YAML-friendly config dict from a ``LiveUnboundHostOverride``.

    Always emits the base fields (``hostname``, ``domain``, ``enabled``);
    optional fields (``server``, ``description``, ``rr``, ``mxprio``, ``mx``)
    are only emitted when the live record carries a non-default value so
    existing 5-field operator YAML round-trips identically.
    """
    raw = override.raw

    config: dict[str, Any] = {
        "hostname": override.hostname,
        "domain": override.domain,
        "enabled": _normalize_field(raw.get("enabled")) != "0",
    }

    # ``server`` — IPv4 / IPv6 address; commonly absent on MX records.
    server = _normalize_field(raw.get("server"))
    if server:
        config["server"] = server

    # ``description`` — operator note; only emit when non-empty.
    description = _normalize_field(raw.get("description"))
    if description:
        config["description"] = description

    # ``rr`` — record type. Default ``A``; emit only when non-default.
    if override.rr and override.rr != _DEFAULT_RR:
        config["rr"] = override.rr

    # ``mxprio`` / ``mx`` — MX records only; preserved as strings.
    mxprio = _normalize_field(raw.get("mxprio"))
    if mxprio:
        config["mxprio"] = mxprio

    mx = _normalize_field(raw.get("mx"))
    if mx:
        config["mx"] = mx

    return config
